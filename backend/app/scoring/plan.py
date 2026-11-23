"""Aus einem Abschnitt abgeleitet: was je Serie erfasst wird und welche Grenzen gelten.

Die Ableitung ist für alle Modelle gleich; welche Kombinationen ein Modell zulässt, prüft das
Modell selbst (`ScoringModel.check_section`).

- `schuss_je_serie` → Ringe je Schuss (bzw. Seriensumme)
- `zeit_wird_gemessen` → Zeit je Serie, oder eine Gesamtzeit für den Abschnitt, wenn er
  `sollzeit_s` oder `max_gesamtzeit_s` hat (Mehrdistanz-Parcours)
- `zuschlag_je_stehender_scheibe_s` → stehende Scheiben je Serie (höchstens `ziele_je_serie`)
- `ringwerte` → erlaubte Ringwerte je Schuss (sonst 0–10 und „X“ als Innenzehner); Werte über
  10 sind erlaubt (Bogen 3D: 11)
- `ringwerte` mit `ziele_je_serie`, aber ohne `schuss_je_serie` (Wurfscheibe: höchstens zwei
  Schuss je Scheibe) → ein Wert je Ziel statt je Schuss (`per_target`, Treffer 1/0)
- `zehntelwertung` (Wertung) → je Schuss 0 oder 1,0–10,9 als `Decimal`; „X“ gibt es nicht
- `serien_gewertet` → nur die ersten N Serien zählen, die übrigen sind „gestrichen“
- `trefferaufnahme_nach` → Kennzeichen je Serie, ohne Einfluss auf die Wertung
- `zeit_bei_abbruch_s`, `zuschlag_stoerung_vor_erstem_schuss_s` → feste Serienzeit bei Abbruch
  bzw. Störung (siehe `status.py`)
"""

from dataclasses import dataclass
from decimal import Decimal

from app.scoring.numbers import seconds_to_cs
from app.scoring.spec import PositionSpec, SectionSpec

MAX_RING = 10
INNER_TEN = "X"
DEFAULT_RING_VALUES: tuple[int | str, ...] = (INNER_TEN, *range(MAX_RING, -1, -1))
# Zehntelwertung: 0 oder MIN_TENTHS bis MAX_TENTHS.
MIN_TENTHS = Decimal("1.0")
MAX_TENTHS = Decimal("10.9")
# Bei Zehntelwertung höchster Wert eines Schusses unter 10,0 (für Plausibilität der Summe).
MAX_TENTHS_BELOW_TEN = Decimal("9.9")

Shot = int | str | Decimal
"""Ein erfasster Schuss: Ringwert, „X“ (Innenzehner) oder bei Zehntelwertung `Decimal`."""


def ring_value(shot: Shot) -> int | Decimal:
    """Zählwert eines Schusses; der Innenzehner zählt 10, Zehntel bleiben `Decimal`."""
    if shot == INNER_TEN:
        return MAX_RING
    if isinstance(shot, Decimal):
        return shot
    return int(shot)


def ring_class(shot: Shot) -> int:
    """Ganzer Ring eines Schusses (10,7 → 10; „X“ → 10) für Zählungen wie Neuner abwärts."""
    return int(ring_value(shot))


@dataclass(frozen=True)
class SeriesPlan:
    index: int
    shots: int | None
    fixed_time_s: Decimal | None
    max_time_s: Decimal | None
    max_time_cs: int | None
    distance_m: Decimal | None
    position: PositionSpec | None
    struck: bool
    """Gestrichen: wird erfasst und angezeigt, aber nicht gewertet (`serien_gewertet`)."""
    scoring_break_after: bool
    """Nach dieser Serie findet eine Trefferaufnahme statt (`trefferaufnahme_nach`)."""

    @property
    def number(self) -> int:
        return self.index + 1


@dataclass(frozen=True)
class SectionPlan:
    spec: SectionSpec
    series: tuple[SeriesPlan, ...]
    penalty_cs: int | None
    target_time_cs: int | None
    max_total_cs: int | None
    abort_time_cs: int | None
    malfunction_penalty_cs: int | None
    tenths: bool = False
    """Zehntelwertung (`scoring.zehntelwertung`)."""

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def per_target(self) -> bool:
        """Ein Wert je Ziel statt je Schuss (`ringwerte` + `ziele_je_serie`, ohne
        `schuss_je_serie`; Wurfscheibe mit bis zu zwei Schuss je Scheibe)."""
        spec = self.spec
        return (
            spec.schuss_je_serie is None
            and spec.ringwerte is not None
            and spec.ziele_je_serie is not None
        )

    @property
    def shots_per_series(self) -> int | None:
        """Erfasste Werte je Serie: Schüsse, bzw. Ziele bei `per_target`."""
        if self.per_target:
            return self.spec.ziele_je_serie
        return self.spec.schuss_je_serie

    @property
    def rings(self) -> bool:
        return self.shots_per_series is not None

    @property
    def section_time(self) -> bool:
        return bool(self.spec.zeit_wird_gemessen) and (
            self.spec.sollzeit_s is not None or self.spec.max_gesamtzeit_s is not None
        )

    @property
    def series_time(self) -> bool:
        return bool(self.spec.zeit_wird_gemessen) and not self.section_time

    @property
    def standing(self) -> bool:
        return self.spec.zuschlag_je_stehender_scheibe_s is not None

    @property
    def targets(self) -> int | None:
        return self.spec.ziele_je_serie

    @property
    def counted_series(self) -> tuple[SeriesPlan, ...]:
        return tuple(series for series in self.series if not series.struck)

    @property
    def shots_expected(self) -> int:
        """Schüsse der gewerteten Serien."""
        return (self.shots_per_series or 0) * len(self.counted_series)

    @property
    def ring_values(self) -> tuple[int | str, ...]:
        """Erlaubte Werte je Schuss; bei Zehntelwertung leer (Bereich statt Liste)."""
        if self.tenths:
            return ()
        return tuple(self.spec.ringwerte) if self.spec.ringwerte else DEFAULT_RING_VALUES

    @property
    def max_ring(self) -> int | Decimal:
        if self.tenths:
            return MAX_TENTHS
        return max(ring_value(value) for value in self.ring_values)

    @property
    def max_rings(self) -> int | Decimal | None:
        return self.shots_expected * self.max_ring if self.rings else None


def build_section_plan(
    spec: SectionSpec, *, tenths: bool = False
) -> tuple[SectionPlan | None, list[str]]:
    """Leitet den Plan ab; liefert stattdessen Probleme, wenn die Angaben sich widersprechen."""
    problems: list[str] = []
    if tenths and spec.ringwerte is not None:
        problems.append("ringwerte passt nicht zu zehntelwertung (Werte 0 und 1,0 bis 10,9)")
    if spec.schuss_je_serie is not None and spec.max_schuss_je_serie is not None:
        problems.append("schuss_je_serie und max_schuss_je_serie schließen sich aus")
    if spec.zeit_je_serie_s is not None and spec.zeiten_s is not None:
        problems.append("zeit_je_serie_s und zeiten_s schließen sich aus")
    if spec.zuschlag_je_stehender_scheibe_s is not None and spec.ziele_je_serie is None:
        problems.append("zuschlag_je_stehender_scheibe_s braucht ziele_je_serie")
    if not spec.zeit_wird_gemessen:
        for name in ("sollzeit_s", "max_gesamtzeit_s", "max_zeit_je_serie_s"):
            if getattr(spec, name) is not None:
                problems.append(f"{name} braucht zeit_wird_gemessen: true")
    if (
        spec.zeit_wird_gemessen
        and spec.max_zeit_je_serie_s is not None
        and (spec.sollzeit_s is not None or spec.max_gesamtzeit_s is not None)
    ):
        problems.append(
            "max_zeit_je_serie_s passt nicht zu einer Gesamtzeit (sollzeit_s/max_gesamtzeit_s)"
        )
    if spec.ringwerte is not None and spec.schuss_je_serie is None and spec.ziele_je_serie is None:
        problems.append("ringwerte braucht schuss_je_serie (oder ziele_je_serie: Wert je Ziel)")
    if (
        spec.ringwerte is not None
        and spec.schuss_je_serie is None
        and spec.zuschlag_je_stehender_scheibe_s is not None
    ):
        problems.append(
            "ringwerte braucht schuss_je_serie (ein Wert je Ziel passt nicht zu "
            "zuschlag_je_stehender_scheibe_s)"
        )
    if spec.zeit_bei_abbruch_s is not None and not spec.zeit_wird_gemessen:
        problems.append("zeit_bei_abbruch_s braucht zeit_wird_gemessen: true")
    if spec.zuschlag_stoerung_vor_erstem_schuss_s is not None and spec.zeit_bei_abbruch_s is None:
        problems.append("zuschlag_stoerung_vor_erstem_schuss_s braucht zeit_bei_abbruch_s")

    try:
        penalty_cs = _cs(spec.zuschlag_je_stehender_scheibe_s)
        target_time_cs = _cs(spec.sollzeit_s)
        max_total_cs = _cs(spec.max_gesamtzeit_s)
        max_time_cs = _cs(spec.max_zeit_je_serie_s)
        abort_time_cs = _cs(spec.zeit_bei_abbruch_s)
        malfunction_penalty_cs = _cs(spec.zuschlag_stoerung_vor_erstem_schuss_s)
    except ValueError as error:
        problems.append(str(error))
    if problems:
        return None, problems

    per_target = spec.schuss_je_serie is None and spec.ringwerte is not None
    series = tuple(
        SeriesPlan(
            index=index,
            shots=spec.ziele_je_serie if per_target else spec.schuss_je_serie,
            fixed_time_s=spec.zeiten_s[index] if spec.zeiten_s else spec.zeit_je_serie_s,
            max_time_s=spec.max_zeit_je_serie_s,
            max_time_cs=max_time_cs,
            distance_m=_distance(spec, index),
            position=spec.positionen[index] if spec.positionen else None,
            struck=spec.serien_gewertet is not None and index >= spec.serien_gewertet,
            scoring_break_after=index + 1 in (spec.trefferaufnahme_nach or []),
        )
        for index in range(spec.serien)
    )
    plan = SectionPlan(
        spec=spec,
        series=series,
        penalty_cs=penalty_cs,
        target_time_cs=target_time_cs,
        max_total_cs=max_total_cs,
        abort_time_cs=abort_time_cs,
        malfunction_penalty_cs=malfunction_penalty_cs,
        tenths=tenths,
    )
    return plan, []


def _distance(spec: SectionSpec, index: int) -> Decimal | None:
    if spec.distanzen_m:
        return spec.distanzen_m[index]
    if spec.positionen:
        return spec.positionen[index].distanz_m
    return None


def _cs(seconds: Decimal | None) -> int | None:
    return None if seconds is None else seconds_to_cs(seconds)
