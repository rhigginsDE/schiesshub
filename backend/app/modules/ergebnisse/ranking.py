"""Ranglisten je Wettbewerb und die Übersicht aller Wettbewerbe eines Turniers.

Platzierung, Gleichstand und Mehrfachstart rechnet `app.scoring` (`rank`, `best_of`); hier wird
nur ausgewählt, gruppiert und dargestellt. Personen erscheinen nur so, wie sie es gewählt haben
(`display_mode`): voll, abgekürzt oder gar nicht (dann nur die Startnummer); den Verein nur mit
`show_club`. Den vollen Namen liefern diese Sichten nie, wenn die Person ihn nicht freigibt.

- Regel für Plätze: `RankPolicy.for_list` aus `app.scoring` – dieselbe für Rangliste, Anzeige
  und Export.
- Abbruch (Sporthandbuch K 1.14 / L 1.12): Ein aufgegebener Start (`dnf`) mit erfassten
  Wertungswerten wird nach dem bis dahin erzielten Ergebnis platziert; nicht geschossene Serien
  zählen nach der Regel der Wertung (`rules.evaluate_aborted`, `app.scoring.compute_aborted`).
  `score`, `series` und der Vergleichsschlüssel der Zeile sind dann dieses Ergebnis (nicht der
  gespeicherte Zwischenstand); es wird beim Lesen aus Rohwerten und Definition gerechnet.
- Ohne Platz bleiben: nicht angetreten (dns), disqualifiziert (dsq), Abbruch ohne
  Wertungswert (Abbruch im Probeschießen, „AB“) und Abbrüche, deren Ergebnis sich nicht
  vergleichen lässt (`abort_note`). Sie stehen am Ende ihrer Gruppe (`group=unranked`), mit
  `include_aborted=false` gar nicht.
- Formelle Wörter (Abbruchgrund, Gleichheit, Titel) kommen aus `begriffe.py`, je Wettbewerb nach
  dem Begriffssatz seines Verbands (`catalog_federation`).
- `abort_remark`: Bemerkung der Bedienung beim Abbrechen (nur in dieser Rangliste, nicht in
  Anzeige und Export).
- Einheit: aus der aktuellen Definition („Treffer“ bei reiner Trefferzählung); ein gespeichertes
  Ergebnis mit anderer Einheit wird beim Lesen angeglichen. Bei reiner Trefferzählung sind
  `tens`/`inner_tens` immer null.
- Gleichstand: Zeilen mit gleichem Ergebnis, die die Gleichstandskette trennt, tragen
  `tie_reason="resolved"`, das entscheidende Kriterium und den Hinweis dazu.
- `scope=final`: abgeschlossene Ergebnisse und Abbrüche; ein unvollständiges Ergebnis (nach
  einer Änderung der Wertung) steht ohne Platz da.
- `scope=live`: zusätzlich laufende Zwischenstände (Status `registered`/`called`/`captured` mit
  erfasstem Stand), gekennzeichnet als `running`; unvollständige stehen hinter den vollständigen.
- `include_provisional=false` lässt Ergebnisse in der Einspruchsfrist weg.
- Mehrfachstart: `best` – der beste der berücksichtigten Starts; `first` – der erste Start der
  Person (fehlt dessen Ergebnis noch, erscheint sie nicht); `all` – jeder Start für sich.
- Klassen: je Klasse eine Gruppe; mit `merged=true` werden Klassen über `merge_into_id`
  zusammengelegt. Bei `combined_ranking` gibt es eine gemeinsame Gruppe; `class_id` filtert dann
  nur die Zeilen, die Plätze bleiben die der gemeinsamen Wertung.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.begriffe import Begriffe
from app.modules.ergebnisse import begriffe
from app.modules.ergebnisse.models import ResultCurrent
from app.modules.ergebnisse.recompute import ensure_current
from app.modules.ergebnisse.rules import AbortedEvaluation, aborted_for_raw, scoring_definition
from app.modules.ergebnisse.schemas import (
    CompetitionSummary,
    LeaderOut,
    RankingGroup,
    RankingOut,
    RankingRow,
    RankingSummaryOut,
    RowStatus,
    SeriesPart,
    StatusCounts,
)
from app.modules.ergebnisse.service import (
    abort_remarks,
    competition_of,
    is_provisional,
    server_now,
)
from app.modules.starts.common import get_tournament
from app.modules.starts.models import Entry, Start
from app.modules.teilnehmer.models import Club, Person
from app.modules.teilnehmer.names import display_name
from app.modules.turnier.models import Competition, TournamentClass
from app.scoring import (
    ComputedResult,
    Contender,
    Definition,
    DefinitionError,
    Placement,
    RankPolicy,
    TieRules,
    best_of,
    load_definition,
    rank,
    tie_rules,
)
from app.scoring.numbers import format_number

Scope = Literal["final", "live"]


def policy_for(scope: Scope, include_aborted: bool = True) -> RankPolicy:
    return RankPolicy.for_list(final=scope == "final", include_aborted=include_aborted)


@dataclass(slots=True)
class Candidate:
    start: Start
    entry: Entry
    person: Person
    club: str | None
    klass: TournamentClass
    current: ResultCurrent | None
    computed: ComputedResult | None
    key: list[int | None] | None
    status: RowStatus
    aborted: AbortedEvaluation | None = None
    """Nur bei aufgegebenen Starts (`dnf`): Wertung nach K 1.14 / L 1.12."""
    abort_remark: str | None = None
    """Bemerkung beim Abbrechen (Grund des Ereignisses `aborted`)."""

    @property
    def abort_placed(self) -> bool:
        return self.aborted is not None and self.aborted.placed

    @property
    def abort_note(self) -> str | None:
        if self.aborted is None or self.aborted.placed:
            return None
        return begriffe.abort_note(self.aborted.reason, self.aborted.labels)

    def contender(self) -> Contender:
        return Contender(
            id=str(self.start.id),
            entry_id=str(self.entry.id),
            attempt=self.start.attempt,
            key=self.key,
            complete=self.computed.complete if self.computed is not None else False,
            abort_reason=self.start.abort_reason,
            abort_ranked=self.abort_placed,
        )

    @property
    def rankable(self) -> bool:
        """Ohne Vergleichsschlüssel nur Abgebrochene (ohne Platz) oder „prüfen“ (ohne Platz)."""
        return self.key is not None or self.start.abort_reason is not None


def _status(start: Start, current: ResultCurrent | None, now: datetime) -> RowStatus:
    if current is not None and current.needs_review:
        return "review"
    if start.status == "aborted":
        return "aborted"
    if start.status == "final":
        return "provisional" if is_provisional(current, now) else "final"
    return "running"


def _include(
    start: Start, current: ResultCurrent | None, scope: Scope, provisional: bool, now: datetime
) -> bool:
    match start.status:
        case "final":
            return provisional or not is_provisional(current, now)
        case "aborted":
            return True
        case "registered" | "called" | "captured":
            # Laufend ist, wozu es schon einen Zwischenstand gibt, auch ohne Aufruf.
            return scope == "live" and current is not None
    return False


def _merge_target(
    class_id: uuid.UUID, classes: dict[uuid.UUID, TournamentClass], merged: bool
) -> uuid.UUID:
    if not merged:
        return class_id
    seen = {class_id}
    target = class_id
    while (parent := classes[target].merge_into_id) is not None and parent in classes:
        if parent in seen:
            break  # Ringverweis: bei der letzten Klasse vor dem Kreis bleiben
        seen.add(parent)
        target = parent
    return target


def _series(computed: ComputedResult | None) -> list[SeriesPart]:
    if computed is None:
        return []
    return [
        SeriesPart(
            section_id=section.id,
            number=series.number,
            struck=series.struck,
            status=series.status,
            rings=series.rings,
            time_cs=series.time_cs,
            standing=series.standing,
            total_cs=series.total_cs,
        )
        for section in computed.sections
        for series in section.series
    ]


def _row(
    candidate: Candidate,
    placement: Placement | None,
    tie_word: str = begriffe.NEUTRAL_TIE,
    terms: Begriffe | None = None,
    hits_only: bool = False,
) -> RankingRow:
    computed = candidate.computed
    person = candidate.person
    tie_note = tie_note_long = None
    if placement is not None and placement.tie_note is not None:
        args = (placement.tie_reason, placement.tie_criterion, placement.place, tie_word)
        tie_note = begriffe.tie_note(*args, hits_only=hits_only)
        tie_note_long = begriffe.tie_note(*args, long=True)
    return RankingRow(
        place=placement.place if placement is not None else None,
        tied=placement.tied if placement is not None else False,
        tie_unresolved=placement.tie_unresolved if placement is not None else False,
        tie_reason=placement.tie_reason if placement is not None else None,
        tie_criterion=placement.tie_criterion if placement is not None else None,
        needs_shootoff=placement.needs_shootoff if placement is not None else False,
        tie_note=tie_note,
        tie_note_long=tie_note_long,
        group=placement.group if placement is not None else "unranked",
        start_id=candidate.start.id,
        entry_id=candidate.entry.id,
        start_number=candidate.entry.start_number,
        attempt=candidate.start.attempt,
        display_name=display_name(person.name_enc, person.display_mode),
        club=candidate.club if person.show_club else None,
        class_id=candidate.klass.id,
        class_short=candidate.klass.short,
        score=computed.score if computed is not None else None,
        score_text=computed.score_text if computed is not None else None,
        complete=computed.complete if computed is not None else False,
        tens=computed.tens if computed is not None else None,
        inner_tens=computed.inner_tens if computed is not None else None,
        series=_series(computed),
        status=candidate.status,
        abort_reason=candidate.start.abort_reason,
        provisional_until=candidate.current.provisional_until if candidate.current else None,
        abort_label=begriffe.abort_label(candidate.start.abort_reason, terms),
        abort_note=candidate.abort_note,
        abort_remark=candidate.abort_remark if candidate.start.abort_reason else None,
    )


async def _candidates(
    session: AsyncSession,
    competition: Competition,
    now: datetime,
    unit: str | None = None,
    hits_only: bool = False,
) -> list[Candidate]:
    rows = await session.execute(
        select(Start, Entry, Person, Club.name, TournamentClass, ResultCurrent)
        .join(Entry, Entry.id == Start.entry_id)
        .join(Person, Person.id == Entry.person_id)
        .outerjoin(Club, Club.id == Person.club_id)
        .join(TournamentClass, TournamentClass.id == Entry.class_id)
        .outerjoin(ResultCurrent, ResultCurrent.start_id == Start.id)
        .where(Start.competition_id == competition.id)
        .order_by(Entry.start_number, Start.attempt)
    )
    candidates = []
    for start, entry, person, club, klass, current in rows:
        computed = (
            ComputedResult.model_validate(current.computed)
            if current is not None and current.computed is not None
            else None
        )
        key = current.rank_keys if current is not None else None
        aborted = aborted_evaluation(competition, start.abort_reason, current)
        if aborted is not None and aborted.placed:
            computed, key = aborted.computed, aborted.rank_keys
        if computed is not None and unit is not None and computed.unit != unit:
            computed = computed.model_copy(
                update={"unit": unit, "score_text": f"{format_number(computed.score)} {unit}"}
            )
        if (
            computed is not None
            and hits_only
            and (computed.tens, computed.inner_tens)
            != (
                None,
                None,
            )
        ):
            # Reine Trefferzählung kennt keine Zehner (ältere Stände hatten hier 0).
            computed = computed.model_copy(update={"tens": None, "inner_tens": None})
        candidates.append(
            Candidate(
                start,
                entry,
                person,
                club,
                klass,
                current,
                computed,
                key,
                _status(start, current, now),
                aborted,
            )
        )
    return candidates


def aborted_evaluation(
    competition: Competition, abort_reason: str | None, current: ResultCurrent | None
) -> AbortedEvaluation | None:
    """Aufgegebener Start (`dnf`): Wertung nach K 1.14 / L 1.12 aus Rohwerten und aktueller
    Definition; None bei anderen Starts. Dieselbe Funktion für Rangliste, Anzeige und Export."""
    if abort_reason != "dnf":
        return None
    if current is None:
        return AbortedEvaluation(has_values=False)
    return aborted_for_raw(competition.definition, competition.capture_mode, current.raw)


def list_result(
    competition: Competition, abort_reason: str | None, current: ResultCurrent | None
) -> ComputedResult | None:
    """Das Ergebnis, das in Listen steht: bei einem platzierten Abbruch das nach K 1.14 / L 1.12
    gewertete, sonst das gespeicherte."""
    aborted = aborted_evaluation(competition, abort_reason, current)
    if aborted is not None and aborted.placed:
        return aborted.computed
    if current is None or current.computed is None:
        return None
    return ComputedResult.model_validate(current.computed)


async def competition_ranking(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    competition_id: uuid.UUID,
    *,
    class_id: uuid.UUID | None = None,
    include_provisional: bool = True,
    scope: Scope = "final",
    merged: bool = False,
    include_aborted: bool = True,
) -> RankingOut:
    """Rangliste eines Wettbewerbs; die gemeinsame Quelle für Anzeige und Export."""
    competition = await competition_of(session, tournament_id, competition_id)
    if await ensure_current(session, competition):
        await session.refresh(competition)
    return await _ranking(
        session,
        competition,
        class_id=class_id,
        include_provisional=include_provisional,
        scope=scope,
        merged=merged,
        include_aborted=include_aborted,
    )


async def _ranking(
    session: AsyncSession,
    competition: Competition,
    *,
    class_id: uuid.UUID | None,
    include_provisional: bool,
    scope: Scope,
    merged: bool,
    include_aborted: bool = True,
) -> RankingOut:
    now = await server_now(session)
    policy = policy_for(scope, include_aborted)
    classes = {
        item.id: item
        for item in await session.scalars(
            select(TournamentClass).where(
                TournamentClass.tournament_id == competition.tournament_id
            )
        )
    }
    defn = _definition(competition)
    unit = defn.unit if defn is not None else None
    every = await _candidates(
        session, competition, now, unit, hits_only=defn is not None and defn.hits_only
    )
    remarks = await abort_remarks(
        session, [c.start.id for c in every if c.start.abort_reason is not None]
    )
    for candidate in every:
        candidate.abort_remark = remarks.get(candidate.start.id)
    rule = competition.multi_start_rule
    rules = tie_rules(defn) if defn is not None else None
    terms = begriffe.terms_for(competition.catalog_federation)
    word = _tie_word(competition, defn, terms)
    # Kurztexte der Kriterien: Fall „treffer“ („letzte Serie“), wenn die Serien wie im Ablauf
    # verglichen werden (Wurfscheibe), sonst „letzte Zehnerserie“ – auch bei Treffer/Fehler mit
    # `gleichstand_serie: zehn_schuss`.
    hits_only = defn is not None and defn.tie_series_as_defined

    # Gruppen gibt es für jede Klasse mit Starts, auch wenn noch kein Ergebnis zählt.
    def group_of(candidate: Candidate) -> uuid.UUID | None:
        if competition.combined_ranking:
            return None
        return _merge_target(candidate.entry.class_id, classes, merged)

    member_classes: dict[uuid.UUID | None, set[uuid.UUID]] = defaultdict(set)
    for candidate in every:
        member_classes[group_of(candidate)].add(candidate.entry.class_id)
    if not competition.combined_ranking and class_id is not None:
        member_classes = defaultdict(set, {class_id: member_classes.get(class_id, {class_id})})

    candidates = every
    if rule == "first":
        # Zählt nur der erste Start, entscheidet das ungefiltert (sonst rückte der zweite nach).
        first = {c.id for c in best_of([c.contender() for c in candidates], "first", policy)}
        candidates = [c for c in candidates if str(c.start.id) in first]
    grouped: dict[uuid.UUID | None, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        if _include(candidate.start, candidate.current, scope, include_provisional, now):
            grouped[group_of(candidate)].append(candidate)

    groups = []
    order = sorted(
        member_classes,
        key=lambda k: (classes[k].sort, classes[k].name) if k in classes else (-1, ""),
    )
    for group_key in order:
        members = grouped.get(group_key, [])
        rows = _rank_group(members, rule, policy, rules, word, terms, hits_only)
        if competition.combined_ranking and class_id is not None:
            rows = [row for row in rows if row.class_id == class_id]
        group_class = classes.get(group_key) if group_key is not None else None
        ids = member_classes[group_key] | ({group_key} if group_key is not None else set())
        groups.append(
            RankingGroup(
                class_id=group_key,
                class_name=group_class.name if group_class else None,
                class_short=group_class.short if group_class else None,
                class_ids=sorted(ids, key=str),
                rows=rows,
            )
        )
    sample = next((c.computed for c in every if c.computed is not None), None)
    return RankingOut(
        competition_id=competition.id,
        competition_name=competition.name,
        competition_code=competition.catalog_code,
        scope=scope,
        include_provisional=include_provisional,
        merged=merged,
        combined=competition.combined_ranking,
        multi_start_rule=rule,
        direction=sample.direction if sample else None,
        unit=(unit or sample.unit) if sample else None,
        generated_at=now,
        groups=groups,
        tie_word=word,
        federation=_federation(competition),
        result_list_title=terms.ergebnisliste,
    )


def _definition(competition: Competition) -> Definition | None:
    """Aktuelle Definition der Wertung; None, wenn die Wertung sie nicht lesen kann (die
    Ergebnisse stehen dann ohnehin zum Prüfen an)."""
    try:
        return load_definition(scoring_definition(competition.definition))
    except DefinitionError, KeyError, TypeError:
        return None


def _federation(competition: Competition) -> str | None:
    federation = (competition.catalog_federation or "").strip().lower()
    return federation or None


def _tie_word(competition: Competition, defn: Definition | None, terms: Begriffe) -> str:
    scoring = (competition.definition or {}).get("scoring") or {}
    return begriffe.tie_word(
        scoring.get("modell"),
        scoring.get("gleichstand") or (),
        terms,
        hits_only=defn is not None and defn.hits_only,
    )


def _rank_group(
    members: list[Candidate],
    rule: str,
    policy: RankPolicy,
    rules: TieRules | None = None,
    tie_word: str = begriffe.NEUTRAL_TIE,
    terms: Begriffe | None = None,
    hits_only: bool = False,
) -> list[RankingRow]:
    rankable = [c for c in members if c.rankable]
    unrankable = [c for c in members if not c.rankable]
    contenders = [c.contender() for c in rankable]
    if rule == "best":
        contenders = best_of(contenders, "best", policy)
    by_id = {str(c.start.id): c for c in rankable}
    if rules is not None and contenders:
        # Schlüssel aus einer älteren Definition passen nicht zur Regel: ohne Regel ranken.
        lengths = {len(c.key or []) for c in contenders if c.key is not None}
        if lengths and lengths != {1 + len(rules.slots)}:
            rules = None
    placements = rank(contenders, policy, rules)
    rows = [
        _row(by_id[placement.id], placement, tie_word, terms, hits_only) for placement in placements
    ]
    # Nach einer Änderung der Wertung nicht wertbar: ohne Platz, zum Prüfen – vor den
    # Abgebrochenen ohne Platz, die immer am Ende stehen.
    cut = next(
        (i for i, row in enumerate(rows) if row.abort_reason is not None and row.place is None),
        len(rows),
    )
    rows[cut:cut] = [_row(candidate, None, tie_word, terms) for candidate in unrankable]
    return rows


async def ranking_summary(session: AsyncSession, tournament_id: uuid.UUID) -> RankingSummaryOut:
    await get_tournament(session, tournament_id)
    competitions = list(
        await session.scalars(
            select(Competition)
            .where(Competition.tournament_id == tournament_id)
            .order_by(Competition.sort, Competition.name)
        )
    )
    counts: dict[uuid.UUID, StatusCounts] = defaultdict(StatusCounts)
    # Angemeldete Starts mit Zwischenstand laufen schon (nachträgliche Erfassung).
    registered_running: dict[uuid.UUID, int] = defaultdict(int)
    has_current = ResultCurrent.start_id.is_not(None)
    for competition_id, status, with_current, number in await session.execute(
        select(Start.competition_id, Start.status, has_current, func.count())
        .join(Competition, Competition.id == Start.competition_id)
        .outerjoin(ResultCurrent, ResultCurrent.start_id == Start.id)
        .where(Competition.tournament_id == tournament_id)
        .group_by(Start.competition_id, Start.status, has_current)
    ):
        item = counts[competition_id]
        setattr(item, status, getattr(item, status) + number)
        if status == "registered" and with_current:
            registered_running[competition_id] += number
    for competition in competitions:
        if await ensure_current(session, competition):
            await session.refresh(competition)
    review = dict(
        (
            await session.execute(
                select(ResultCurrent.competition_id, func.count())
                .where(
                    ResultCurrent.competition_id.in_([c.id for c in competitions]),
                    ResultCurrent.needs_review,
                )
                .group_by(ResultCurrent.competition_id)
            )
        ).all()
    )
    now = await server_now(session)
    provisional = dict(
        (
            await session.execute(
                select(ResultCurrent.competition_id, func.count())
                .join(Start, Start.id == ResultCurrent.start_id)
                .where(
                    ResultCurrent.competition_id.in_([c.id for c in competitions]),
                    Start.status == "final",
                    ResultCurrent.provisional_until > now,
                )
                .group_by(ResultCurrent.competition_id)
            )
        ).all()
    )
    summaries = []
    for competition in competitions:
        ranking = await _ranking(
            session,
            competition,
            class_id=None,
            include_provisional=True,
            scope="final",
            merged=False,
        )
        leaders = [
            LeaderOut(
                class_id=group.class_id,
                class_short=group.class_short,
                start_number=row.start_number,
                display_name=row.display_name,
                club=row.club,
                score_text=row.score_text,
                status=row.status,
            )
            for group in ranking.groups
            for row in group.rows
            if row.place == 1
        ]
        item = counts[competition.id]
        early = registered_running[competition.id]
        summaries.append(
            CompetitionSummary(
                competition_id=competition.id,
                competition_name=competition.name,
                counts=item,
                starts_total=item.registered
                + item.called
                + item.captured
                + item.final
                + item.aborted,
                starts_final=item.final,
                starts_running=item.called + item.captured + early,
                starts_waiting=item.registered - early,
                needs_review=review.get(competition.id, 0),
                provisional=provisional.get(competition.id, 0),
                leaders=leaders,
            )
        )
    return RankingSummaryOut(tournament_id=tournament_id, generated_at=now, competitions=summaries)
