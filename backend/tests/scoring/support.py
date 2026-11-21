"""Hilfen für die Wertungstests: Rohwerte und Ranglisten-Einträge bauen."""

from typing import Any

from app.scoring import Contender, compute, rank_key


def series_of(*series: dict, section: str) -> dict:
    return {"sections": {section: {"series": list(series)}}}


def contender(
    definition_: dict, raw: dict, ident: str, capture_mode: str = "shot", **extra: Any
) -> Contender:
    result = compute(definition_, capture_mode, raw)
    return Contender(id=ident, key=rank_key(definition_, result), complete=result.complete, **extra)
