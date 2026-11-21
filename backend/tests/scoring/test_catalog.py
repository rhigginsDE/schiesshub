"""Jede Gruppendatei des echten Katalogs: Maske bauen, Beispiel vollständig durchrechnen.

Nur diese Datei arbeitet gegen den Katalog. Die Beispieldaten entstehen allein aus der
Eingabemaske (erlaubte Ringwerte, Felder je Serie), damit Katalogänderungen den Test nicht
brechen, solange die Wertung sie versteht. Das erwartete Ergebnis rechnet eine kleine, von der
Bibliothek unabhängige Formel je Modell nach; handgerechnete Zahlen stehen in den Modelltests.
"""

import copy
from decimal import Decimal
from typing import Any

import pytest
import yaml

from app.scoring import ComputedResult, compute, describe_form, rank_key, validate_raw
from app.scoring.form import FormDescription
from tests.conftest import REAL_CATALOG_DIR

GROUPS_DIR = REAL_CATALOG_DIR / "bds" / "gruppen"
GROUPS = sorted(path.stem for path in GROUPS_DIR.glob("*.yaml"))

RING_TIME_CS = 1234  # Zeit je Serie bei Ringen mit Zeit (Speed)
TIME_CS = 1500  # Zeit je Serie ohne Ringe (Fallscheibe)
STANDING = 1
OVERTIME_CS = 350  # Gesamtzeit 3,50 s über der Sollzeit


def variants(group: str) -> list[tuple[str, dict]]:
    data: dict[str, Any] = yaml.safe_load((GROUPS_DIR / f"{group}.yaml").read_text("utf-8"))
    return [
        (
            f"{group}/{key}/{variant['id']}",
            {"variant": copy.deepcopy(variant), "scoring": copy.deepcopy(data["wertung"])},
        )
        for key, ablauf in data["ablaeufe"].items()
        for variant in ablauf["varianten"]
    ]


def ring(value: int | str) -> int:
    return 10 if value == "X" else int(value)


def example_raw(form: FormDescription) -> dict:
    """Vollständige Rohwerte aus der Maske: je Serie der höchste erlaubte Ringwert einmal, sonst der
    höchste unter 10; auch gestrichene Serien werden erfasst (sie dürfen nicht mitzählen)."""
    sections: dict[str, Any] = {}
    for section in form.sections:
        entry: dict[str, Any] = {"series": []}
        for field in section.fields:
            assert field.key == "time_cs"
            assert section.target_time_s is not None
            entry["time_cs"] = int(section.target_time_s * 100) + OVERTIME_CS
        for series in section.series:
            values: dict[str, Any] = {}
            for field in series.fields:
                match field.key:
                    case "shots":
                        allowed = field.allowed_values or []
                        below_ten = [v for v in allowed if v != "X" and int(v) < 10]
                        second = max(below_ten, default=allowed[0], key=ring)
                        assert field.count is not None
                        values["shots"] = [allowed[0]] + [second] * (field.count - 1)
                    case "sum":
                        assert field.max is not None
                        assert series.shots is not None
                        values["sum"] = field.max - (series.shots - 1)
                    case "tens" | "inner_tens":
                        values[field.key] = 1
                    case "time_cs":
                        values["time_cs"] = RING_TIME_CS if series.shots else TIME_CS
                    case "standing":
                        values["standing"] = STANDING
                    case "status":
                        pass  # ohne Angabe „normal“
                    case other:
                        raise AssertionError(f"unbekanntes Feld {other}")
            entry["series"].append(values)
        sections[section.id] = entry
    return {"sections": sections}


def expected_score(definition: dict, form: FormDescription, raw: dict) -> Decimal:
    """Unabhängige Nachrechnung je Modell, nur über die gewerteten Serien."""
    scoring = definition["scoring"]
    total = Decimal(0)
    times_cs = 0
    for section in form.sections:
        data = raw["sections"][section.id]
        counted = [data["series"][s.index] for s in section.series if not s.struck]
        rings = sum(
            sum(map(ring, s["shots"])) if "shots" in s else s.get("sum", 0) for s in counted
        )
        times_cs += sum(s.get("time_cs", 0) for s in counted)
        match scoring["modell"]:
            case "ringe" | "ringe_minus_zeit":
                total += rings
            case "ringe_mit_zeitabzug":
                part = Decimal(rings)
                if section.target_time_s is not None:
                    over = max(0, data["time_cs"] - int(section.target_time_s * 100)) // 100
                    part -= over * Decimal(str(scoring["abzug_je_voller_sekunde_ueber_sollzeit"]))
                if "min_teilergebnis" in scoring:
                    part = max(part, Decimal(str(scoring["min_teilergebnis"])))
                total += part
            case "zeit_plus_zuschlaege":
                penalty = int((section.penalty_per_standing_s or 0) * 100)
                cs = sum(s["time_cs"] + s.get("standing", 0) * penalty for s in counted)
                total += Decimal(cs) / 100
            case other:
                raise AssertionError(f"Modell {other} hier nicht nachgerechnet")
    if scoring["modell"] == "ringe_minus_zeit":
        rounded = scoring.get("zeit_rundung") == "summe_abrunden"
        total -= Decimal(times_cs // 100) if rounded else Decimal(times_cs) / 100
    return total


def test_catalog_group_files_are_found() -> None:
    # Stand bei Einführung: 25 Gruppen; neue Dateien kommen automatisch in den Test unten.
    assert len(GROUPS) >= 25


@pytest.mark.parametrize("group", GROUPS)
@pytest.mark.parametrize("capture_mode", ["shot", "series"])
def test_group_file_computes_complete_example(group: str, capture_mode: str) -> None:
    found = variants(group)
    assert found

    for context, definition in found:
        form = describe_form(definition, capture_mode)
        assert form.model_dump(mode="json"), context
        sections = definition["variant"]["abschnitte"]
        assert [s.id for s in form.sections] == [section["id"] for section in sections], context
        raw = example_raw(form)

        assert validate_raw(definition, capture_mode, raw, partial=False) == [], context
        result = compute(definition, capture_mode, raw)

        assert result.score == expected_score(definition, form, raw), context
        assert result.complete, context
        assert result.warnings == [], context
        assert result.progress.series_complete == result.progress.series_expected, context
        assert result.progress.series_expected == form.series_expected, context
        assert result.progress.shots_entered == result.progress.shots_expected, context
        assert result.steps[-1].startswith("Ergebnis: "), context

        stored = ComputedResult.model_validate(result.model_dump(mode="json"))
        assert rank_key(definition, stored) == rank_key(definition, result), context
