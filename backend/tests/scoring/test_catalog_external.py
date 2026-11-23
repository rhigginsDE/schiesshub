"""Abnahme eines Katalogs außerhalb von `catalog/` (z. B. Entwurf eines neuen Verbands).

Läuft nur mit Umgebungsvariable, sonst übersprungen:

    docker compose cp <ordner-mit-dsb> backend:/tmp/katalog-check
    docker compose exec -T -e SCHIESSHUB_CATALOG_CHECK=/tmp/katalog-check backend \
        pytest tests/scoring/test_catalog_external.py -q

`SCHIESSHUB_CATALOG_CHECK` ist die Katalogwurzel (der Ordner, der `<verband>/` enthält). Jede
Variante jeder Disziplin geht genau den Weg der Turnier-Kopie: Katalog-Loader →
`CompetitionDefinition` (wie `turnier.service._catalog_definition`, gespeichert mit
`exclude_none`) → `scoring_definition` → strenge Definition der Wertung, dazu `describe_form`
in beiden Erfassungsarten und ein vollständiges Beispiel durch `validate_raw` und `compute`.

Fehler erscheinen als „Disziplin, Feld: Meldung“. Fehler des Katalog-Loaders (Katalogdatei
falsch) werden getrennt gemeldet.
"""

import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.modules.ergebnisse.rules import scoring_definition
from app.modules.katalog.loader import load_catalog
from app.modules.turnier.schemas import CompetitionDefinition
from app.scoring import DefinitionError, compute, describe_form, rank_key, validate_raw
from app.scoring.criteria import criterion_texts
from app.scoring.form import FormDescription

ROOT = os.environ.get("SCHIESSHUB_CATALOG_CHECK")
pytestmark = pytest.mark.skipif(not ROOT, reason="SCHIESSHUB_CATALOG_CHECK nicht gesetzt")


def _load() -> tuple[list[str], list[tuple[str, dict[str, Any]]]]:
    if not ROOT:
        return [], []
    result = load_catalog(Path(ROOT))
    catalog_errors = [f"{error.verband}: {error}" for error in result.errors]
    cases = []
    for federation in result.federations:
        for group in federation.groups:
            content = group.content
            for discipline in content.disziplinen:
                ablauf = content.ablaeufe[discipline.ablauf]
                for variant in ablauf.varianten:
                    stored = CompetitionDefinition(
                        variant=variant,
                        scoring=content.wertung,
                        ablauf_beschreibung=ablauf.beschreibung,
                    ).model_dump(mode="json", exclude_none=True)
                    context = (
                        f"{federation.key} {discipline.kennziffer} {discipline.name} "
                        f"({content.gruppe.id}/{discipline.ablauf}/{variant.id})"
                    )
                    cases.append((context, stored))
    return catalog_errors, cases


CATALOG_ERRORS, CASES = _load()


def example_raw(form: FormDescription) -> dict[str, Any]:
    """Vollständige Rohwerte aus der Maske (je Serie bester Wert einmal, sonst ein mittlerer)."""
    sections: dict[str, Any] = {}
    for section in form.sections:
        entry: dict[str, Any] = {"series": []}
        for field in section.fields:
            assert field.key == "time_cs"
            entry["time_cs"] = int((section.target_time_s or Decimal(60)) * 100) + 350
        for series in section.series:
            values: dict[str, Any] = {}
            for field in series.fields:
                match field.key:
                    case "shots":
                        assert field.count is not None
                        if field.decimals:
                            values["shots"] = ["10,9"] + ["9.5"] * (field.count - 1)
                        else:
                            allowed = field.allowed_values or []
                            values["shots"] = [allowed[0]] + [allowed[-1]] * (field.count - 1)
                    case "sum":
                        if field.decimals:
                            assert field.value_max is not None
                            values["sum"] = str(field.value_max - 1)
                        else:
                            assert field.max is not None
                            values["sum"] = field.max
                    case "tens" | "inner_tens":
                        pass  # freiwillig
                    case "time_cs":
                        values["time_cs"] = 1234
                    case "standing":
                        values["standing"] = 1
                    case "status":
                        pass
                    case other:
                        raise AssertionError(f"unbekanntes Feld {other}")
            entry["series"].append(values)
        sections[section.id] = entry
    return {"sections": sections}


def check(context: str, stored: dict[str, Any]) -> list[str]:
    definition = scoring_definition(stored)
    problems: list[str] = []
    for mode in ("shot", "series"):
        try:
            form = describe_form(definition, mode)
        except DefinitionError as exc:
            return [f"{context}, {problem}" for problem in exc.problems]
        form.model_dump(mode="json")
        raw = example_raw(form)
        issues = validate_raw(definition, mode, raw, partial=False)
        problems.extend(f"{context}, {mode}: {i.path}: {i.message}" for i in issues)
        if issues:
            continue
        result = compute(definition, mode, raw)
        if not result.complete:
            problems.append(f"{context}, {mode}: Beispiel nicht vollständig")
        rank_key(definition, result)
    return problems


def test_catalog_loads_without_errors() -> None:
    assert CATALOG_ERRORS == [], "Katalogdatei falsch:\n" + "\n".join(CATALOG_ERRORS)
    assert CASES


@pytest.mark.parametrize(
    ("context", "stored"), CASES or [("leer", {})], ids=[c for c, _ in CASES] or ["leer"]
)
def test_variant_passes_strict_definition_and_form(context: str, stored: dict) -> None:
    problems = check(context, stored)
    assert problems == [], "\n".join(problems)


def test_every_criterion_has_a_plain_text() -> None:
    """Jede Kriterien-ID des Katalogs hat einen Klartext (`app/scoring/kriterien.yaml`)."""
    used = {c for _, stored in CASES for c in stored.get("scoring", {}).get("gleichstand", [])}
    missing = sorted(used - set(criterion_texts()))
    assert missing == [], f"Klartext fehlt in app/scoring/kriterien.yaml: {missing}"
