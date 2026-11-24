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
- `letzte_serie_rueckwaerts`: Ringe der letzten Zehnerserie, dann in 10-Schuss-Blöcken
  rückwärts über alle gewerteten Schüsse aller Abschnitte in ihrer Reihenfolge (DSB-SpO 0.12.1
  Nr. 1; Auflage 9.4.1 ebenso), unabhängig davon, wie lang die Serien der Disziplin sind.
  Einzelschüsse werden direkt in Blöcke geteilt; Seriensummen nur, wenn sie genau in einen Block
  fallen (10er-Serien direkt, 5er-Serien paarweise vom Ende her), sonst fehlen die Angaben.
  *Annahme* (die SpO regelt es nicht): Ist die Schusszahl kein Vielfaches von 10, wird vom Ende
  her geblockt, der vorderste Block ist kürzer. Ausnahme: Zählen alle Abschnitte nur Treffer
  (Wurfscheibe, `ringwerte` höchstens 1), gilt die Serie, wie sie definiert ist (DSB-SpO 3.9.1.2:
  letzte Serie zu 25 Wurfscheiben, dann rückwärts).
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
# `letzte_serie_rueckwaerts`: Schüsse je Vergleichsblock (DSB-SpO 0.12.1: „Zehnerserie“).
BLOCK_SHOTS = 10
COUNTED_VALUE = {"elfer": 11, "neuner": 9, "sechser": 6, "fuenfer": 5}

Values = list[int | None]

# Kriterien, die Einzelschüsse brauchen: aus Seriensummen nie zu rechnen.
SHOT_CRITERIA = frozenset(
    {
        "neuner_abwaerts",
        "schuesse_rueckwaerts",
        "mehr_treffer",
        "elfer",
        "neuner",
        "sechser",
        "fuenfer",
    }
)


def criterion_capturable(defn: Definition, criterion: str, capture_mode: str | None = None) -> bool:
    """Lässt sich das Kriterium bei dieser Definition (und Erfassungsart) überhaupt erfassen?

    Nein heißt: Die Angaben fehlen nicht, weil jemand sie nicht eingegeben hat, sondern weil es
    sie hier grundsätzlich nicht gibt – ein Gleichstand ist dort nach Sportordnung manuell zu
    entscheiden (wie ein Kriterium, das die Wertung nicht rechnet):

    - `innenzehner` bei Zehntelwertung (kein „X“), `zehner`/`innenzehner` bei reiner
      Trefferzählung (Wurfscheibe: Werte 0/1);
    - nur mit `capture_mode="series"`: Kriterien, die Einzelschüsse brauchen, und
      `letzte_serie_rueckwaerts`, wenn die Serien keine 10-Schuss-Blöcke ergeben.
    """
    if criterion == "innenzehner" and defn.tenths:
        return False
    if criterion in ("zehner", "innenzehner") and defn.hits_only:
        return False
    if capture_mode == "series":
        if criterion in SHOT_CRITERIA:
            return False
        if criterion == "letzte_serie_rueckwaerts" and not series_sums_fit_blocks(defn):
            return False
    return True


def criterion_slots(defn: Definition, criterion: str) -> int:
    """Anzahl Vergleichswerte des Kriteriums (hängt nur von der Definition ab)."""
    match criterion:
        case "neuner_abwaerts":
            return len(NINES_DOWN)
        case "letzte_serie_rueckwaerts":
            if defn.hits_only:
                return sum(len(plan.counted_series) for plan in defn.sections if plan.rings)
            return -(-_total_shots(defn) // BLOCK_SHOTS)
        case "schuesse_rueckwaerts":
            return _total_shots(defn)
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
            if defn.hits_only:
                series = _counted_series(result)
                return [_points(s.rings if s.captured else None) for s in reversed(series)]
            return _blocks_backwards(result, slots)
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


def _total_shots(defn: Definition) -> int:
    return sum(plan.shots_expected for plan in defn.sections if plan.rings)


def series_sums_fit_blocks(defn: Definition) -> bool:
    """Lässt sich `letzte_serie_rueckwaerts` aus Seriensummen rechnen (jede gewertete Serie
    liegt ganz in einem 10-Schuss-Block)? Bei reiner Trefferzählung immer (Serie = Block)."""
    if defn.hits_only:
        return True
    counts = [
        plan.shots_per_series or 0
        for plan in defn.sections
        if plan.rings
        for _ in plan.counted_series
    ]
    total = sum(counts)
    position = 0
    for count in counts:
        if (
            count
            and (total - 1 - position) // BLOCK_SHOTS != (total - position - count) // BLOCK_SHOTS
        ):
            return False
        position += count
    return True


def _blocks_backwards(result: ComputedResult, slots: int) -> Values:
    """Summe je 10-Schuss-Block, vom letzten Block rückwärts (Länge `slots`).

    Jede gewertete Serie belegt ihre Schussplätze in der Reihenfolge der Abschnitte. Mit
    Einzelschüssen zählt jeder Schuss in seinem Block; fehlt ein Schuss (Zwischenstand), fehlt
    die Summe seines Blocks. Eine Seriensumme zählt nur, wenn die Serie ganz in einem Block
    liegt; sonst fehlen die Summen aller Blöcke, die sie berührt."""
    series = _counted_series(result)
    total = sum(s.shots_expected for s in series)
    if -(-total // BLOCK_SHOTS) != slots:
        return [None] * slots  # Ergebnis passt nicht zur Definition
    # Blöcke vom Ende her: Block 0 ist der letzte; der vorderste darf kürzer sein (Annahme).
    sums: list[Decimal | None] = [Decimal(0)] * slots

    def block_of(position: int) -> int:
        return (total - 1 - position) // BLOCK_SHOTS

    position = 0
    for item in series:
        count = item.shots_expected
        if count == 0:
            continue
        first, last = block_of(position), block_of(position + count - 1)
        if not item.captured:
            for block in range(last, first + 1):
                sums[block] = None
        elif item.shot_values is not None:
            values = list(item.shot_values)
            for offset in range(count):
                block = block_of(position + offset)
                current = sums[block]
                if offset >= len(values) or current is None:
                    sums[block] = None
                else:
                    sums[block] = current + Decimal(values[offset])
        elif first != last or item.rings is None:
            for block in range(last, first + 1):
                sums[block] = None
        else:
            current = sums[first]
            sums[first] = None if current is None else current + Decimal(item.rings)
        position += count
    return [_points(value) for value in sums]


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
