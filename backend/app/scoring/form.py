"""Beschreibung der Eingabemaske für das Erfassungsterminal.

`describe_form(...).model_dump(mode="json")` geht unverändert als JSON an das Frontend. Die
Feldschlüssel (`key`) sind die Schlüssel der Rohwerte, `path` der Pfad bis zur Serie.
"""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.scoring.definition import Definition, check_capture_mode, load_definition
from app.scoring.numbers import format_seconds_value
from app.scoring.plan import SectionPlan, SeriesPlan
from app.scoring.spec import CaptureMode, Direction, PositionSpec
from app.scoring.status import ABORTED, NORMAL, STATUS_LABELS, UNFINISHED, SeriesStatus

HAND = {
    "beidhaendig": "beidhändig",
    "einhaendig": "einhändig",
    "starke_hand": "starke Hand",
    "schwache_hand": "schwache Hand",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class StatusOption(_Frozen):
    """Ein möglicher Ablauf der Serie und die Felder, die er verlangt."""

    key: SeriesStatus
    label: str
    required_fields: list[str]


class FieldSpec(_Frozen):
    key: str
    """Schlüssel in den Rohwerten: status, shots, sum, tens, inner_tens, time_cs, standing."""
    label: str
    kind: Literal["shots", "integer", "time", "choice"]
    required: bool
    """Pflicht im Regelfall (Status „normal“); je Status gilt `options[].required_fields`."""
    options: list[StatusOption] | None = None
    """Auswahl (nur `status`); fehlt der Wert, gilt „normal“."""
    count: int | None = None
    """Anzahl Schüsse (nur `shots`)."""
    allowed_values: list[int | str] | None = None
    """Erlaubte Ringwerte; „X“ ist der Innenzehner und zählt 10."""
    min: int | None = None
    max: int | None = None
    unit: str | None = None
    """„cs“ = Hundertstelsekunden."""


class StanceForm(_Frozen):
    haltung: str
    hand: str | None
    text: str


class PositionForm(_Frozen):
    nr: int
    distance_m: Decimal | None
    target: int | None
    """n-te Scheibe von links."""
    stances: list[StanceForm]


class SeriesForm(_Frozen):
    index: int
    number: int
    label: str
    path: str
    fields: list[FieldSpec]
    shots: int | None
    distance_m: Decimal | None
    time_limit_s: Decimal | None
    """Feste Schießzeit der Serie (Hinweis)."""
    max_time_s: Decimal | None
    """Zeitobergrenze der Serie (Hinweis; Überschreiten ergibt eine Warnung)."""
    position: PositionForm | None
    struck: bool
    """Gestrichen (`serien_gewertet`): darf erfasst werden, zählt nicht; ohne Pflichtfelder."""
    scoring_break_after: bool
    """Nach dieser Serie findet eine Trefferaufnahme statt."""
    max_rings: int | None
    hints: list[str]


class SectionForm(_Frozen):
    id: str
    name: str
    path: str
    fields: list[FieldSpec]
    """Felder für den ganzen Abschnitt (Gesamtzeit beim Parcours)."""
    series: list[SeriesForm]
    series_counted: int
    """Anzahl gewerteter Serien (die ersten `series_counted`)."""
    targets: int | None
    max_shots_per_series: int | None
    penalty_per_standing_s: Decimal | None
    target_time_s: Decimal | None
    max_total_time_s: Decimal | None
    time_per_shot_s: Decimal | None
    pause_between_shots_s: Decimal | None
    max_rings: int | None
    hints: list[str]


class FormDescription(_Frozen):
    variant_id: str
    variant_name: str
    model: str
    direction: Direction
    unit: str
    capture_mode: CaptureMode
    tie_breakers: list[str]
    sections: list[SectionForm]
    shots_expected: int
    series_expected: int
    max_rings: int | None
    notes: list[str]


def describe_form(definition: Mapping[str, Any] | Definition, capture_mode: str) -> FormDescription:
    mode = check_capture_mode(capture_mode)
    defn = load_definition(definition)
    sections = [_section_form(defn, plan, mode) for plan in defn.sections]
    ring_sections = [plan for plan in defn.sections if plan.rings]
    notes = []
    if mode == "series" and ring_sections:
        if "neuner_abwaerts" in defn.tie_breakers:
            notes.append(
                "Bei Seriensumme lässt sich ein Gleichstand nicht nach Neunern abwärts auflösen."
            )
        if "zehner" in defn.tie_breakers or "innenzehner" in defn.tie_breakers:
            notes.append(
                "Zehner und Innenzehner sind freiwillig, werden aber für den Gleichstand gebraucht."
            )
    return FormDescription(
        variant_id=defn.variant_id,
        variant_name=defn.variant_name,
        model=defn.model.name,
        direction=defn.model.direction,
        unit=defn.model.unit,
        capture_mode=mode,
        tie_breakers=defn.tie_breakers,
        sections=sections,
        shots_expected=sum(plan.shots_expected for plan in defn.sections),
        series_expected=sum(len(plan.counted_series) for plan in defn.sections),
        max_rings=sum(plan.max_rings or 0 for plan in ring_sections) if ring_sections else None,
        notes=notes,
    )


def _section_form(defn: Definition, plan: SectionPlan, mode: CaptureMode) -> SectionForm:
    spec = plan.spec
    path = f"sections.{plan.id}"
    fields = []
    hints = []
    if plan.section_time:
        fields.append(_time_field("Gesamtzeit"))
    if spec.sollzeit_s is not None:
        hints.append(f"Sollzeit {_s(spec.sollzeit_s)}")
    if spec.max_gesamtzeit_s is not None:
        hints.append(f"Abbruchzeit {_s(spec.max_gesamtzeit_s)}")
    return SectionForm(
        id=plan.id,
        name=plan.name,
        path=path,
        fields=fields,
        series=[_series_form(defn, plan, series, mode, path) for series in plan.series],
        series_counted=len(plan.counted_series),
        targets=plan.targets,
        max_shots_per_series=spec.max_schuss_je_serie,
        penalty_per_standing_s=spec.zuschlag_je_stehender_scheibe_s,
        target_time_s=spec.sollzeit_s,
        max_total_time_s=spec.max_gesamtzeit_s,
        time_per_shot_s=spec.zeit_je_schuss_s,
        pause_between_shots_s=spec.pause_zwischen_schuessen_s,
        max_rings=plan.max_rings,
        hints=hints,
    )


def _series_form(
    defn: Definition, plan: SectionPlan, series: SeriesPlan, mode: CaptureMode, path: str
) -> SeriesForm:
    spec = plan.spec
    fields: list[FieldSpec] = []
    statuses = defn.series_statuses(plan)
    if len(statuses) > 1:
        fields.append(
            FieldSpec(
                key="status",
                label="Ablauf der Serie",
                kind="choice",
                required=False,
                options=[_status_option(plan, status, mode) for status in statuses],
            )
        )
    shots = series.shots
    if shots is not None:
        if mode == "shot":
            fields.append(
                FieldSpec(
                    key="shots",
                    label="Schüsse",
                    kind="shots",
                    required=True,
                    count=shots,
                    allowed_values=list(plan.ring_values),
                )
            )
        else:
            fields.append(
                FieldSpec(
                    key="sum",
                    label="Seriensumme",
                    kind="integer",
                    required=True,
                    min=0,
                    max=shots * plan.max_ring,
                )
            )
            if "zehner" in defn.tie_breakers or "innenzehner" in defn.tie_breakers:
                fields.append(
                    FieldSpec(
                        key="tens",
                        label="Zehner (mit Innenzehnern)",
                        kind="integer",
                        required=False,
                        min=0,
                        max=shots,
                    )
                )
            if "innenzehner" in defn.tie_breakers:
                fields.append(
                    FieldSpec(
                        key="inner_tens",
                        label="Innenzehner",
                        kind="integer",
                        required=False,
                        min=0,
                        max=shots,
                    )
                )
    if plan.series_time:
        fields.append(_time_field("Zeit"))
    if plan.standing:
        fields.append(
            FieldSpec(
                key="standing",
                label="Stehende Scheiben",
                kind="integer",
                required=True,
                min=0,
                max=plan.targets,
            )
        )

    hints = []
    position = _position_form(series.position) if series.position else None
    if position is not None:
        hints.append(_position_text(position))
    if series.distance_m is not None:
        hints.append(f"Distanz {format_seconds_value(series.distance_m)} m")
    if shots is not None:
        hints.append(f"{shots} Schuss")
    if spec.max_schuss_je_serie is not None:
        hints.append(f"höchstens {spec.max_schuss_je_serie} Schuss")
    if plan.targets is not None:
        hints.append(f"{plan.targets} Scheiben")
    if series.fixed_time_s is not None:
        hints.append(f"Schießzeit {_s(series.fixed_time_s)}")
    if spec.zeit_je_schuss_s is not None or spec.pause_zwischen_schuessen_s is not None:
        parts = []
        if spec.zeit_je_schuss_s is not None:
            parts.append(f"{_s(spec.zeit_je_schuss_s)} Sicht")
        if spec.pause_zwischen_schuessen_s is not None:
            parts.append(f"{_s(spec.pause_zwischen_schuessen_s)} Pause")
        hints.append(f"je Schuss {', '.join(parts)}")
    if series.max_time_s is not None:
        hints.append(f"Zeitlimit {_s(series.max_time_s)}")
    if spec.zuschlag_je_stehender_scheibe_s is not None:
        hints.append(f"{_s(spec.zuschlag_je_stehender_scheibe_s)} Zuschlag je stehender Scheibe")
    if series.scoring_break_after:
        hints.append("danach Trefferaufnahme")
    if series.struck:
        hints.insert(0, "gestrichen (nicht gewertet)")
        fields = [field.model_copy(update={"required": False}) for field in fields]

    prefix = f"{plan.name}, " if defn.multi_section else ""
    return SeriesForm(
        index=series.index,
        number=series.number,
        label=f"{prefix}Serie {series.number}",
        path=f"{path}.series[{series.index}]",
        fields=fields,
        shots=shots,
        distance_m=series.distance_m,
        time_limit_s=series.fixed_time_s,
        max_time_s=series.max_time_s,
        position=position,
        struck=series.struck,
        scoring_break_after=series.scoring_break_after,
        max_rings=shots * plan.max_ring if shots is not None else None,
        hints=hints,
    )


def _status_option(plan: SectionPlan, status: SeriesStatus, mode: CaptureMode) -> StatusOption:
    fields: list[str] = []
    if status == NORMAL:
        if plan.rings:
            fields.append("shots" if mode == "shot" else "sum")
        if plan.series_time:
            fields.append("time_cs")
        if plan.standing:
            fields.append("standing")
    elif status == UNFINISHED:
        fields = ["shots", "time_cs"]
    elif status in ABORTED and plan.standing:
        fields = ["standing"]
    return StatusOption(key=status, label=STATUS_LABELS[status], required_fields=fields)


def _time_field(label: str) -> FieldSpec:
    return FieldSpec(key="time_cs", label=label, kind="time", required=True, min=1, unit="cs")


def _position_form(position: PositionSpec) -> PositionForm:
    stances = []
    for stance in position.anschlaege:
        text = stance.haltung
        if stance.hand is not None:
            text += f", {HAND[stance.hand]}"
        stances.append(StanceForm(haltung=stance.haltung, hand=stance.hand, text=text))
    return PositionForm(
        nr=position.nr, distance_m=position.distanz_m, target=position.scheibe, stances=stances
    )


def _position_text(position: PositionForm) -> str:
    text = f"Position {position.nr}: " + " oder ".join(s.text for s in position.stances)
    if position.target is not None:
        text += f", Scheibe {position.target}"
    return text


def _s(seconds: Decimal) -> str:
    return f"{format_seconds_value(seconds)} s"
