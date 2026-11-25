"""Rangfolge, Gleichstand und Mehrfachstart.

**Vergleichsschlüssel** (`rank_key`): eine Liste ganzer Zahlen, bei der überall *größer besser*
ist. Erster Eintrag ist das Ergebnis in Hundertsteln (bei „aufsteigend“ negiert), danach je
gerechnetem Gleichstandskriterium der Definition seine Werte (`tiebreak.py`; `neuner_abwaerts`
ergibt neun Werte: Anzahl Neuner, Achter, …, Einer; `parcours_zeit` die negierte Parcourszeit in
cs). Fehlt die Angabe für ein Kriterium (Seriensumme ohne Zehner), steht dort `None`.

**Nicht gerechnete Kriterien:** `gleichstand` darf IDs enthalten, die die Wertung nicht rechnet
(z. B. `abstand_letzter_schuss`, `stechen`). Gerechnet wird bis zur ersten solchen ID; bleiben
Starts danach gleich, teilen sie sich den Platz mit `tie_reason="manual"` und dem Hinweis
„Gleichstand nach Sportordnung manuell entscheiden“.

**Stechen** (`stechen_bis_platz` N): Gleiches Ergebnis auf einem Platz bis N wird nicht nach
`gleichstand` getrennt, sondern teilt sich den Platz mit `needs_shootoff` („Ringgleichheit auf
Platz 2: Stechen“); das Stechen selbst erfasst die Wertung nicht. Maßgeblich ist der Platz, auf
dem die gleichen Starts beginnen. `stechen` in `gleichstand` wird dann übersprungen, ab Platz
N+1 gilt der Rest der Kette.

**Höchstergebnis** (`hoechstergebnis_gleicher_rang`, DSB-SpO 0.12.1 Satz 1): Wer das erzielbare
Höchstergebnis (`Definition.max_score`) erreicht, wird nicht unterschieden – alle teilen den
Platz mit `tie_reason="max_score"`, ohne Gleichstandskette, ohne Stechen und ohne „manuell“.

**Stechen beim Höchstergebnis** (`stechen_bei_hoechstergebnis`, DSB-SpO 9.4.3): Wer das
erzielbare Höchstergebnis erreicht, wird nicht nach `gleichstand` getrennt, sondern teilt den
Platz mit `tie_reason="max_score_shootoff"` und `needs_shootoff` („Höchstergebnis auf Platz 1:
Stechen“) – auf jedem Platz, vor `stechen_bis_platz` und der Kette. Das Stechen erfasst die
Wertung nicht.

**Kette je Platz** (`gleichstand_bis_platz` N, `gleichstand_danach`, DSB-SpO 9.4.1): Gleiche, die
auf Platz 1 bis N beginnen, trennt `gleichstand`, alle anderen `gleichstand_danach` (leer:
gleicher Platz). Maßgeblich ist wie beim Stechen der Platz, auf dem die Gleichen beginnen
(*Annahme*: Die SpO sagt nicht, was gilt, wenn ein Gleichstand über Platz N hinausreicht). Der
Vergleichsschlüssel enthält die Werte beider Ketten (`Definition.tie_criteria`).

**Gleichstand** (`rank`): Starts mit gleichem Ergebnis werden Kriterium für Kriterium getrennt.
Fehlt bei einem der noch Gleichen der Wert des nächsten Kriteriums, endet die Trennung dort: Die
Gruppe teilt sich den Platz und wird als „nicht auflösbar“ markiert (`tie_unresolved`).
Ohne Gleichstandsregel (z. B. Fallscheibe) teilen sich Gleiche einfach den Platz. Plätze werden
nach Wettkampfart vergeben: 1, 2, 2, 4.

**Unvollständige und abgebrochene Starts** (`RankPolicy`):

- Abbruch durch den Schützen nach dem Kommando „Feuer“ (`dnf` mit `abort_ranked`, Sporthandbuch
  K 1.14 / L 1.12): platziert nach dem bis dahin erzielten Ergebnis wie ein reguläres Ergebnis.
  Den Vergleichsschlüssel rechnet `compute_aborted` (nicht geschossene Serien nach der Regel
  des Modells); ohne vergleichbares Ergebnis bleibt `abort_ranked` aus.
- Alle anderen Abgebrochenen (`dns` nicht angetreten, `dsq` disqualifiziert, `dnf` ohne
  Wertungswert bzw. ohne vergleichbares Ergebnis) bekommen **nie** einen Platz und stehen nie
  vor gewerteten Ergebnissen – gleich, ob ihr Teilergebnis nach der Wertungsrichtung besser
  wäre. `"unranked"` – am Ende ohne Platz aufgeführt (in der Reihenfolge aufgegeben, nicht
  angetreten, disqualifiziert); `"exclude"` – nicht in der Liste.
- `incomplete` (Rohwerte unvollständig, kein Abbruch, etwa ein laufender Start):
  `"normal"` – mit dem bisherigen Ergebnis regulär einsortiert;
  `"last"` – hinter allen regulären Starts, untereinander nach Ergebnis, Plätze laufen weiter;
  `"unranked"` – ohne Platz am Ende (vor den Abgebrochenen); `"exclude"` – nicht in der Liste.

Voreinstellung (`RankPolicy()`): unvollständig hinten, Abgebrochene ohne Platz am Ende.
`RankPolicy.for_list(final=…, include_aborted=…)` liefert die Regel einer Liste: In endgültigen
Listen werden auch unvollständige Ergebnisse nicht platziert.
"""

from collections.abc import Mapping, Sequence
from functools import cmp_to_key
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.scoring.criteria import criterion_text
from app.scoring.definition import Definition, load_definition
from app.scoring.numbers import to_hundredths
from app.scoring.results import ComputedResult
from app.scoring.tiebreak import criterion_capturable, criterion_slots, criterion_values

RankKey = list[int | None]
MAX_SCORE_NOTE = "Höchstergebnis: gleicher Platz"
SHOOTOFF_REASONS = frozenset({"shootoff", "max_score_shootoff"})
AbortReason = Literal["dns", "dnf", "dsq"]
RankGroup = Literal["ranked", "last", "unranked"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Contender(_Frozen):
    """Ein Start in der Rangliste."""

    id: str
    """Start-ID."""
    entry_id: str | None = None
    """Teilnehmer (Anmeldung); fasst Mehrfachstarts zusammen, sonst gilt `id`."""
    attempt: int = 1
    key: RankKey | None = None
    """`rank_key(...)`; darf nur bei DNS/DSQ fehlen."""
    complete: bool = True
    abort_reason: AbortReason | None = None
    abort_ranked: bool = False
    """Nur mit `abort_reason="dnf"`: Abbruch nach „Feuer“ mit vergleichbarem Ergebnis in `key`;
    wird platziert wie ein reguläres Ergebnis (Sporthandbuch K 1.14 / L 1.12)."""

    @property
    def participant(self) -> str:
        return self.entry_id or self.id

    @property
    def scored(self) -> bool:
        """Zählt als Ergebnis: nicht abgebrochen oder platzierbarer Abbruch."""
        return self.abort_reason is None or (self.abort_reason == "dnf" and self.abort_ranked)


AbortedSetting = Literal["unranked", "exclude"]


class RankPolicy(_Frozen):
    incomplete: Literal["normal", "last", "unranked", "exclude"] = "last"
    # Abgebrochene ohne vergleichbares Ergebnis: nie mit Platz (es gibt bewusst keine
    # Einstellung dafür). Ein platzierbarer Abbruch (`abort_ranked`) gilt immer als regulär.
    dnf: AbortedSetting = "unranked"
    dns: AbortedSetting = "unranked"
    dsq: AbortedSetting = "unranked"

    @classmethod
    def for_list(cls, *, final: bool, include_aborted: bool = True) -> RankPolicy:
        """Endgültige Liste (`final`): Unvollständige ohne Platz; sonst (live) hinten.
        `include_aborted=False` lässt abgebrochene Starts ganz weg."""
        aborted: AbortedSetting = "unranked" if include_aborted else "exclude"
        return cls(
            incomplete="unranked" if final else "last", dnf=aborted, dns=aborted, dsq=aborted
        )


TieReason = Literal[
    "missing_data", "manual", "shootoff", "max_score", "max_score_shootoff", "resolved"
]


class TieRules(_Frozen):
    """Gleichstandsregel einer Definition für `rank` (aus `tie_rules(definition)`)."""

    criteria: list[str] = []
    """Gerechnete Kriterien in Reihenfolge (bis `chain_until_place`)."""
    slots: list[str] = []
    """Kriterium je Stelle des Vergleichsschlüssels nach dem Ergebnis (beide Ketten)."""
    manual_from: str | None = None
    """Erstes Kriterium, das die Wertung nicht rechnet; ab dort manuell entscheiden."""
    chain_until_place: int | None = None
    """`gleichstand_bis_platz`: `criteria` gilt nur für Gleiche, die bis zu diesem Platz
    beginnen, danach `criteria_after`."""
    criteria_after: list[str] = []
    """Gerechnete Kriterien von `gleichstand_danach`."""
    manual_from_after: str | None = None
    """Wie `manual_from` für `gleichstand_danach`."""
    shootoff_until: int | None = None
    """`stechen_bis_platz`."""
    max_score_key: int | None = None
    """Höchstergebnis als erster Schlüsselwert (Hundertstel), nur mit
    `hoechstergebnis_gleicher_rang` (gleicher Platz ohne Kette und Stechen) oder
    `stechen_bei_hoechstergebnis` (`max_score_shootoff`)."""
    max_score_shootoff: bool = False
    """`stechen_bei_hoechstergebnis`: Gleiche mit `max_score_key` stechen."""
    uncapturable: list[str] = []
    """Gerechnete Kriterien, die sich bei dieser Definition grundsätzlich nicht erfassen lassen
    (Innenzehner bei Zehntelwertung): Bleiben Starts bis dorthin gleich, ist das „manuell“, nicht
    „Angaben fehlen“."""


class Placement(_Frozen):
    id: str
    place: int | None
    tied: bool
    """Platz wird mit anderen geteilt."""
    tie_unresolved: bool
    """Geteilt, aber nicht entschieden: Angaben fehlen, ein Kriterium ist von Hand zu prüfen
    oder ein Stechen steht aus (`tie_reason`)."""
    group: RankGroup
    tie_reason: TieReason | None = None
    """`missing_data`: für `tie_criterion` fehlen Rohdaten; `manual`: `tie_criterion` rechnet die
    Wertung nicht (nach Sportordnung entscheiden); `shootoff`: Stechen (`stechen_bis_platz`);
    `max_score`: Höchstergebnis erreicht, gleicher Platz nach Regel (DSB-SpO 0.12.1) – das ist
    entschieden (`tie_unresolved` bleibt aus); `max_score_shootoff`: Höchstergebnis erreicht,
    Stechen (`stechen_bei_hoechstergebnis`, DSB-SpO 9.4.3); `resolved`: im Ergebnis gleich,
    aber durch die Gleichstandskette getrennt – `tie_criterion` ist das entscheidende Kriterium
    (nicht geteilt, `tied` und `tie_unresolved` bleiben aus)."""
    tie_criterion: str | None = None
    needs_shootoff: bool = False
    tie_note: str | None = None
    """Hinweis für Listen und Anzeige, z. B. „Ringgleichheit auf Platz 2: Stechen“."""


def rank_key(
    definition: Mapping[str, Any] | Definition, computed: ComputedResult | Mapping[str, Any]
) -> RankKey:
    defn = load_definition(definition)
    result = (
        computed
        if isinstance(computed, ComputedResult)
        else ComputedResult.model_validate(computed)
    )
    if result.model != defn.model.name:
        raise ValueError(
            f"Ergebnis stammt vom Modell „{result.model}“, Definition nutzt „{defn.model.name}“"
        )
    primary = to_hundredths(result.score)
    key: RankKey = [primary if defn.model.direction == "absteigend" else -primary]
    for criterion in defn.tie_criteria:
        key.extend(criterion_values(defn, result, criterion))
    return key


def tie_rules(definition: Mapping[str, Any] | Definition) -> TieRules:
    """Was `rank` über die Gleichstandsregel der Definition wissen muss."""
    defn = load_definition(definition)
    evaluated, manual_from = defn.tie_chain
    after, manual_from_after = defn.tie_chain_after or ([], None)
    criteria = defn.tie_criteria
    slots = [c for c in criteria for _ in range(criterion_slots(defn, c))]
    scoring = defn.scoring
    max_rule = scoring.hoechstergebnis_gleicher_rang or scoring.stechen_bei_hoechstergebnis
    maximum = defn.max_score if max_rule else None
    return TieRules(
        criteria=evaluated,
        slots=slots,
        manual_from=manual_from,
        chain_until_place=scoring.gleichstand_bis_platz,
        criteria_after=after,
        manual_from_after=manual_from_after,
        shootoff_until=scoring.stechen_bis_platz,
        max_score_key=to_hundredths(maximum) if maximum is not None else None,
        max_score_shootoff=bool(scoring.stechen_bei_hoechstergebnis),
        uncapturable=[c for c in criteria if not criterion_capturable(defn, c)],
    )


def rank(
    contenders: Sequence[Contender],
    policy: RankPolicy | None = None,
    rules: TieRules | None = None,
) -> list[Placement]:
    """Platzierungen in Listenreihenfolge (ranked, dann last, dann unranked).

    Mit `rules` (aus `tie_rules(definition)`) zusätzlich: Stechen auf den Plätzen bis
    `stechen_bis_platz` (nur reguläre Starts) und Hinweise, warum ein Gleichstand offen bleibt.
    Ohne `rules` wie bisher (Gleichstand nach dem Schlüssel, `tie_unresolved` bei fehlenden
    Angaben).
    """
    policy = policy or RankPolicy()
    groups: dict[str, list[Contender]] = {"ranked": [], "last": [], "unranked": []}
    for contender in contenders:
        group = _group(contender, policy)
        if group is not None:
            groups[group].append(contender)
    _check_keys([*groups["ranked"], *groups["last"]])

    placements: list[Placement] = []
    next_place = 1
    for group in ("ranked", "last"):
        shootoff = rules.shootoff_until if rules is not None and group == "ranked" else None
        for members, reason, criterion in _tiers(groups[group], rules, next_place, shootoff):
            tied = len(members) > 1
            shown = tied or reason == "resolved"
            placements.extend(
                Placement(
                    id=member.id,
                    place=next_place,
                    tied=tied,
                    tie_unresolved=tied and reason not in (None, "max_score", "resolved"),
                    group=group,
                    tie_reason=reason if shown else None,
                    tie_criterion=criterion if shown else None,
                    needs_shootoff=tied and reason in SHOOTOFF_REASONS,
                    tie_note=_tie_note(reason, criterion, next_place) if shown else None,
                )
                for member in members
            )
            next_place += len(members)
    # Ohne Platz: erst Unvollständige, dann aufgegeben, nicht angetreten, disqualifiziert;
    # innerhalb gleicher Art in der Reihenfolge der Eingabe.
    unranked = sorted(groups["unranked"], key=lambda c: UNRANKED_ORDER[c.abort_reason])
    placements.extend(
        Placement(id=c.id, place=None, tied=False, tie_unresolved=False, group="unranked")
        for c in unranked
    )
    return placements


def best_of(
    contenders: Sequence[Contender],
    rule: Literal["best", "first", "all"],
    policy: RankPolicy | None = None,
) -> list[Contender]:
    """Wählt bei Mehrfachstart je Teilnehmer (`entry_id`) die Starts, die in die Wertung gehen.

    - `all`: jeder Start zählt für sich.
    - `first`: der Start mit der kleinsten `attempt`-Nummer, der ein Ergebnis hat (nicht
      abgebrochen oder platzierbarer Abbruch, `Contender.scored`); gibt es nur Abgebrochene
      ohne Ergebnis, der erste davon, der angetreten ist (sonst der erste).
    - `best`: der Start, der nach `policy` am weitesten vorn stünde; bei Gleichheit der frühere.

    Ein platzierbarer Abbruch zählt wie ein reguläres Ergebnis. Ein abgebrochener Versuch ohne
    Ergebnis wird nie einem gewerteten (oder laufenden) vorgezogen.
    """
    if rule == "all":
        return list(contenders)
    if rule not in ("best", "first"):
        raise ValueError(f"Mehrfachstart-Regel „{rule}“ unbekannt (erlaubt: best, first, all)")
    policy = policy or RankPolicy()
    by_participant: dict[str, list[Contender]] = {}
    for contender in contenders:
        by_participant.setdefault(contender.participant, []).append(contender)

    chosen = []
    for attempts in by_participant.values():
        ordered = sorted(attempts, key=lambda c: c.attempt)
        if rule == "first":
            scored = [c for c in ordered if c.scored]
            started = [c for c in ordered if c.abort_reason != "dns"]
            chosen.append((scored or started or ordered)[0])
        else:
            chosen.append(min(ordered, key=cmp_to_key(lambda a, b: _compare(a, b, policy))))
    return chosen


GROUP_ORDER: dict[RankGroup | None, int] = {"ranked": 0, "last": 1, "unranked": 2, None: 3}
UNRANKED_ORDER: dict[AbortReason | None, int] = {None: 0, "dnf": 1, "dns": 2, "dsq": 3}
GROUP_FOR_SETTING: dict[str, RankGroup] = {
    "normal": "ranked",
    "last": "last",
    "unranked": "unranked",
}


def _group(contender: Contender, policy: RankPolicy) -> RankGroup | None:
    match contender.abort_reason:
        case "dns":
            setting: str = policy.dns
        case "dsq":
            setting = policy.dsq
        case "dnf":
            setting = "normal" if contender.abort_ranked else policy.dnf
        case None:
            setting = "normal" if contender.complete else policy.incomplete
    return GROUP_FOR_SETTING.get(setting)


def _check_keys(contenders: list[Contender]) -> None:
    lengths = set()
    for contender in contenders:
        if contender.key is None or not contender.key or contender.key[0] is None:
            raise ValueError(f"Start {contender.id}: Vergleichsschlüssel fehlt")
        lengths.add(len(contender.key))
    if len(lengths) > 1:
        raise ValueError("Vergleichsschlüssel unterschiedlich lang (verschiedene Definitionen?)")


Tier = tuple[list[Contender], TieReason | None, str | None]
# Kette: je Stelle die Position im Vergleichsschlüssel und das Kriterium (ohne Regel: None).
Chain = list[tuple[int, str | None]]


def _tiers(
    members: list[Contender],
    rules: TieRules | None = None,
    first_place: int = 1,
    shootoff_until: int | None = None,
) -> list[Tier]:
    """Teilt nach dem Ergebnis, dann Gleiche nach der Kette ihres Platzes; liefert Gruppen in
    Rangfolge mit dem Grund, warum eine Gruppe mit mehreren gleich bleibt (None: alle
    Kriterien gleich)."""
    scores = [(member.key or [None])[0] for member in members]
    tiers: list[Tier] = []
    place = first_place
    for score in sorted({s for s in scores if s is not None}, reverse=True):
        same = [m for m, s in zip(members, scores, strict=True) if s == score]
        tiers.extend(_tie_group(same, rules, place, shootoff_until))
        place += len(same)
    return tiers


def _tie_group(
    members: list[Contender],
    rules: TieRules | None,
    first_place: int,
    shootoff_until: int | None,
) -> list[Tier]:
    """Starts mit gleichem Ergebnis, die auf `first_place` beginnen."""
    if len(members) < 2:
        return [(members, None, None)]
    # Höchstergebnis: gleicher Platz (DSB-SpO 0.12.1 Satz 1) bzw. Stechen (9.4.3) – vor dem
    # Stechen bis Platz N und vor der Kette.
    maximum = rules.max_score_key if rules is not None else None
    if maximum is not None and (members[0].key or [None])[0] == maximum:
        shootoff = rules is not None and rules.max_score_shootoff
        return [(members, "max_score_shootoff" if shootoff else "max_score", None)]
    if shootoff_until is not None and first_place <= shootoff_until:
        return [(members, "shootoff", None)]
    chain, manual = _chain(rules, first_place, len(members[0].key or []))
    return _split(members, chain, 0, rules, manual, None)


def _chain(rules: TieRules | None, place: int, length: int) -> tuple[Chain, str | None]:
    """Kette für Gleiche, die auf `place` beginnen: Stellen im Schlüssel und erstes nicht
    gerechnetes Kriterium."""
    if rules is None:
        return [(index, None) for index in range(1, length)], None
    criteria, manual = rules.criteria, rules.manual_from
    if rules.chain_until_place is not None and place > rules.chain_until_place:
        criteria, manual = rules.criteria_after, rules.manual_from_after
    chain: Chain = [
        (index + 1, slot)
        for criterion in criteria
        for index, slot in enumerate(rules.slots)
        if slot == criterion
    ]
    return chain, manual


def _split(
    members: list[Contender],
    chain: Chain,
    depth: int,
    rules: TieRules | None,
    manual: str | None,
    decided_by: str | None,
) -> list[Tier]:
    """Teilt Gleiche rekursiv nach der nächsten Stelle der Kette.

    Ein einzelner Start, den erst ein Kriterium der Kette von Ergebnisgleichen getrennt hat,
    bekommt `resolved` und dieses Kriterium (`decided_by`, das zuletzt trennende)."""
    if len(members) < 2:
        return [(members, "resolved" if decided_by is not None else None, decided_by)]
    if depth == len(chain):
        return [(members, "manual" if manual else None, manual)]
    position, criterion = chain[depth]
    values = [(member.key or [])[position] for member in members]
    present = [value for value in values if value is not None]
    if len(present) < len(values):
        if rules is not None and criterion in rules.uncapturable:
            return [(members, "manual", criterion)]
        return [(members, "missing_data", criterion)]
    distinct = sorted(set(present), reverse=True)
    # Trennt dieses Kriterium, ist es das entscheidende.
    decided = criterion if len(distinct) > 1 else decided_by
    tiers: list[Tier] = []
    for value in distinct:
        same = [m for m, v in zip(members, values, strict=True) if v == value]
        tiers.extend(_split(same, chain, depth + 1, rules, manual, decided))
    return tiers


def max_score_shootoff_note(place: int | None) -> str:
    """Hinweis bei `max_score_shootoff` (DSB-SpO 9.4.3)."""
    return f"Höchstergebnis auf Platz {place}: Stechen"


def _tie_note(reason: TieReason | None, criterion: str | None, place: int) -> str | None:
    """Hinweis ohne Verbandswort; Listen ersetzen ihn durch `ergebnisse.begriffe.tie_note`."""
    match reason:
        case "resolved":
            return f"Ringgleichheit, entschieden nach: {criterion_text(criterion)}"
        case "shootoff":
            return f"Ringgleichheit auf Platz {place}: Stechen"
        case "max_score":
            return MAX_SCORE_NOTE
        case "max_score_shootoff":
            return max_score_shootoff_note(place)
        case "manual":
            return (
                "Gleichstand nach Sportordnung manuell entscheiden "
                f"(nächstes Kriterium: {criterion_text(criterion)})"
            )
        case "missing_data":
            detail = f" für „{criterion_text(criterion)}“" if criterion else ""
            return (
                f"Gleichstand nicht auflösbar: Angaben{detail} fehlen (z. B. Seriensumme statt "
                "Einzelschüssen); nach Sportordnung manuell entscheiden"
            )
    return None


def _compare(a: Contender, b: Contender, policy: RankPolicy) -> int:
    """< 0, wenn `a` vor `b` stünde (für `best_of`)."""
    # Abgebrochene stehen hinter allem, was gewertet wird oder noch läuft – auch wenn die
    # Regel sie ganz weglässt.
    aborted_a, aborted_b = not a.scored, not b.scored
    if aborted_a != aborted_b:
        return 1 if aborted_a else -1
    group_a, group_b = GROUP_ORDER[_group(a, policy)], GROUP_ORDER[_group(b, policy)]
    if group_a != group_b:
        return group_a - group_b
    if group_a >= GROUP_ORDER["unranked"]:
        # Ohne Platz zählt das Teilergebnis nicht: der frühere Versuch.
        return a.attempt - b.attempt
    for value_a, value_b in zip(a.key or [], b.key or [], strict=False):
        if value_a is None or value_b is None:
            break
        if value_a != value_b:
            return -1 if value_a > value_b else 1
    return a.attempt - b.attempt
