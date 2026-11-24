"""Rohwerte in den Worten der Maske: abgeleitete Feldwerte beim Wechsel der Erfassungsart und
deutsche Namen der Felder im Verlauf.

- `derived_values`: Wurde eine Serie Schuss für Schuss (bzw. je Ziel) erfasst und wird die Maske
  in der Seriensumme gezeigt, liefert der Server die aus den Einzelwerten gerechnete Summe (und
  Zehner/Innenzehner, soweit die Maske sie hat) als Feldwert. Gespeichert wird dabei nichts; erst
  wer in der Seriensumme etwas ändert, ersetzt die Einzelwerte (`PUT …/raw`). Ringwertung und
  „je Ziel“ (Wurfscheibe, Treffer 1/0) gehen denselben Weg.
- `change_label`: Pfad einer Änderung (`sections.trap.series[0].shots`) → „Serie 1 · Treffer je
  Ziel“, unabhängig davon, in welcher Erfassungsart die Maske gerade gezeigt wird.
"""

import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from app.modules.ergebnisse.schemas import DerivedValue
from app.scoring import ComputedResult, FormDescription
from app.scoring.definition import Definition
from app.scoring.raw import series_label

_PATH = re.compile(r"^sections\.([^.\[]+)(?:\.series\[(\d+)\])?(?:\.(\w+))?(?:\[(\d+)\])?$")

# Seriensumme und, was zu ihr gehört, aus der gerechneten Serie.
_FROM_SERIES = {"sum": "rings", "tens": "tens", "inner_tens": "inner_tens"}


def derived_values(
    form: FormDescription, raw: Mapping[str, Any], computed: ComputedResult | None
) -> list[DerivedValue]:
    """Feldwerte der Seriensumme aus erfassten Einzelwerten (nur Maske in Seriensumme)."""
    if form.capture_mode != "series" or computed is None:
        return []
    sections = raw.get("sections") if isinstance(raw, Mapping) else None
    if not isinstance(sections, Mapping):
        return []
    result: list[DerivedValue] = []
    by_id = {section.id: section for section in computed.sections}
    for section_form in form.sections:
        raw_section = sections.get(section_form.id)
        computed_section = by_id.get(section_form.id)
        if not isinstance(raw_section, Mapping) or computed_section is None:
            continue
        raw_series = raw_section.get("series")
        if not isinstance(raw_series, list):
            continue
        for series_form in section_form.series:
            index = series_form.index
            item = raw_series[index] if index < len(raw_series) else None
            if not isinstance(item, Mapping) or not isinstance(item.get("shots"), list):
                continue
            if index >= len(computed_section.series):
                continue
            series = computed_section.series[index]
            for field in series_form.fields:
                attribute = _FROM_SERIES.get(field.key)
                if attribute is None:
                    continue
                value = getattr(series, attribute)
                if value is None:
                    continue
                result.append(
                    DerivedValue(
                        path=series_form.path,
                        key=field.key,
                        value=_plain(value),
                        source="shots",
                    )
                )
    return result


def _plain(value: Decimal | int) -> Decimal | int:
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    return value


_FIELD_LABELS = {
    "sum": "Seriensumme",
    "tens": "Zehner",
    "inner_tens": "Innenzehner",
    "time_cs": "Zeit",
    "standing": "Stehende Scheiben",
    "status": "Ablauf der Serie",
}


def change_label(defn: Definition | None, path: str) -> str:
    """„Serie 2 · Zeit“, „Serie 1 · Schüsse“, „Parcours · Gesamtzeit“; unbekannt: der Pfad."""
    match = _PATH.match(path)
    if defn is None or match is None:
        return path
    section_id, series_index, key, item = match.groups()
    plan = defn.section(section_id)
    if plan is None:
        return path
    if series_index is None:
        if key == "time_cs":
            return f"{plan.name} · Gesamtzeit"
        return f"{plan.name} · {key}" if key else plan.name
    index = int(series_index)
    if index >= len(plan.series):
        return path
    label = series_label(defn, plan, plan.series[index])
    if key is None:
        return label
    if key == "shots":
        if item is not None:
            unit = "Ziel" if plan.per_target else "Schuss"
            return f"{label} · {unit} {int(item) + 1}"
        return f"{label} · {'Treffer je Ziel' if plan.per_target else 'Schüsse'}"
    if key == "sum" and plan.per_target:
        return f"{label} · Treffer"
    if key == "tens" and plan.tenths:
        return f"{label} · Zehner (ab 10,0)"
    return f"{label} · {_FIELD_LABELS.get(key, key)}"
