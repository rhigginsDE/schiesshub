"""Ranglisten je Wettbewerb und die Übersicht aller Wettbewerbe eines Turniers.

Platzierung, Gleichstand und Mehrfachstart rechnet `app.scoring` (`rank`, `best_of`); hier wird
nur ausgewählt, gruppiert und dargestellt. Personen erscheinen nur so, wie sie es gewählt haben
(`display_mode`): voll, abgekürzt oder gar nicht (dann nur die Startnummer); den Verein nur mit
`show_club`. Den vollen Namen liefern diese Sichten nie, wenn die Person ihn nicht freigibt.

- Regel für Plätze: `RankPolicy.for_list` aus `app.scoring` – dieselbe für Rangliste, Anzeige
  und Export. Abgebrochene Starts (nicht angetreten, aufgegeben, disqualifiziert) bekommen nie
  einen Platz; sie stehen am Ende ihrer Gruppe ohne Platz (`group=unranked`, `abort_reason`),
  mit `include_aborted=false` gar nicht.
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

from app.modules.ergebnisse.models import ResultCurrent
from app.modules.ergebnisse.recompute import ensure_current
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
from app.modules.ergebnisse.service import competition_of, is_provisional, server_now
from app.modules.starts.common import get_tournament
from app.modules.starts.models import Entry, Start
from app.modules.teilnehmer.models import Club, Person
from app.modules.teilnehmer.names import display_name
from app.modules.turnier.models import Competition, TournamentClass
from app.scoring import ComputedResult, Contender, Placement, RankPolicy, best_of, rank

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

    def contender(self) -> Contender:
        return Contender(
            id=str(self.start.id),
            entry_id=str(self.entry.id),
            attempt=self.start.attempt,
            key=self.key,
            complete=self.computed.complete if self.computed is not None else False,
            abort_reason=self.start.abort_reason,
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


def _row(candidate: Candidate, placement: Placement | None) -> RankingRow:
    computed = candidate.computed
    person = candidate.person
    return RankingRow(
        place=placement.place if placement is not None else None,
        tied=placement.tied if placement is not None else False,
        tie_unresolved=placement.tie_unresolved if placement is not None else False,
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
    )


async def _candidates(
    session: AsyncSession, competition: Competition, now: datetime
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
            )
        )
    return candidates


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
    every = await _candidates(session, competition, now)
    rule = competition.multi_start_rule

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
        rows = _rank_group(members, rule, policy)
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
        unit=sample.unit if sample else None,
        generated_at=now,
        groups=groups,
    )


def _rank_group(members: list[Candidate], rule: str, policy: RankPolicy) -> list[RankingRow]:
    rankable = [c for c in members if c.rankable]
    unrankable = [c for c in members if not c.rankable]
    contenders = [c.contender() for c in rankable]
    if rule == "best":
        contenders = best_of(contenders, "best", policy)
    by_id = {str(c.start.id): c for c in rankable}
    rows = [_row(by_id[placement.id], placement) for placement in rank(contenders, policy)]
    # Nach einer Änderung der Wertung nicht wertbar: ohne Platz, zum Prüfen – vor den
    # Abgebrochenen, die immer am Ende stehen.
    cut = next((i for i, row in enumerate(rows) if row.abort_reason is not None), len(rows))
    rows[cut:cut] = [_row(candidate, None) for candidate in unrankable]
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
