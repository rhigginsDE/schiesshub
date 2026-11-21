"""Wertung: reine Rechenbibliothek ohne Datenbank und ohne Web-Abhängigkeit.

Aus `competition.definition` (Kopie von Variante und Wertung aus dem Katalog) und den Rohwerten
eines Starts entstehen Eingabemaske, Prüfung, Ergebnis mit Rechenweg und Rangfolge:

- `describe_form(definition, capture_mode)` → `FormDescription`
- `validate_raw(definition, capture_mode, raw, partial=True)` → `list[Issue]`
- `compute(definition, capture_mode, raw)` → `ComputedResult`
- `rank_key(definition, computed)` → Vergleichsschlüssel (Liste ganzer Zahlen)
- `rank(contenders, policy)` → `list[Placement]`
- `best_of(contenders, rule, policy)` → Starts, die bei Mehrfachstart zählen

Wertungsmodelle stehen im Register (`registry.py`); ein neues Modell ist eine Klasse mit
`@register_model`.
"""

from app.scoring.compute import compute
from app.scoring.definition import Definition, load_definition
from app.scoring.errors import DefinitionError, InvalidRawError, Issue, ScoringError
from app.scoring.form import FormDescription, describe_form
from app.scoring.ranking import Contender, Placement, RankPolicy, best_of, rank, rank_key
from app.scoring.raw import validate_raw
from app.scoring.registry import ScoringModel, model_names, register_model
from app.scoring.results import ComputedResult

__all__ = [
    "ComputedResult",
    "Contender",
    "Definition",
    "DefinitionError",
    "FormDescription",
    "InvalidRawError",
    "Issue",
    "Placement",
    "RankPolicy",
    "ScoringError",
    "ScoringModel",
    "best_of",
    "compute",
    "describe_form",
    "load_definition",
    "model_names",
    "rank",
    "rank_key",
    "register_model",
    "validate_raw",
]
