"""Klartext der Gleichstandskriterien für Menschen.

Die Texte stehen in `kriterien.yaml` neben diesem Modul (nicht im Code), je Kriterium in zwei
Fassungen:

- `lang` – der volle Wortlaut (`criterion_text(id)`): Rangliste (`tie_note_long`), Export,
  Eingabemaske, fehlende Angaben;
- `kurz` – für den Bildschirm (`criterion_short(id, hits_only=…)`, `tie_note`). Ein Text oder,
  wenn die Wertung das Kriterium je nach Disziplin verschieden anwendet, je Fall:
  `standard` und `treffer` (alle Abschnitte zählen nur Treffer, z. B. Wurfscheibe).

Hinweise wie „nächstes Kriterium: …“ zeigen nie die interne ID; eine ID ohne Text wird lesbar
gemacht (`abstand_zum_rand` → „abstand zum rand“).
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

TEXTS_FILE = Path(__file__).with_name("kriterien.yaml")
SHORT_CASES = ("standard", "treffer")
"""Fälle eines Kurztexts je Anwendung: 10-Schuss-Blöcke bzw. Ringe (`standard`) oder reine
Trefferzählung (`treffer`, `Definition.hits_only`)."""


@dataclass(frozen=True, slots=True)
class CriterionTexts:
    long: str
    short: str
    """Kurztext im Regelfall."""
    short_hits: str
    """Kurztext bei reiner Trefferzählung (meist wie `short`)."""


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


@cache
def criterion_entries() -> dict[str, CriterionTexts]:
    data = yaml.safe_load(TEXTS_FILE.read_text(encoding="utf-8")) or {}
    entries = data.get("kriterien") or {}
    if not isinstance(entries, dict):
        raise ValueError(f"{TEXTS_FILE.name}: „kriterien“ muss ID → Texte zuordnen")
    result: dict[str, CriterionTexts] = {}
    for key, value in entries.items():
        where = f"{TEXTS_FILE.name}: Kriterium „{key}“"
        if not isinstance(key, str) or not isinstance(value, dict):
            raise ValueError(f"{where} braucht „lang“ und „kurz“")
        long = _text(value.get("lang"))
        short_value = value.get("kurz")
        if isinstance(short_value, dict):
            unknown = set(short_value) - set(SHORT_CASES)
            short, short_hits = (_text(short_value.get(case)) for case in SHORT_CASES)
            if unknown or short is None or short_hits is None:
                raise ValueError(f"{where}: „kurz“ je Fall braucht genau {', '.join(SHORT_CASES)}")
        else:
            short = short_hits = _text(short_value)
        if long is None or short is None or short_hits is None:
            raise ValueError(f"{where} braucht „lang“ und „kurz“ (nicht leer)")
        result[key] = CriterionTexts(long=long, short=short, short_hits=short_hits)
    return result


def criterion_texts() -> dict[str, str]:
    """ID → voller Wortlaut."""
    return {key: entry.long for key, entry in criterion_entries().items()}


def _readable(criterion: str) -> str:
    return criterion.replace("_", " ").strip()


def criterion_text(criterion: str | None) -> str | None:
    """„trefferfolge_rueckwaerts“ → „Trefferfolge ab der letzten Scheibe rückwärts …“."""
    if criterion is None:
        return None
    entry = criterion_entries().get(criterion)
    return entry.long if entry is not None else _readable(criterion)


def criterion_short(criterion: str | None, *, hits_only: bool = False) -> str | None:
    """Kurztext für den Bildschirm, passend zur Anwendung: „letzte_serie_rueckwaerts“ →
    „letzte Zehnerserie“ (10-Schuss-Blöcke) bzw. „letzte Serie“ (`hits_only`, Wurfscheibe)."""
    if criterion is None:
        return None
    entry = criterion_entries().get(criterion)
    if entry is None:
        return _readable(criterion)
    return entry.short_hits if hits_only else entry.short


# Beim Import lesen: ein Fehler in der Datei soll beim Start auffallen.
criterion_entries()
