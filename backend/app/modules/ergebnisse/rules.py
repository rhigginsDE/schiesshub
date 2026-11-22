"""Reine Regeln des Moduls `ergebnisse`: ohne Datenbank, einzeln getestet.

- `scoring_definition` macht aus `competition.definition` die Eingabe für `app.scoring`.
- `replay` faltet die Ereignisse eines Starts zum aktuellen Stand (Grundlage des Neuaufbaus).
- `evaluate` rechnet einen Stand mit der Wertung und erkennt, was nach einer Änderung der
  Definition zu prüfen ist.
- `raw_changes` beschreibt den Unterschied zweier Rohwerte für den Verlauf.
- `request_hash` erkennt die Wiederholung einer Anfrage (Idempotency-Key).
"""

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.scoring import (
    ComputedResult,
    DefinitionError,
    InvalidRawError,
    Issue,
    compute,
    rank_key,
    validate_raw,
)

EVENT_LABELS: dict[str, str] = {
    "raw_set": "Rohwerte erfasst",
    "finalized": "abgeschlossen",
    "corrected": "korrigiert",
    "reopened": "wieder geöffnet",
    "aborted": "abgebrochen",
}


def scoring_definition(stored: Mapping[str, Any]) -> dict[str, Any]:
    """Nur Variante und Wertung; Herkunft (`source`) und Beschreibung braucht die Wertung nicht."""
    return {"variant": stored["variant"], "scoring": stored["scoring"]}


def issues_text(issues: Sequence[Issue], limit: int = 3) -> str:
    """Die ersten Meldungen als ein Satzteil („Serie 3: Zeit fehlt; …“)."""
    texts = [issue.message.rstrip(".") for issue in issues[:limit]]
    if len(issues) > limit:
        texts.append(f"und {len(issues) - limit} weitere")
    return "; ".join(texts)


# --- Ereignisse falten ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Was `replay` von einem Ereignis braucht."""

    seq: int
    type: str
    payload: Mapping[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Replayed:
    raw: dict[str, Any]
    is_final: bool
    finalized_at: datetime | None
    provisional_until: datetime | None
    last_seq: int


def replay(events: Iterable[EventRecord]) -> Replayed:
    """Stand nach allen Ereignissen, in der Reihenfolge ihrer Sequenznummer.

    Rohwerte kommen aus dem letzten `raw_set` oder `corrected`; `finalized` schließt ab,
    `reopened` öffnet wieder, `corrected` bleibt abgeschlossen und beginnt die Einspruchsfrist neu.
    Ein Abbruch ändert die Rohwerte nicht (der Abbruchgrund steht am Start).
    """
    raw: dict[str, Any] = {}
    is_final = False
    finalized_at: datetime | None = None
    provisional_until: datetime | None = None
    last_seq = 0
    for event in sorted(events, key=lambda item: item.seq):
        last_seq = event.seq
        if event.type in ("raw_set", "corrected"):
            raw = dict(event.payload["raw"])
        if event.type in ("finalized", "corrected"):
            is_final = True
            finalized_at = event.created_at
            until = event.payload.get("provisional_until")
            provisional_until = datetime.fromisoformat(until) if until else None
        elif event.type == "reopened":
            is_final = False
            finalized_at = None
            provisional_until = None
    return Replayed(raw, is_final, finalized_at, provisional_until, last_seq)


# --- Werten --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Evaluation:
    computed: ComputedResult | None
    rank_keys: list[int | None] | None
    review_reason: str | None

    @property
    def score(self) -> Decimal | None:
        return self.computed.score if self.computed is not None else None

    @property
    def computed_json(self) -> dict[str, Any] | None:
        return self.computed.model_dump(mode="json") if self.computed is not None else None


def evaluate(
    definition: Mapping[str, Any], capture_mode: str, raw: Mapping[str, Any], *, is_final: bool
) -> Evaluation:
    """Rechnet den Stand. Wirft nie: Was sich nicht werten lässt, wird zum Prüfgrund.

    Ein abgeschlossenes Ergebnis, das nach der Definition unvollständig ist (z. B. nach mehr
    gewerteten Serien), bekommt ebenfalls einen Prüfgrund; geöffnet wird es nicht.
    """
    try:
        computed = compute(definition, capture_mode, raw)
        keys = rank_key(definition, computed)
    except DefinitionError as exc:
        return Evaluation(None, None, f"Die Wertung kann die Definition nicht lesen: {exc}")
    except InvalidRawError as exc:
        return Evaluation(
            None, None, f"Die Rohwerte passen nicht zur Definition: {issues_text(exc.issues)}."
        )
    reason = None
    if is_final:
        missing = validate_raw(definition, capture_mode, raw, partial=False)
        if missing:
            reason = (
                "Das abgeschlossene Ergebnis ist nach der aktuellen Definition unvollständig: "
                f"{issues_text(missing)}."
            )
    return Evaluation(computed, keys, reason)


# --- Verlauf -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RawChange:
    path: str
    before: Any
    after: Any


def _flatten(value: Any, path: str, into: dict[str, Any]) -> None:
    """Blätter der Rohwerte; eine Schussliste ist ein Blatt."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            _flatten(item, f"{path}.{key}" if path else str(key), into)
    elif isinstance(value, list) and not path.endswith(".shots"):
        for index, item in enumerate(value):
            _flatten(item, f"{path}[{index}]", into)
    elif value is not None:
        into[path] = value


def raw_changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[RawChange]:
    """Geänderte, neue und entfernte Werte; Pfade wie in den Fehlermeldungen der Wertung."""
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    _flatten(before, "", old)
    _flatten(after, "", new)
    return [
        RawChange(path, old.get(path), new.get(path))
        for path in sorted(old.keys() | new.keys(), key=_path_order)
        if old.get(path) != new.get(path)
    ]


def _path_order(path: str) -> list[Any]:
    """Serien in Zahlenfolge (series[10] nach series[9])."""
    parts: list[Any] = []
    for part in path.replace("]", "").replace("[", ".").split("."):
        parts.append((0, int(part), "") if part.isdigit() else (1, 0, part))
    return parts


# --- Wiederholte Anfragen ----------------------------------------------------------


def request_hash(action: str, body: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {"action": action, "body": body}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
