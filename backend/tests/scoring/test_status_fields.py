"""Serienstatus und Felder über den echten Katalog (`/catalog`, BDS und DSB, alle Varianten).

1. Vollständigkeit: Jede Status-Option ordnet jedes Wertfeld der Serie genau einer Liste zu
   (`required_fields`, `optional_fields`, `unscored_fields`).
2. Annahme und Erhalt: Rohwerte mit allen Feldern der Serie werden bei jedem Status angenommen
   (auch für das Abschließen); gewertet wird nur, was der Status vorsieht, und der Rechenweg
   nennt die nicht gewerteten Werte.

Die Rohwerte entstehen allein aus Maske und Abschnitt, damit Katalogänderungen den Test nicht
brechen, solange die Wertung sie versteht.
"""

from decimal import Decimal
from typing import Any

import pytest

from app.modules.ergebnisse.rules import scoring_definition
from app.modules.katalog.loader import load_catalog
from app.modules.turnier.schemas import CompetitionDefinition
from app.scoring import compute, describe_form, load_definition, validate_raw
from app.scoring.definition import Definition
from app.scoring.form import FormDescription, SectionForm, SeriesForm, StatusOption
from app.scoring.numbers import format_cs
from app.scoring.plan import INNER_TEN, MAX_RING, SectionPlan, ring_value
from app.scoring.status import STATUS_LABELS
from tests.conftest import REAL_CATALOG_DIR

TIME_CS = 1234
STANDING = 1


def _cases() -> list[tuple[str, dict[str, Any]]]:
    result = load_catalog(REAL_CATALOG_DIR)
    assert not result.errors, result.errors
    seen: dict[str, dict[str, Any]] = {}
    for federation in result.federations:
        for group in federation.groups:
            content = group.content
            for key, ablauf in content.ablaeufe.items():
                for variant in ablauf.varianten:
                    stored = CompetitionDefinition(
                        variant=variant,
                        scoring=content.wertung,
                        ablauf_beschreibung=ablauf.beschreibung,
                    ).model_dump(mode="json", exclude_none=True)
                    context = f"{federation.key}/{content.gruppe.id}/{key}/{variant.id}"
                    seen[context] = scoring_definition(stored)
    return sorted(seen.items())


CASES = _cases()
MODES = ("shot", "series")


def _definition(data: dict[str, Any]) -> Definition:
    return load_definition(data)


def _status_options(series: SeriesForm) -> list[StatusOption]:
    status = next((field for field in series.fields if field.key == "status"), None)
    return list(status.options or []) if status is not None else []


def test_catalog_covers_every_status() -> None:
    """Der Katalog enthält jeden Serienstatus mindestens einmal (sonst prüfte der Test zu wenig)."""
    found: set[str] = set()
    for _, data in CASES:
        defn = _definition(data)
        for plan in defn.sections:
            found.update(defn.series_statuses(plan))
    assert found == set(STATUS_LABELS)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(("context", "data"), CASES, ids=[c for c, _ in CASES])
def test_every_field_is_in_exactly_one_list(context: str, data: dict, mode: str) -> None:
    form = describe_form(data, mode)
    for section in form.sections:
        for series in section.series:
            keys = [field.key for field in series.fields if field.key != "status"]
            for option in _status_options(series):
                lists = [option.required_fields, option.optional_fields, option.unscored_fields]
                where = f"{context} {mode} {series.label} {option.key}"
                listed = [key for keys_ in lists for key in keys_]
                assert sorted(listed) == sorted(keys), where  # genau einmal, keins fehlt
                if option.key == "normal" and not series.struck:
                    required = [field.key for field in series.fields if field.required]
                    assert required == option.required_fields, where


# --- Rohwerte mit allen Feldern -----------------------------------------------------------


def _shots(plan: SectionPlan, count: int) -> list[Any]:
    """Gültige Schüsse: einmal der höchste Wert, sonst der höchste unter 10."""
    if count == 0:
        return []
    if plan.tenths:
        return ["10,9"] + ["9.5"] * (count - 1)
    allowed = list(plan.ring_values)
    below_ten = [v for v in allowed if v != INNER_TEN and ring_value(v) < MAX_RING]
    second = max(below_ten, default=allowed[0], key=ring_value)
    return [allowed[0]] + [second] * (count - 1)


def _ring_total(plan: SectionPlan, shots: list[Any]) -> Any:
    if plan.tenths:
        return str(sum((Decimal(str(s).replace(",", ".")) for s in shots), Decimal(0)))
    return sum(ring_value(s) for s in shots)


def _tens(plan: SectionPlan, shots: list[Any]) -> int:
    if plan.tenths:
        return sum(1 for s in shots if Decimal(str(s).replace(",", ".")) >= MAX_RING)
    return sum(1 for s in shots if ring_value(s) == MAX_RING)


def series_values(plan: SectionPlan, series: SeriesForm, status: str) -> dict[str, Any]:
    """Alle Wertfelder der Serie mit gültigen Werten für diesen Status."""
    values: dict[str, Any] = {} if status == "normal" else {"status": status}
    count = series.shots or 0
    shots = _shots(plan, count - 1 if status == "unfinished" else count)
    for field in series.fields:
        match field.key:
            case "status":
                pass
            case "shots":
                values["shots"] = shots
            case "sum":
                values["sum"] = _ring_total(plan, shots)
            case "tens":
                values["tens"] = _tens(plan, shots)
            case "inner_tens":
                values["inner_tens"] = shots.count(INNER_TEN)
            case "time_cs":
                assert field.max is not None
                values["time_cs"] = min(TIME_CS, field.max)
            case "standing":
                values["standing"] = STANDING
            case other:
                raise AssertionError(f"unbekanntes Feld {other}")
    return values


def raw_for(
    defn: Definition, form: FormDescription, statuses: dict[str, str] | None = None
) -> dict[str, Any]:
    """Rohwerte mit allen Feldern aller Serien; `statuses`: Status je Abschnitt (sonst normal)."""
    sections: dict[str, Any] = {}
    for section in form.sections:
        plan = defn.section(section.id)
        assert plan is not None
        status = (statuses or {}).get(section.id, "normal")
        entry: dict[str, Any] = {
            "series": [series_values(plan, series, status) for series in section.series]
        }
        for field in section.fields:
            assert field.key == "time_cs"
            assert field.max is not None
            target = int((section.target_time_s or Decimal(60)) * 100) + 350
            entry["time_cs"] = min(target, field.max)
        sections[section.id] = entry
    return {"sections": sections}


def _section_statuses(section: SectionForm) -> list[StatusOption]:
    return _status_options(section.series[0]) if section.series else []


STATUS_CASES = [
    (context, data, mode, section_id, status)
    for context, data in CASES
    for mode in MODES
    for section in describe_form(data, mode).sections
    for section_id, status in [(section.id, option.key) for option in _section_statuses(section)]
]


@pytest.mark.parametrize(
    ("context", "data", "mode", "section_id", "status"),
    STATUS_CASES,
    ids=[f"{c[0]}-{c[2]}-{c[3]}-{c[4]}" for c in STATUS_CASES],
)
def test_all_fields_are_accepted_and_only_scored_fields_count(
    context: str, data: dict, mode: str, section_id: str, status: str
) -> None:
    defn = _definition(data)
    form = describe_form(defn, mode)
    raw = raw_for(defn, form, {section_id: status})

    assert validate_raw(defn, mode, raw, partial=True) == []
    assert validate_raw(defn, mode, raw, partial=False) == []  # Pflichtfelder genügen

    result = compute(defn, mode, raw)
    section_form = next(s for s in form.sections if s.id == section_id)
    index = [s.id for s in form.sections].index(section_id)
    for series_form, series in zip(section_form.series, result.sections[index].series, strict=True):
        if series_form.struck:
            continue  # gestrichen: zählt bei keinem Status
        option = next(o for o in _status_options(series_form) if o.key == status)
        values = raw["sections"][section_id]["series"][series_form.index]
        step = next(s for s in result.steps if s.startswith(f"{series_form.label}: "))
        where = f"{context} {mode} {series_form.label} {status}: {step}"
        assert series.status == status
        for key in option.required_fields + option.optional_fields:
            match key:
                case "shots" | "sum":
                    assert series.rings is not None, where
                case "tens":
                    assert series.tens == values["tens"], where
                case "inner_tens":
                    assert series.inner_tens == values["inner_tens"], where
                case "time_cs":
                    assert series.time_cs == values["time_cs"], where
                case "standing":
                    assert series.standing == values["standing"], where
                    assert series.penalty_cs is not None, where
        for key in option.unscored_fields:
            match key:
                case "time_cs":
                    assert series.measured_time_cs == values["time_cs"], where
                    assert series.time_cs != values["time_cs"], where
                    measured = format_cs(values["time_cs"])
                    assert f"gemessene Zeit {measured} wird nicht gewertet" in step, where
                case "standing":
                    assert "1 erfasste stehende Scheibe wird nicht gewertet" in step, where
                case other:
                    raise AssertionError(f"{where}: kein Rechenweg-Text für {other}")
