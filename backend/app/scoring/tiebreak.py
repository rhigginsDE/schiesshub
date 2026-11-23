"""Vergleichswerte der Gleichstandskriterien, die die Wertung selbst rechnet.

Jedes Kriterium liefert eine feste Anzahl ganzer Zahlen (`criterion_slots`), überall gilt
*größer ist besser*. `None` heißt: Für diesen Start fehlen die Angaben (z. B. Seriensumme statt
Einzelschüssen) – die Rangliste trennt dann nicht weiter, statt zu raten (`ranking.py`).

Kriterien (in Klammern, was dafür erfasst sein muss):

- `zehner`: Anzahl Zehner mit Innenzehnern; bei Zehntelwertung Schüsse ab 10,0 (Einzelschüsse
  oder Seriensumme mit Zehnern)
- `innenzehner`: Anzahl „X“ (wie oben; bei Zehntelwertung nie vorhanden → manuell)
- `neuner_abwaerts`: Anzahl Neuner, dann Achter … Einer; bei Zehntelwertung zählt der ganze
  Ring, 9,8 ist ein Neuner (Einzelschüsse)
- `elfer`, `neuner`, `sechser`, `fuenfer`: Anzahl Schüsse mit diesem ganzen Ring (Einzelschüsse)
- `parcours_zeit`: niedrigere Parcourszeit (Gesamtzeiten)
- `letzte_serie_rueckwaerts`: Ringe der letzten gewerteten Serie, dann der vorletzten … über
  alle Abschnitte in ihrer Reihenfolge, so wie die Serien definiert sind (Serienwerte)
- `schuesse_rueckwaerts`: letzter Schuss, dann vorletzter … (Einzelschüsse aller Serien)
- `ergebnis_zweite_haelfte`: Ringe der zweiten Hälfte der gewerteten Serien; bei ungerader
  Serienzahl die zweite Hälfte der Schüsse (Serienwerte bzw. Einzelschüsse)
- `mehr_treffer`: Anzahl Schüsse mit Wert über 0 (Einzelschüsse)
- `zehntel_gesamt`: Ringsumme in Zehnteln (nur mit Zehntelwertung, sonst fehlen die Zehntel)
"""

from decimal import Decimal

from app.scoring.definition import Definition
from app.scoring.numbers import to_hundredths
from app.scoring.results import ComputedResult, SeriesResult

NINES_DOWN = range(9, 0, -1)
COUNTED_VALUE = {"elfer": 11, "neuner": 9, "sechser": 6, "fuenfer": 5}

Values = list[int | None]


def criterion_slots(defn: Definition, criterion: str) -> int:
    """Anzahl Vergleichswerte des Kriteriums (hängt nur von der Definition ab)."""
    match criterion:
        case "neuner_abwaerts":
            return len(NINES_DOWN)
        case "letzte_serie_rueckwaerts":
            return sum(len(plan.counted_series) for plan in defn.sections if plan.rings)
        case "schuesse_rueckwaerts":
            return sum(plan.shots_expected for plan in defn.sections if plan.rings)
        case _:
            return 1


def criterion_values(defn: Definition, result: ComputedResult, criterion: str) -> Values:
    slots = criterion_slots(defn, criterion)
    match criterion:
        case "zehner":
            return [result.tens]
        case "innenzehner":
            return [result.inner_tens]
        case "neuner_abwaerts":
            counts = result.ring_counts
            return [None if counts is None else counts.get(value, 0) for value in NINES_DOWN]
        case "elfer" | "neuner" | "sechser" | "fuenfer":
            counts = result.ring_counts
            return [None if counts is None else counts.get(COUNTED_VALUE[criterion], 0)]
        case "parcours_zeit":
            time = result.parcours_time_cs
            return [None if time is None else -time]
        case "letzte_serie_rueckwaerts":
            series = _counted_series(result)
            return [_points(s.rings if s.captured else None) for s in reversed(series)]
        case "schuesse_rueckwaerts":
            shots = _all_shots(result)
            if shots is None:
                return [None] * slots
            values: Values = [_points(value) for value in reversed(shots)]
            return [None] * (slots - len(values)) + values if len(values) < slots else values
        case "ergebnis_zweite_haelfte":
            return [_second_half(result)]
        case "mehr_treffer":
            return [result.hits]
        case "zehntel_gesamt":
            if not defn.tenths or result.rings is None:
                return [None]
            return [_points(result.rings)]
    raise ValueError(f"Gleichstandskriterium „{criterion}“ ohne Vergleichswert")


def _points(value: Decimal | int | None) -> int | None:
    """Ringe als ganze Zahl in Hundertsteln (auch Zehntel bleiben exakt)."""
    return None if value is None else to_hundredths(Decimal(value))


def _counted_series(result: ComputedResult) -> list[SeriesResult]:
    return [
        series
        for section in result.sections
        if section.rings is not None
        for series in section.series
        if not series.struck
    ]


def _all_shots(result: ComputedResult) -> list[Decimal | int] | None:
    """Alle gewerteten Schüsse in Reihenfolge; None, sobald eine Serie als Summe vorliegt.
    Fehlende Schüsse (Zwischenstand) fehlen einfach am Ende ihrer Serie."""
    shots: list[Decimal | int] = []
    for series in _counted_series(result):
        if series.captured and series.shot_values is None:
            return None
        shots.extend(series.shot_values or [])
    return shots


def _second_half(result: ComputedResult) -> int | None:
    series = _counted_series(result)
    if len(series) % 2 == 0 and series:
        half = series[len(series) // 2 :]
        if any(s.rings is None or not s.captured for s in half):
            return None
        return _points(sum((Decimal(s.rings or 0) for s in half), Decimal(0)))
    expected = sum(s.shots_expected for s in series)
    shots = _all_shots(result)
    if shots is None or expected % 2 or len(shots) < expected:
        return None
    return _points(sum((Decimal(v) for v in shots[expected // 2 :]), Decimal(0)))
