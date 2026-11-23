"""Die Wertungsmodelle des Katalogs (catalog/README.md, „Wertungsmodelle“)."""

from collections.abc import Iterable, Sequence
from decimal import Decimal

from app.scoring.numbers import (
    cs_to_seconds,
    format_cs,
    format_number,
    format_seconds_value,
    is_hundredths,
    plural,
    to_tenths,
)
from app.scoring.plan import SectionPlan
from app.scoring.registry import (
    Evaluation,
    ScoringModel,
    SectionInput,
    SectionScore,
    register_model,
)
from app.scoring.spec import ScoringSpec

RING_TIE_BREAKERS = frozenset({"zehner", "innenzehner", "neuner_abwaerts"})
# Weitere Kriterien, die nur das reine Ringmodell rechnet (Bedeutung: `ranking.py`).
RING_DETAIL_TIE_BREAKERS = frozenset(
    {
        "letzte_serie_rueckwaerts",
        "schuesse_rueckwaerts",
        "ergebnis_zweite_haelfte",
        "mehr_treffer",
        "zehntel_gesamt",
        "elfer",
        "neuner",
        "sechser",
        "fuenfer",
    }
)


@register_model
class Rings(ScoringModel):
    """Summe der Ringe, höher ist besser. Mit `zehntelwertung` mit einer Nachkommastelle."""

    name = "ringe"
    direction = "absteigend"
    unit = "Ringe"
    parameters = frozenset({"zehntelwertung"})
    tie_breakers = RING_TIE_BREAKERS | RING_DETAIL_TIE_BREAKERS

    def check_section(self, section: SectionPlan) -> list[str]:
        return [
            *_needs_rings(section),
            *_no_standing(section, self.name),
            *_no_abort_rules(section, self.name),
            *_no_measured_time(section, self.name),
        ]

    def evaluate(self, scoring: ScoringSpec, sections: Sequence[SectionInput]) -> Evaluation:
        scores: list[SectionScore] = []
        steps: list[str] = []
        tenths = bool(scoring.zehntelwertung)
        for section in sections:
            steps.extend(_ring_sum_step(section))
            rings = Decimal(section.rings)
            if tenths:
                rings = to_tenths(rings)
            scores.append(SectionScore(subtotal=rings, result=rings))
        score = _sum(score.result for score in scores)
        if tenths:
            score = to_tenths(score)
        steps.append(_result_step(sections, scores, score, self.unit))
        return Evaluation(sections=scores, score=score, steps=steps)


@register_model
class RingsMinusTime(ScoringModel):
    """Ringe minus Summe der Serienzeiten in Sekunden (Speed), höher ist besser.

    Mit `zeit_rundung: summe_abrunden` wird die Zeitsumme vor dem Abzug auf volle Sekunden
    abgerundet, sonst auf die Hundertstelsekunde genau abgezogen. Das Ergebnis wird nicht nach
    unten begrenzt (dafür bräuchte es `min_teilergebnis`, das dieses Modell nicht kennt).
    Mit `unbeendete_serie` darf eine Serie als nicht beendet erfasst werden (`status.py`).
    """

    name = "ringe_minus_zeit"
    direction = "absteigend"
    unit = "Punkte"
    parameters = frozenset({"zeit_rundung", "unbeendete_serie"})
    tie_breakers = RING_TIE_BREAKERS

    def check_section(self, section: SectionPlan) -> list[str]:
        problems = [
            *_needs_rings(section),
            *_no_standing(section, self.name),
            *_no_abort_rules(section, self.name),
        ]
        if not section.spec.zeit_wird_gemessen:
            problems.append(
                "zeit_wird_gemessen: true fehlt (das Modell zieht die Zeit je Serie ab)"
            )
        elif section.section_time:
            problems.append(
                f"sollzeit_s/max_gesamtzeit_s werden vom Modell „{self.name}“ nicht ausgewertet"
            )
        return problems

    def evaluate(self, scoring: ScoringSpec, sections: Sequence[SectionInput]) -> Evaluation:
        scores = [
            SectionScore(subtotal=Decimal(section.rings), result=Decimal(section.rings))
            for section in sections
        ]
        rings = sum(section.rings for section in sections)
        ring_parts = [
            format_number(value) for section in sections for value in section.captured_rings
        ]
        times = [s.time_cs for section in sections for s in section.series if s.time_cs is not None]
        time_cs = sum(times)

        steps = [_sum_text("Ringe", ring_parts, format_number(rings))]
        steps.append(_sum_text("Zeit", [format_cs(t) for t in times], format_cs(time_cs)))
        if scoring.zeit_rundung == "summe_abrunden":
            seconds = Decimal(time_cs // 100)
            steps.append(f"Zeitsumme auf volle Sekunden abgerundet: {format_number(seconds)} s")
        else:
            seconds = cs_to_seconds(time_cs)
        score = Decimal(rings) - seconds
        steps.append(
            f"Ergebnis: {format_number(rings)} − {format_number(seconds)} = "
            f"{format_number(score)} {self.unit}"
        )
        return Evaluation(sections=scores, score=score, steps=steps)


@register_model
class RingsWithOvertimeDeduction(ScoringModel):
    """Ringe, je voller Sekunde über `sollzeit_s` eines Abschnitts ein Abzug (Mehrdistanz).

    Je Abschnitt: Ringe − volle Sekunden über Sollzeit × `abzug_je_voller_sekunde_ueber_sollzeit`;
    jedes Teilergebnis wird vor dem Addieren auf `min_teilergebnis` angehoben, falls angegeben.
    """

    name = "ringe_mit_zeitabzug"
    direction = "absteigend"
    unit = "Ringe"
    parameters = frozenset({"abzug_je_voller_sekunde_ueber_sollzeit", "min_teilergebnis"})
    required_parameters = frozenset({"abzug_je_voller_sekunde_ueber_sollzeit"})
    tie_breakers = RING_TIE_BREAKERS | {"parcours_zeit"}

    def check_section(self, section: SectionPlan) -> list[str]:
        problems = [
            *_needs_rings(section),
            *_no_standing(section, self.name),
            *_no_abort_rules(section, self.name),
        ]
        if section.series_time:
            problems.append(
                f"Zeit je Serie wird vom Modell „{self.name}“ nicht ausgewertet "
                "(gemessene Zeit braucht sollzeit_s)"
            )
        if section.section_time and section.target_time_cs is None:
            problems.append("sollzeit_s fehlt (Abzug ohne Sollzeit nicht berechenbar)")
        return problems

    def check_definition(self, scoring: ScoringSpec, sections: Sequence[SectionPlan]) -> list[str]:
        problems = []
        if not any(section.target_time_cs is not None for section in sections):
            problems.append("variant.abschnitte: kein Abschnitt hat sollzeit_s")
        for name in ("abzug_je_voller_sekunde_ueber_sollzeit", "min_teilergebnis"):
            value = getattr(scoring, name)
            if value is not None and not is_hundredths(value):
                problems.append(f"scoring.{name}: höchstens zwei Nachkommastellen")
        return problems

    def evaluate(self, scoring: ScoringSpec, sections: Sequence[SectionInput]) -> Evaluation:
        per_second = scoring.abzug_je_voller_sekunde_ueber_sollzeit
        assert per_second is not None  # durch check() garantiert
        floor = scoring.min_teilergebnis
        scores: list[SectionScore] = []
        steps: list[str] = []
        for section in sections:
            steps.extend(_ring_sum_step(section))
            name = section.plan.name
            rings = Decimal(section.rings)
            subtotal = rings
            overtime: int | None = None
            deduction: Decimal | None = None
            target_s = section.plan.spec.sollzeit_s
            if section.plan.target_time_cs is not None and target_s is not None:
                if section.time_cs is None:
                    steps.append(f"{name}: Gesamtzeit noch nicht erfasst, Abzug offen")
                else:
                    overtime = max(0, section.time_cs - section.plan.target_time_cs) // 100
                    deduction = overtime * per_second
                    subtotal = rings - deduction
                    steps.append(
                        _overtime_text(name, section.time_cs, target_s, overtime, per_second)
                        + (
                            f": {format_number(rings)} − {format_number(deduction)} "
                            f"= {format_number(subtotal)}"
                            if overtime
                            else ""
                        )
                    )
            result, floored = subtotal, False
            if floor is not None and subtotal < floor:
                result, floored = floor, True
                steps.append(
                    f"{name}: Teilergebnis {format_number(subtotal)} liegt unter der "
                    f"Untergrenze {format_number(floor)} → {format_number(floor)}"
                )
            scores.append(
                SectionScore(
                    subtotal=subtotal,
                    result=result,
                    overtime_s=overtime,
                    deduction=deduction,
                    floored=floored,
                )
            )
        score = _sum(score.result for score in scores)
        steps.append(_result_step(sections, scores, score, self.unit))
        return Evaluation(sections=scores, score=score, steps=steps)


@register_model
class TimePlusPenalties(ScoringModel):
    """Summe der Serienzeiten plus Zuschlag je stehender Scheibe (Fallscheibe), niedriger ist
    besser. Abbruch und Störung (Serienstatus, `status.py`) setzen die Serienzeit auf
    `zeit_bei_abbruch_s`. Überschreitet eine regulär erfasste Serie `max_zeit_je_serie_s`, wird
    nichts gekappt oder ersetzt – die Wertung gibt nur eine Warnung (siehe `compute`)."""

    name = "zeit_plus_zuschlaege"
    direction = "aufsteigend"
    unit = "s"

    def check_section(self, section: SectionPlan) -> list[str]:
        problems = []
        if section.rings:
            problems.append(
                f"schuss_je_serie wird vom Modell „{self.name}“ nicht ausgewertet "
                "(es zählen Zeit und stehende Scheiben)"
            )
        if not section.spec.zeit_wird_gemessen:
            problems.append("zeit_wird_gemessen: true fehlt (das Modell wertet die Zeit je Serie)")
        elif section.section_time:
            problems.append(
                f"sollzeit_s/max_gesamtzeit_s werden vom Modell „{self.name}“ nicht ausgewertet"
            )
        return problems

    def evaluate(self, scoring: ScoringSpec, sections: Sequence[SectionInput]) -> Evaluation:
        scores: list[SectionScore] = []
        steps: list[str] = []
        for section in sections:
            seconds = cs_to_seconds(sum(s.total_cs or 0 for s in section.series))
            scores.append(SectionScore(subtotal=seconds, result=seconds))
            if len(sections) > 1:
                parts = [format_cs(s.total_cs) for s in section.series if s.total_cs is not None]
                steps.append(_sum_text(section.plan.name, parts, f"{format_number(seconds)} s"))
        score = _sum(score.result for score in scores)
        if len(sections) > 1:
            steps.append(_result_step(sections, scores, score, self.unit))
        else:
            parts = [format_cs(s.total_cs) for s in sections[0].series if s.total_cs is not None]
            steps.append(_sum_text("Ergebnis", parts, f"{format_number(score)} s"))
        return Evaluation(sections=scores, score=score, steps=steps)


# --- Prüfhilfen -------------------------------------------------------------


def _needs_rings(section: SectionPlan) -> list[str]:
    if section.rings:
        return []
    return ["schuss_je_serie fehlt (das Modell wertet Ringe je Schuss)"]


def _no_standing(section: SectionPlan, model: str) -> list[str]:
    if not section.standing:
        return []
    return [f"zuschlag_je_stehender_scheibe_s wird vom Modell „{model}“ nicht ausgewertet"]


def _no_abort_rules(section: SectionPlan, model: str) -> list[str]:
    return [
        f"{name} wird vom Modell „{model}“ nicht ausgewertet"
        for name in ("zeit_bei_abbruch_s", "zuschlag_stoerung_vor_erstem_schuss_s")
        if getattr(section.spec, name) is not None
    ]


def _no_measured_time(section: SectionPlan, model: str) -> list[str]:
    if not section.spec.zeit_wird_gemessen:
        return []
    return [f"zeit_wird_gemessen: das Modell „{model}“ wertet keine gemessene Zeit"]


# --- Rechenweg --------------------------------------------------------------


def _sum(values: Iterable[Decimal]) -> Decimal:
    return sum(values, Decimal(0))


def _sum_text(label: str, parts: list[str], total: str) -> str:
    if len(parts) > 1:
        return f"{label}: {' + '.join(parts)} = {total}"
    return f"{label}: {total}"


def _ring_sum_step(section: SectionInput) -> list[str]:
    parts = [format_number(value) for value in section.captured_rings]
    if len(parts) < 2:
        return []
    rings = section.rings
    if section.plan.tenths:
        rings = to_tenths(Decimal(rings))
    return [_sum_text(section.plan.name, parts, f"{format_number(rings)} Ringe")]


def _result_step(
    sections: Sequence[SectionInput], scores: list[SectionScore], score: Decimal, unit: str
) -> str:
    total = f"{format_number(score)} {unit}"
    if len(sections) == 1:
        return f"Ergebnis: {total}"
    parts = [
        f"{section.plan.name} {format_number(part.result)}"
        for section, part in zip(sections, scores, strict=True)
    ]
    return _sum_text("Ergebnis", parts, total)


def _overtime_text(
    name: str, time_cs: int, target_s: Decimal, overtime: int, per_second: Decimal
) -> str:
    target = f"{format_seconds_value(target_s)} s"
    if overtime == 0:
        return f"{name}: Zeit {format_cs(time_cs)} innerhalb der Sollzeit von {target}, kein Abzug"
    deduction = overtime * per_second
    return (
        f"{name}: Zeit {format_cs(time_cs)}, Sollzeit {target} → "
        f"{plural(overtime, 'volle Sekunde', 'volle Sekunden')} darüber × "
        f"{format_number(per_second)} = {format_number(deduction)} Ringe Abzug"
    )
