"""Wettbewerbsdefinition einlesen: Form prüfen, Abschnitte ableiten, Modell auflösen."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from pydantic import ValidationError

from app.scoring import models as _models  # noqa: F401  (registriert die Modelle)
from app.scoring.errors import DefinitionError
from app.scoring.plan import SectionPlan, build_section_plan
from app.scoring.registry import ScoringModel, get_model
from app.scoring.spec import CAPTURE_MODES, CaptureMode, DefinitionSpec, ScoringSpec
from app.scoring.status import ABORTED, MALFUNCTION, NORMAL, UNFINISHED, SeriesStatus


@dataclass(frozen=True)
class Definition:
    variant_id: str
    variant_name: str
    scoring: ScoringSpec
    sections: tuple[SectionPlan, ...]
    model: ScoringModel

    @property
    def multi_section(self) -> bool:
        return len(self.sections) > 1

    @property
    def tie_breakers(self) -> list[str]:
        return list(self.scoring.gleichstand or [])

    def series_statuses(self, plan: SectionPlan) -> list[SeriesStatus]:
        """Status, die eine Serie dieses Abschnitts haben darf (siehe `status.py`)."""
        statuses = [NORMAL]
        if self.scoring.unbeendete_serie and plan.rings and plan.series_time:
            statuses.append(UNFINISHED)
        if plan.abort_time_cs is not None:
            statuses.extend(ABORTED)
        if plan.malfunction_penalty_cs is not None:
            statuses.append(MALFUNCTION)
        return statuses

    def section(self, section_id: str) -> SectionPlan | None:
        return next((s for s in self.sections if s.id == section_id), None)


def load_definition(data: Mapping[str, Any] | Definition) -> Definition:
    """Liest `competition.definition`; jedes unbekannte oder unpassende Feld ist ein Fehler."""
    if isinstance(data, Definition):
        return data
    try:
        spec = DefinitionSpec.model_validate(data)
    except ValidationError as error:
        raise DefinitionError([_describe(item) for item in error.errors()]) from None

    model = get_model(spec.scoring.modell)
    plans: list[SectionPlan] = []
    problems: list[str] = []
    for index, section in enumerate(spec.variant.abschnitte):
        plan, section_problems = build_section_plan(section)
        problems.extend(
            f"variant.abschnitte[{index}] ({section.id}): {p}" for p in section_problems
        )
        if plan is not None:
            plans.append(plan)
    if not problems:
        problems = model.check(spec.scoring, plans)
    if problems:
        raise DefinitionError(problems)
    return Definition(
        variant_id=spec.variant.id,
        variant_name=spec.variant.name,
        scoring=spec.scoring,
        sections=tuple(plans),
        model=model,
    )


def check_capture_mode(capture_mode: str) -> CaptureMode:
    if capture_mode not in CAPTURE_MODES:
        raise DefinitionError(
            [f"capture_mode: „{capture_mode}“ unbekannt (erlaubt: {', '.join(CAPTURE_MODES)})"]
        )
    return cast(CaptureMode, capture_mode)


def _describe(item: Mapping[str, Any]) -> str:
    path = ""
    for part in item["loc"]:
        if isinstance(part, str) and not part.isidentifier():
            continue  # Zweige von Union-Typen, z. B. „function-before[...]“
        path += f"[{part}]" if isinstance(part, int) else (f".{part}" if path else str(part))
    if item["type"] == "extra_forbidden":
        message = "unbekanntes Feld"
    elif item["type"] == "missing":
        message = "Pflichtfeld fehlt"
    else:
        message = str(item["msg"]).removeprefix("Value error, ")
    return f"{path}: {message}" if path else message
