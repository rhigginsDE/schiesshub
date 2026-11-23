"""Klartext der Gleichstandskriterien für Menschen.

Die Texte stehen in `kriterien.yaml` neben diesem Modul (nicht im Code). Hinweise wie „nächstes
Kriterium: …“ zeigen nie die interne ID, sondern `criterion_text(id)`; eine ID ohne Text wird
lesbar gemacht (`abstand_zum_rand` → „abstand zum rand“).
"""

from functools import cache
from pathlib import Path

import yaml

TEXTS_FILE = Path(__file__).with_name("kriterien.yaml")


@cache
def criterion_texts() -> dict[str, str]:
    data = yaml.safe_load(TEXTS_FILE.read_text(encoding="utf-8")) or {}
    texts = data.get("kriterien") or {}
    if not isinstance(texts, dict) or not all(
        isinstance(key, str) and isinstance(value, str) and value.strip()
        for key, value in texts.items()
    ):
        raise ValueError(f"{TEXTS_FILE.name}: „kriterien“ muss ID → Text zuordnen")
    return {key: value.strip() for key, value in texts.items()}


def criterion_text(criterion: str | None) -> str | None:
    """„trefferfolge_rueckwaerts“ → „Trefferfolge ab der letzten Scheibe rückwärts …“."""
    if criterion is None:
        return None
    return criterion_texts().get(criterion) or criterion.replace("_", " ").strip()


# Beim Import lesen: ein Fehler in der Datei soll beim Start auffallen.
criterion_texts()
