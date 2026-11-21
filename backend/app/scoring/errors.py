"""Fehler und Hinweise der Wertung."""

from pydantic import BaseModel, ConfigDict


class Issue(BaseModel):
    """Ein Fehler oder eine Warnung zu einer Stelle der Rohwerte.

    `path` folgt dem Aufbau der Rohwerte, zum Beispiel `sections.fallscheibe.series[2].standing`
    (Serien und Schüsse ab 0 gezählt); die Meldung zählt für Menschen ab 1.
    """

    model_config = ConfigDict(frozen=True)

    path: str
    message: str


class ScoringError(ValueError):
    """Basisklasse aller Fehler der Wertung."""


class DefinitionError(ScoringError):
    """Die Wettbewerbsdefinition ist für die Wertung unbrauchbar (unbekanntes Modell, Feld, …)."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("Wettbewerbsdefinition ungültig: " + "; ".join(problems))


class InvalidRawError(ScoringError):
    """Die Rohwerte lassen sich nicht werten; `issues` nennt jede fehlerhafte Stelle."""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__(
            "Rohwerte ungültig: " + "; ".join(f"{i.path}: {i.message}" for i in issues)
        )
