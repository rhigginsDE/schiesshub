"""Register der Wertungsmodelle.

Ein Modell ist eine Klasse mit Namen (= `scoring.modell`), Rangfolge, erlaubten Parametern und
Gleichstandskriterien. Es prüft die Abschnitte (`check_section`) und rechnet aus den
Serienergebnissen das Endergebnis (`evaluate`). Neue Modelle (beste N aus M, Treffer, Hit-Factor)
kommen mit `@register_model` dazu, ohne dass Formular, Prüfung oder Rangliste umgebaut werden.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from app.scoring.errors import DefinitionError
from app.scoring.plan import SectionPlan
from app.scoring.results import SeriesResult
from app.scoring.spec import MODEL_PARAMETERS, TIE_BREAKERS, Direction, ScoringSpec


@dataclass(frozen=True)
class SectionInput:
    """Was ein Modell je Abschnitt bekommt: Plan, fertige Serienergebnisse, Gesamtzeit."""

    plan: SectionPlan
    series: list[SeriesResult]
    time_cs: int | None
    label: str
    """Name für den Rechenweg; leer, wenn die Variante nur einen Abschnitt hat."""

    @property
    def rings(self) -> int | Decimal:
        """Ringe der gewerteten Serien; bei Zehntelwertung `Decimal`."""
        return sum((series.rings or 0 for series in self.series), 0)

    @property
    def captured_rings(self) -> list[int | Decimal]:
        return [s.rings for s in self.series if s.captured and s.rings is not None]


@dataclass(frozen=True)
class SectionScore:
    subtotal: Decimal
    result: Decimal
    overtime_s: int | None = None
    deduction: Decimal | None = None
    floored: bool = False


@dataclass(frozen=True)
class Evaluation:
    sections: list[SectionScore]
    score: Decimal
    steps: list[str]


class ScoringModel(ABC):
    name: ClassVar[str]
    direction: ClassVar[Direction]
    unit: ClassVar[str]
    """Einheit des Endergebnisses für Menschen („Ringe“, „Punkte“, „s“)."""
    parameters: ClassVar[frozenset[str]] = frozenset()
    """Felder aus `MODEL_PARAMETERS`, die das Modell auswertet."""
    required_parameters: ClassVar[frozenset[str]] = frozenset()
    tie_breakers: ClassVar[frozenset[str]] = frozenset()

    def check(self, scoring: ScoringSpec, sections: Sequence[SectionPlan]) -> list[str]:
        problems: list[str] = []
        if scoring.rangfolge != self.direction:
            problems.append(
                f"scoring.rangfolge: Modell „{self.name}“ wertet „{self.direction}“, "
                f"nicht „{scoring.rangfolge}“"
            )
        for parameter in MODEL_PARAMETERS:
            value = getattr(scoring, parameter)
            # `false` ist bei Schaltern die Grundeinstellung und bei jedem Modell erlaubt.
            given = value is not None and value is not False
            if given and parameter not in self.parameters:
                problems.append(
                    f"scoring.{parameter}: wird vom Modell „{self.name}“ nicht ausgewertet"
                )
            if value is None and parameter in self.required_parameters:
                problems.append(f"scoring.{parameter}: Pflichtangabe für Modell „{self.name}“")
        criteria = scoring.gleichstand or []
        for index, criterion in enumerate(criteria):
            # Unbekannte IDs sind erlaubt (manuell zu entscheiden); bekannte müssen passen.
            path = f"scoring.gleichstand[{index}]"
            if criterion in TIE_BREAKERS and criterion not in self.tie_breakers:
                problems.append(
                    f"{path}: „{criterion}“ ist beim Modell „{self.name}“ nicht anwendbar"
                )
            elif criterion in criteria[:index]:
                problems.append(f"{path}: „{criterion}“ steht mehrfach in der Liste")
        for index, section in enumerate(sections):
            problems.extend(
                f"variant.abschnitte[{index}] ({section.id}): {problem}"
                for problem in self.check_section(section)
            )
        problems.extend(self.check_definition(scoring, sections))
        return problems

    @abstractmethod
    def check_section(self, section: SectionPlan) -> list[str]:
        """Probleme eines Abschnitts für dieses Modell (leer = in Ordnung)."""

    def check_definition(self, scoring: ScoringSpec, sections: Sequence[SectionPlan]) -> list[str]:
        """Prüfungen über alle Abschnitte hinweg."""
        return []

    @abstractmethod
    def evaluate(self, scoring: ScoringSpec, sections: Sequence[SectionInput]) -> Evaluation:
        """Teilergebnisse, Endergebnis und Rechenweg (ohne die Schritte je Serie)."""


_MODELS: dict[str, ScoringModel] = {}


def register_model[M: type[ScoringModel]](model: M) -> M:
    """Klassen-Dekorator: meldet ein Wertungsmodell unter seinem Namen an."""
    if model.name in _MODELS:
        raise ValueError(f"Wertungsmodell „{model.name}“ ist schon registriert")
    _MODELS[model.name] = model()
    return model


def get_model(name: str) -> ScoringModel:
    try:
        return _MODELS[name]
    except KeyError:
        known = ", ".join(model_names())
        raise DefinitionError(
            [f"scoring.modell: unbekanntes Wertungsmodell „{name}“ (bekannt: {known})"]
        ) from None


def model_names() -> list[str]:
    return sorted(_MODELS)
