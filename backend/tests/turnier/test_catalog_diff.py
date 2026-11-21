"""Vergleich einer Turnier-Definition mit der Katalog-Variante (reine Funktion)."""

import copy
from typing import Any

import pytest

from app.modules.katalog.fileformat import Variante, Wertung
from app.modules.turnier.catalog_diff import compare

FERTIGKEIT: dict[str, Any] = {
    "id": "fertigkeit",
    "name": "Fertigkeit",
    "serien": 6,
    "schuss_je_serie": 5,
    "zeit_je_serie_s": 10,
    "trefferaufnahme_nach": [2, 4],
    "positionen": [
        {"nr": n, "distanz_m": 10, "anschlaege": [{"haltung": "stehend", "hand": "beidhaendig"}]}
        for n in range(1, 7)
    ],
}
PARCOURS: dict[str, Any] = {
    "id": "parcours",
    "name": "Parcours",
    "serien": 4,
    "schuss_je_serie": 5,
    "zeit_wird_gemessen": True,
    "sollzeit_s": 80,
}
VARIANT: dict[str, Any] = {
    "id": "standard",
    "name": "Standard",
    "abschnitte": [FERTIGKEIT, PARCOURS],
}
SCORING: dict[str, Any] = {
    "modell": "ringe_mit_zeitabzug",
    "rangfolge": "absteigend",
    "geprueft": True,
    "gleichstand": ["zehner", "innenzehner"],
    "abzug_je_voller_sekunde_ueber_sollzeit": 1,
}


def diff(
    variant: dict[str, Any] | None = None, scoring: dict[str, Any] | None = None
) -> list[tuple[str, Any, Any, str]]:
    result = compare(
        Variante.model_validate(VARIANT),
        Wertung.model_validate(SCORING),
        Variante.model_validate(variant or VARIANT),
        Wertung.model_validate(scoring or SCORING),
    )
    return [(d.path, d.catalog_value, d.tournament_value, d.text) for d in result]


def changed_section(index: int, **changes: Any) -> dict[str, Any]:
    variant = copy.deepcopy(VARIANT)
    for key, value in changes.items():
        if value is None:
            variant["abschnitte"][index].pop(key, None)
        else:
            variant["abschnitte"][index][key] = value
    return variant


def test_identical_definition_has_no_deviation() -> None:
    assert diff() == []


def test_cosmetic_fields_do_not_count() -> None:
    variant = copy.deepcopy(VARIANT)
    variant["name"] = "Vereinsmeisterschaft"
    variant["abschnitte"][0]["name"] = "Fertigkeit (geändert)"

    assert diff(variant, {**SCORING, "geprueft": False}) == []


def test_counted_series() -> None:
    assert diff(changed_section(0, serien_gewertet=4)) == [
        (
            "variant.abschnitte[0].serien_gewertet",
            None,
            4,
            "Abschnitt Fertigkeit: 4 von 6 Serien gewertet",
        )
    ]
    # Alle Serien gewertet ist keine Abweichung.
    assert diff(changed_section(0, serien_gewertet=6)) == []


def test_hit_review() -> None:
    only_four = diff(changed_section(0, trefferaufnahme_nach=[4]))
    none = diff(changed_section(0, trefferaufnahme_nach=[]))
    other = diff(changed_section(0, trefferaufnahme_nach=[1, 3, 5]))
    removed = diff(changed_section(0, trefferaufnahme_nach=None))
    added = diff(changed_section(1, trefferaufnahme_nach=[2]))

    assert only_four == [
        (
            "variant.abschnitte[0].trefferaufnahme_nach",
            [2, 4],
            [4],
            "Abschnitt Fertigkeit: Trefferaufnahme nur nach Serie 4 statt nach 2 und 4",
        )
    ]
    assert none[0][3] == "Abschnitt Fertigkeit: keine Trefferaufnahme statt nach 2 und 4"
    assert other[0][3] == (
        "Abschnitt Fertigkeit: Trefferaufnahme nach Serie 1, 3 und 5 statt nach 2 und 4"
    )
    assert removed[0][2] is None
    assert removed[0][3] == (
        "Abschnitt Fertigkeit: Trefferaufnahme nicht festgelegt (Katalog: nach 2 und 4)"
    )
    assert added == [
        (
            "variant.abschnitte[1].trefferaufnahme_nach",
            None,
            [2],
            "Abschnitt Parcours: Trefferaufnahme nach Serie 2 (im Katalog nicht festgelegt)",
        )
    ]


def test_series_count_changes_together_with_counted_series() -> None:
    variant = changed_section(0, serien=4, serien_gewertet=3, positionen=None)

    assert [entry[3] for entry in diff(variant)] == [
        "Abschnitt Fertigkeit: 3 von 4 Serien gewertet",
        "Abschnitt Fertigkeit: Serien 4 statt 6",
        "Abschnitt Fertigkeit: Positionen entfällt",
    ]


def test_values_with_units_and_decimal_comma() -> None:
    result = diff(changed_section(0, zeit_je_serie_s=7.5))

    assert result == [
        (
            "variant.abschnitte[0].zeit_je_serie_s",
            10,
            7.5,
            "Abschnitt Fertigkeit: Zeit je Serie 7,5 s statt 10 s",
        )
    ]


def test_new_and_removed_optional_fields() -> None:
    added = diff(changed_section(1, max_gesamtzeit_s=160))
    removed = diff(changed_section(1, sollzeit_s=None))

    assert added[0][3] == "Abschnitt Parcours: Abbruchzeit 160 s (im Katalog nicht festgelegt)"
    assert removed[0][:3] == ("variant.abschnitte[1].sollzeit_s", 80, None)
    assert removed[0][3] == "Abschnitt Parcours: Sollzeit entfällt (Katalog: 80 s)"


def test_single_position_changed() -> None:
    positions = copy.deepcopy(FERTIGKEIT["positionen"])
    positions[2]["anschlaege"] = [{"haltung": "kniend", "hand": "beidhaendig"}]

    result = diff(changed_section(0, positionen=positions))

    assert [(entry[0], entry[3]) for entry in result] == [
        (
            "variant.abschnitte[0].positionen[2]",
            "Abschnitt Fertigkeit: Position in Serie 3 geändert",
        )
    ]


def test_sections_added_removed_and_reordered() -> None:
    extra = copy.deepcopy(VARIANT)
    extra["abschnitte"].append({"id": "stechen", "name": "Stechen", "serien": 1})
    missing = copy.deepcopy(VARIANT)
    missing["abschnitte"] = [PARCOURS]
    reordered = copy.deepcopy(VARIANT)
    reordered["abschnitte"].reverse()

    assert [entry[3] for entry in diff(extra)] == [
        "Zusätzlicher Abschnitt „Stechen“ (nicht im Katalog)"
    ]
    assert [(entry[0], entry[3]) for entry in diff(missing)] == [
        ("variant.abschnitte[0]", "Abschnitt „Fertigkeit“ aus dem Katalog fehlt")
    ]
    assert [entry[3] for entry in diff(reordered)] == [
        "Reihenfolge der Abschnitte weicht vom Katalog ab"
    ]


@pytest.mark.parametrize(
    ("changes", "path", "text"),
    [
        (
            {"modell": "ringe"},
            "scoring.modell",
            "Wertung: Wertungsmodell „ringe“ statt „ringe_mit_zeitabzug“",
        ),
        (
            {"gleichstand": ["zehner"]},
            "scoring.gleichstand",
            "Wertung: Gleichstand zehner statt zehner, innenzehner",
        ),
        (
            {"unbeendete_serie": "ringe_bis_dahin_zeit_letzter_schuss"},
            "scoring.unbeendete_serie",
            "Wertung: Nicht beendete Serie „ringe_bis_dahin_zeit_letzter_schuss“ "
            "(im Katalog nicht festgelegt)",
        ),
        (
            {"abzug_je_voller_sekunde_ueber_sollzeit": None},
            "scoring.abzug_je_voller_sekunde_ueber_sollzeit",
            "Wertung: Abzug je voller Sekunde über der Sollzeit entfällt (Katalog: 1)",
        ),
    ],
)
def test_scoring_rules(changes: dict[str, Any], path: str, text: str) -> None:
    scoring = {key: value for key, value in {**SCORING, **changes}.items() if value is not None}

    assert [(entry[0], entry[3]) for entry in diff(scoring=scoring)] == [(path, text)]


def test_ring_values() -> None:
    result = diff(changed_section(1, ringwerte=[10, 8, 0]))

    assert result[0][3] == "Abschnitt Parcours: Ringwerte 10, 8, 0 (im Katalog nicht festgelegt)"
