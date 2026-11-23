"""Wertung: reine Rechenbibliothek ohne Datenbank und ohne Web-Abhängigkeit.

Aus `competition.definition` (Kopie von Variante und Wertung aus dem Katalog) und den Rohwerten
eines Starts entstehen Eingabemaske, Prüfung, Ergebnis mit Rechenweg und Rangfolge:

- `describe_form(definition, capture_mode)` → `FormDescription`
- `validate_raw(definition, capture_mode, raw, partial=True)` → `list[Issue]`
- `compute(definition, capture_mode, raw)` → `ComputedResult`
- `compute_aborted(definition, capture_mode, raw)` → `AbortedOutcome` (Abbruch durch den
  Schützen: vergleichbares Ergebnis oder der Grund, warum es keines gibt)
- `rank_key(definition, computed)` → Vergleichsschlüssel (Liste ganzer Zahlen)
- `tie_rules(definition)` → `TieRules` (Stechen, manuell zu entscheidende Kriterien)
- `rank(contenders, policy, rules)` → `list[Placement]`
- `best_of(contenders, rule, policy)` → Starts, die bei Mehrfachstart zählen

Wertungsmodelle stehen im Register (`registry.py`); ein neues Modell ist eine Klasse mit
`@register_model`.
"""

from app.scoring.aborted import AbortedOutcome, compute_aborted
from app.scoring.compute import compute
from app.scoring.definition import Definition, load_definition
from app.scoring.errors import DefinitionError, InvalidRawError, Issue, ScoringError
from app.scoring.form import FormDescription, describe_form
from app.scoring.ranking import (
    Contender,
    Placement,
    RankPolicy,
    TieRules,
    best_of,
    rank,
    rank_key,
    tie_rules,
)
from app.scoring.raw import validate_raw
from app.scoring.registry import ScoringModel, model_names, register_model
from app.scoring.results import ComputedResult

__all__ = [
    "AbortedOutcome",
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
    "TieRules",
    "best_of",
    "compute",
    "compute_aborted",
    "describe_form",
    "load_definition",
    "model_names",
    "rank",
    "rank_key",
    "register_model",
    "tie_rules",
    "validate_raw",
]
