"""Ergebnis eines Starts aus Definition und Rohwerten rechnen."""

from collections import Counter
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from app.scoring.definition import Definition, check_capture_mode, load_definition
from app.scoring.errors import InvalidRawError, Issue
from app.scoring.numbers import format_cs, format_number, format_seconds_value, plural, to_tenths
from app.scoring.plan import (
    INNER_TEN,
    MAX_RING,
    SectionPlan,
    SeriesPlan,
    Shot,
    ring_class,
    ring_value,
)
from app.scoring.raw import RawSeries, read_raw, series_label
from app.scoring.registry import SectionInput, SectionScore
from app.scoring.results import ComputedResult, Progress, SectionResult, SeriesResult
from app.scoring.status import FIXED_TIME, MALFUNCTION, NORMAL, STATUS_LABELS, UNFINISHED
from app.scoring.tiebreak import criterion_capturable, criterion_values

TIME_LIMIT_NOTE = (
    "Der Katalog legt dafür keine Wertung fest; die Zeit geht unverändert ein – "
    "bitte nach Regelwerk prüfen."
)
TIME_LIMIT_STATUS_NOTE = (
    "Wurde die Serie beim Zeitlimit abgebrochen, den Status „Zeitlimit erreicht“ wählen; "
    "sonst geht die gemessene Zeit unverändert ein."
)


def compute(
    definition: Mapping[str, Any] | Definition, capture_mode: str, raw: object
) -> ComputedResult:
    """Rechnet Zwischen- oder Endstand. Unvollständige Rohwerte sind erlaubt (`complete=False`);
    fehlerhafte Rohwerte lösen `InvalidRawError` mit allen Fehlern aus."""
    check_capture_mode(capture_mode)
    defn = load_definition(definition)
    sections_raw, issues = read_raw(defn, raw, partial=True)
    if issues:
        raise InvalidRawError(issues)

    steps: list[str] = []
    warnings: list[Issue] = []
    inputs: list[SectionInput] = []
    all_series: list[list[SeriesResult]] = []
    tally = _Tally()
    for plan in defn.sections:
        raw_section = sections_raw[plan.id]
        path = f"sections.{plan.id}"
        series_results = []
        shown_results = []
        for series_plan in plan.series:
            raw_series = raw_section.series[series_plan.index]
            result = _series_result(plan, series_plan, raw_series)
            shown_results.append(result)
            if series_plan.struck:
                continue  # gestrichen: Einzelwert nur zur Anzeige
            series_results.append(result)
            tally.add(plan, raw_series, result)
            label = series_label(defn, plan, series_plan)
            if result.captured and raw_series is not None:
                steps.append(f"{label}: {_series_text(plan, raw_series, result)}")
            limit = series_plan.max_time_cs
            if (
                limit is not None
                and series_plan.max_time_s is not None
                and result.status == NORMAL
                and result.time_cs is not None
                and result.time_cs > limit
            ):
                note = (
                    TIME_LIMIT_STATUS_NOTE
                    if "time_limit" in defn.series_statuses(plan)
                    else TIME_LIMIT_NOTE
                )
                warnings.append(
                    Issue(
                        path=f"{path}.series[{series_plan.index}].time_cs",
                        message=f"{label}: {format_cs(result.time_cs)} liegt über dem Zeitlimit "
                        f"von {format_seconds_value(series_plan.max_time_s)} s. {note}",
                    )
                )
        struck = [s.number for s in plan.series if s.struck]
        if struck:
            prefix = f"{plan.name}, " if defn.multi_section else ""
            steps.append(f"{prefix}{_series_numbers(struck)} gestrichen (nicht gewertet)")
        if (
            plan.max_total_cs is not None
            and raw_section.time_cs is not None
            and raw_section.time_cs > plan.max_total_cs
            and plan.spec.max_gesamtzeit_s is not None
        ):
            warnings.append(
                Issue(
                    path=f"{path}.time_cs",
                    message=f"{plan.name}: Gesamtzeit {format_cs(raw_section.time_cs)} liegt über "
                    f"der Abbruchzeit von {format_seconds_value(plan.spec.max_gesamtzeit_s)} s. "
                    f"{TIME_LIMIT_NOTE}",
                )
            )
        inputs.append(
            SectionInput(
                plan=plan,
                series=series_results,
                time_cs=raw_section.time_cs,
                label=plan.name if defn.multi_section else "",
            )
        )
        all_series.append(shown_results)

    evaluation = defn.model.evaluate(defn.scoring, inputs)
    steps.extend(evaluation.steps)
    sections = [
        _section_result(section, score, shown)
        for section, score, shown in zip(inputs, evaluation.sections, all_series, strict=True)
    ]
    parcours = [s for s in inputs if s.plan.section_time]
    parcours_time = (
        sum(s.time_cs for s in parcours if s.time_cs is not None)
        if parcours and all(s.time_cs is not None for s in parcours)
        else None
    )
    deductions = [s.deduction for s in evaluation.sections if s.deduction is not None]
    complete = all(s.complete for s in sections)
    result = ComputedResult(
        model=defn.model.name,
        direction=defn.model.direction,
        unit=defn.unit,
        score=evaluation.score,
        score_text=f"{format_number(evaluation.score)} {defn.unit}",
        complete=complete,
        rings=tally.rings,
        # Reine Trefferzählung (Wurfscheibe): Zehner gibt es nicht.
        tens=None if defn.hits_only else tally.tens,
        inner_tens=None if defn.hits_only else tally.inner_tens,
        ring_counts=tally.ring_counts,
        time_cs=tally.time_cs(inputs),
        penalty_cs=tally.penalty_cs,
        deduction=sum(deductions) if deductions else None,
        parcours_time_cs=parcours_time,
        tie_breakers_missing=[],
        sections=sections,
        progress=Progress(
            shots_entered=sum(s.shots_entered for sec in inputs for s in sec.series),
            shots_expected=sum(plan.shots_expected for plan in defn.sections),
            series_complete=sum(s.complete for sec in inputs for s in sec.series),
            series_expected=sum(len(plan.counted_series) for plan in defn.sections),
            section_times_entered=sum(s.time_cs is not None for s in parcours),
            section_times_expected=len(parcours),
        ),
        steps=steps,
        warnings=warnings,
        decimals=1 if defn.tenths else 0,
        hits=tally.hits,
    )
    # Gerechnete Gleichstandskriterien, für die Angaben fehlen (z. B. Seriensumme ohne Zehner).
    # Was sich hier grundsätzlich nicht erfassen lässt (Innenzehner bei Zehntelwertung, Neuner
    # abwärts bei Seriensumme), „fehlt“ nicht: Dort entscheidet ein Mensch (`tie_rules`).
    evaluated, _ = defn.tie_chain
    missing = [
        c
        for c in evaluated
        if criterion_capturable(defn, c, capture_mode) and None in criterion_values(defn, result, c)
    ]
    return result.model_copy(update={"tie_breakers_missing": missing})


def _series_result(
    plan: SectionPlan, series_plan: SeriesPlan, raw: RawSeries | None
) -> SeriesResult:
    expected = series_plan.shots or 0
    if raw is None:
        return SeriesResult(
            number=series_plan.number,
            struck=series_plan.struck,
            status=NORMAL,
            captured=False,
            complete=False,
            shots_entered=0,
            shots_expected=expected,
            rings=None,
            tens=None,
            inner_tens=None,
            measured_time_cs=None,
            time_cs=None,
            standing=None,
            penalty_cs=None,
            total_cs=None,
        )
    rings: int | Decimal | None = None
    tens = inner_tens = None
    shot_values: list[int | Decimal] | None = None
    entered = 0
    if plan.rings and raw.shots is not None:
        shot_values = [ring_value(shot) for shot in raw.shots]
        rings, entered = sum(shot_values, 0), len(shot_values)
        if plan.tenths:
            # Zehner: jeder Schuss ab 10,0; Innenzehner gibt es nicht.
            rings = to_tenths(Decimal(rings))
            tens = sum(1 for value in shot_values if value >= MAX_RING)
        elif not plan.hits_only:
            tens = shot_values.count(MAX_RING)
            inner_tens = raw.shots.count(INNER_TEN)
    elif plan.rings and raw.total is not None:
        rings, entered, tens, inner_tens = raw.total, expected, raw.tens, raw.inner_tens

    time_cs = plan.abort_time_cs if raw.status in FIXED_TIME else raw.time_cs
    penalty = None
    if raw.status == MALFUNCTION:
        penalty = plan.malfunction_penalty_cs
    elif raw.standing is not None and plan.penalty_cs is not None:
        penalty = raw.standing * plan.penalty_cs
    total = None
    if plan.series_time and (time_cs is not None or penalty is not None):
        total = (time_cs or 0) + (penalty or 0)

    complete = (
        (not plan.rings or entered == expected or raw.status == UNFINISHED)
        and (not plan.series_time or time_cs is not None)
        and (not plan.standing or raw.standing is not None or raw.status == MALFUNCTION)
    )
    captured = (
        raw.status != NORMAL
        or bool(raw.shots)
        or any(
            value is not None
            for value in (raw.total, raw.tens, raw.inner_tens, raw.time_cs, raw.standing)
        )
    )
    return SeriesResult(
        number=series_plan.number,
        struck=series_plan.struck,
        status=raw.status,
        captured=captured,
        complete=complete,
        shots_entered=entered,
        shots_expected=expected,
        rings=rings,
        tens=tens,
        inner_tens=inner_tens,
        measured_time_cs=raw.time_cs,
        time_cs=time_cs,
        standing=raw.standing,
        penalty_cs=penalty,
        total_cs=total,
        shot_values=shot_values,
    )


def _shot_text(shot: Shot) -> str:
    return shot if isinstance(shot, str) else format_number(shot)


def _series_text(plan: SectionPlan, raw: RawSeries, result: SeriesResult) -> str:
    parts: list[str] = []
    if plan.rings and result.rings is not None:
        rings = format_number(result.rings)
        if raw.shots is not None:
            text = f"{rings} Ringe"
            if len(raw.shots) > 1:
                text = f"{' + '.join(_shot_text(shot) for shot in raw.shots)} = {text}"
            if result.shots_entered < result.shots_expected:
                unit = "Ziele" if plan.per_target else "Schuss"
                text += f" ({result.shots_entered} von {result.shots_expected} {unit})"
            if result.status == UNFINISHED:
                text = f"{STATUS_LABELS[UNFINISHED]} → {text}"
        else:
            text = f"Seriensumme {rings} Ringe"
            if result.tens is not None:
                text += f", {result.tens} Zehner"
            if result.inner_tens is not None:
                text += f", {result.inner_tens} Innenzehner"
        parts.append(text)
    if plan.standing or result.status in FIXED_TIME:
        parts.append(_penalty_text(plan, result))
    elif plan.series_time and result.time_cs is not None:
        label = "Zeit des letzten Schusses" if result.status == UNFINISHED else "Zeit"
        parts.append(f"{label} {format_cs(result.time_cs)}")
    return ", ".join(parts)


def _penalty_text(plan: SectionPlan, result: SeriesResult) -> str:
    if result.status in FIXED_TIME:
        return _fixed_time_text(plan, result)
    per_target = plan.spec.zuschlag_je_stehender_scheibe_s
    assert per_target is not None  # plan.standing
    standing = result.standing
    penalty = (
        f"{plural(standing, 'stehende Scheibe', 'stehende Scheiben')} × "
        f"{format_seconds_value(per_target)} s"
        if standing is not None
        else ""
    )
    if result.time_cs is None:
        return f"Zeit noch nicht erfasst, {penalty} = {format_cs(result.penalty_cs or 0)}"
    if standing is None:
        return f"{format_cs(result.time_cs)} (stehende Scheiben noch nicht erfasst)"
    return f"{format_cs(result.time_cs)} + {penalty} = {format_cs(result.total_cs or 0)}"


def _fixed_time_text(plan: SectionPlan, result: SeriesResult) -> str:
    """Abbruch oder Störung: feste Serienzeit statt der gemessenen."""
    fixed = format_cs(result.time_cs or 0)
    text = f"{STATUS_LABELS[result.status]} → {fixed}"
    if result.status == MALFUNCTION:
        assert plan.spec.zuschlag_stoerung_vor_erstem_schuss_s is not None
        surcharge = format_seconds_value(plan.spec.zuschlag_stoerung_vor_erstem_schuss_s)
        text += f" + {surcharge} s Zuschlag = {format_cs(result.total_cs or 0)}"
        if result.standing is not None:
            text += "; stehende Scheiben werden nicht gewertet"
    elif plan.standing and result.standing is None:
        text += " (stehende Scheiben noch nicht erfasst)"
    elif plan.standing and result.standing is not None:
        per_target = plan.spec.zuschlag_je_stehender_scheibe_s or 0
        text += (
            f" + {plural(result.standing, 'stehende Scheibe', 'stehende Scheiben')} × "
            f"{format_seconds_value(per_target)} s = {format_cs(result.total_cs or 0)}"
        )
    if result.measured_time_cs is not None:
        text += f"; gemessene Zeit {format_cs(result.measured_time_cs)} wird nicht gewertet"
    return text


def _series_numbers(numbers: list[int]) -> str:
    """[5, 6] → „Serie 5 und 6“."""
    if len(numbers) == 1:
        return f"Serie {numbers[0]}"
    return f"Serie {', '.join(map(str, numbers[:-1]))} und {numbers[-1]}"


def _section_result(
    section: SectionInput, score: SectionScore, shown: list[SeriesResult]
) -> SectionResult:
    """Summen aus den gewerteten Serien (`section.series`); `shown` enthält auch gestrichene."""
    plan = section.plan
    if plan.section_time:
        time_cs = section.time_cs
    elif plan.series_time:
        times = [s.time_cs for s in section.series if s.time_cs is not None]
        time_cs = sum(times) if times else None
    else:
        time_cs = None
    penalties = [s.penalty_cs for s in section.series if s.penalty_cs is not None]
    return SectionResult(
        id=plan.id,
        name=plan.name,
        complete=all(s.complete for s in section.series)
        and (not plan.section_time or section.time_cs is not None),
        rings=section.rings if plan.rings else None,
        time_cs=time_cs,
        penalty_cs=sum(penalties) if plan.standing else None,
        overtime_s=score.overtime_s,
        deduction=score.deduction,
        subtotal=score.subtotal,
        result=score.result,
        floored=score.floored,
        series=shown,
    )


class _Tally:
    """Zählt über alle Serien: Ringe, Zehner, Innenzehner, Ringwerte, Zuschläge."""

    def __init__(self) -> None:
        self.has_rings = False
        self.has_standing = False
        self.tenths = False
        self._rings: int | Decimal = 0
        self._tens: int | None = 0
        self._inner_tens: int | None = 0
        self._counts: Counter[int] | None = Counter()
        self._hits: int | None = 0
        self._high_values: set[int] = set()
        self._penalty = 0

    def add(self, plan: SectionPlan, raw: RawSeries | None, result: SeriesResult) -> None:
        self.has_rings |= plan.rings
        self.has_standing |= plan.standing
        self.tenths |= plan.tenths
        if plan.rings:
            self._high_values.update(
                value for value in plan.ring_values if isinstance(value, int) and value > MAX_RING
            )
            if plan.tenths:
                self._inner_tens = None
        self._penalty += result.penalty_cs or 0
        if result.rings is None or raw is None:
            return
        self._rings += result.rings
        if self._hits is not None and result.shot_values is not None:
            self._hits += sum(1 for value in result.shot_values if value > 0)
        else:
            self._hits = None
        self._tens = None if self._tens is None or result.tens is None else self._tens + result.tens
        self._inner_tens = (
            None
            if self._inner_tens is None or result.inner_tens is None
            else self._inner_tens + result.inner_tens
        )
        if self._counts is not None and raw.shots is not None:
            self._counts.update(ring_class(shot) for shot in raw.shots)
        else:
            self._counts = None

    @property
    def rings(self) -> int | Decimal | None:
        if not self.has_rings:
            return None
        return to_tenths(Decimal(self._rings)) if self.tenths else self._rings

    @property
    def hits(self) -> int | None:
        return self._hits if self.has_rings else None

    @property
    def tens(self) -> int | None:
        return self._tens if self.has_rings else None

    @property
    def inner_tens(self) -> int | None:
        return self._inner_tens if self.has_rings else None

    @property
    def ring_counts(self) -> dict[int, int] | None:
        if not self.has_rings or self._counts is None:
            return None
        keys = [*sorted(self._high_values, reverse=True), *range(MAX_RING, -1, -1)]
        return {value: self._counts[value] for value in keys}

    @property
    def penalty_cs(self) -> int | None:
        return self._penalty if self.has_standing else None

    @staticmethod
    def time_cs(sections: list[SectionInput]) -> int | None:
        times = [
            s.time_cs
            for section in sections
            if section.plan.series_time
            for s in section.series
            if s.time_cs is not None
        ] + [s.time_cs for s in sections if s.plan.section_time and s.time_cs is not None]
        timed = any(s.plan.series_time or s.plan.section_time for s in sections)
        return sum(times) if timed else None
