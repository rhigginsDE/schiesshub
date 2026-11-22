"""Rangfolge, Gleichstand und Mehrfachstart.

**Vergleichsschlüssel** (`rank_key`): eine Liste ganzer Zahlen, bei der überall *größer besser*
ist. Erster Eintrag ist das Ergebnis in Hundertsteln (bei „aufsteigend“ negiert), danach je
Gleichstandskriterium der Definition ein Wert (`neuner_abwaerts` ergibt neun Werte: Anzahl
Neuner, Achter, …, Einer; `parcours_zeit` die negierte Parcourszeit in cs). Fehlt die Angabe für
ein Kriterium (Seriensumme ohne Zehner), steht dort `None`.

**Gleichstand** (`rank`): Starts mit gleichem Ergebnis werden Kriterium für Kriterium getrennt.
Fehlt bei einem der noch Gleichen der Wert des nächsten Kriteriums, endet die Trennung dort: Die
Gruppe teilt sich den Platz und wird als „nicht auflösbar“ markiert (`tie_unresolved`).
Ohne Gleichstandsregel (z. B. Fallscheibe) teilen sich Gleiche einfach den Platz. Plätze werden
nach Wettkampfart vergeben: 1, 2, 2, 4.

**Unvollständige und abgebrochene Starts** (`RankPolicy`):

- Abgebrochene Starts (`dns` nicht angetreten, `dnf` aufgegeben, `dsq` disqualifiziert) bekommen
  **nie** einen Platz und stehen nie vor gewerteten Ergebnissen – gleich, ob ihr Teilergebnis
  nach der Wertungsrichtung besser wäre. `"unranked"` – am Ende ohne Platz aufgeführt (in der
  Reihenfolge aufgegeben, nicht angetreten, disqualifiziert); `"exclude"` – nicht in der Liste.
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

from app.scoring.definition import Definition, load_definition
from app.scoring.numbers import to_hundredths
from app.scoring.results import ComputedResult

RankKey = list[int | None]
AbortReason = Literal["dns", "dnf", "dsq"]
RankGroup = Literal["ranked", "last", "unranked"]

NINES_DOWN = range(9, 0, -1)


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

    @property
    def participant(self) -> str:
        return self.entry_id or self.id


AbortedSetting = Literal["unranked", "exclude"]


class RankPolicy(_Frozen):
    incomplete: Literal["normal", "last", "unranked", "exclude"] = "last"
    # Abgebrochene: nie mit Platz (es gibt bewusst keine Einstellung dafür).
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


class Placement(_Frozen):
    id: str
    place: int | None
    tied: bool
    """Platz wird mit anderen geteilt."""
    tie_unresolved: bool
    """Geteilt, weil für ein Gleichstandskriterium Angaben fehlen."""
    group: RankGroup


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
    for criterion in defn.tie_breakers:
        match criterion:
            case "zehner":
                key.append(result.tens)
            case "innenzehner":
                key.append(result.inner_tens)
            case "neuner_abwaerts":
                counts = result.ring_counts
                key.extend(None if counts is None else counts[value] for value in NINES_DOWN)
            case "parcours_zeit":
                time = result.parcours_time_cs
                key.append(None if time is None else -time)
            case _:
                raise ValueError(f"Gleichstandskriterium „{criterion}“ ohne Vergleichswert")
    return key


def rank(contenders: Sequence[Contender], policy: RankPolicy | None = None) -> list[Placement]:
    """Platzierungen in Listenreihenfolge (ranked, dann last, dann unranked)."""
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
        for members, unresolved in _tiers(groups[group], 0):
            placements.extend(
                Placement(
                    id=member.id,
                    place=next_place,
                    tied=len(members) > 1,
                    tie_unresolved=unresolved,
                    group=group,
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
    - `first`: der Start mit der kleinsten `attempt`-Nummer, der nicht abgebrochen ist; gibt es
      nur abgebrochene, der erste davon, der angetreten ist (sonst der erste).
    - `best`: der Start, der nach `policy` am weitesten vorn stünde; bei Gleichheit der frühere.

    Ein abgebrochener Versuch wird nie einem gewerteten (oder laufenden) vorgezogen.
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
            scored = [c for c in ordered if c.abort_reason is None]
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
            setting = policy.dnf
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


def _tiers(members: list[Contender], level: int) -> list[tuple[list[Contender], bool]]:
    """Teilt Gleiche rekursiv nach dem nächsten Kriterium; liefert Gruppen in Rangfolge."""
    if len(members) < 2 or level == len(members[0].key or []):
        return [(members, False)] if members else []
    values = [(member.key or [])[level] for member in members]
    present = [value for value in values if value is not None]
    if len(present) < len(values):
        return [(members, True)]
    tiers: list[tuple[list[Contender], bool]] = []
    for value in sorted(set(present), reverse=True):
        same = [m for m, v in zip(members, values, strict=True) if v == value]
        tiers.extend(_tiers(same, level + 1))
    return tiers


def _compare(a: Contender, b: Contender, policy: RankPolicy) -> int:
    """< 0, wenn `a` vor `b` stünde (für `best_of`)."""
    # Abgebrochene stehen hinter allem, was gewertet wird oder noch läuft – auch wenn die
    # Regel sie ganz weglässt.
    aborted_a, aborted_b = a.abort_reason is not None, b.abort_reason is not None
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
