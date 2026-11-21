"""Prüfung der Katalogdateien ohne Datenbank."""

from pathlib import Path

from app.modules.katalog.loader import CatalogError, load_catalog
from tests.conftest import REAL_CATALOG_DIR, edit_yaml

GROUP_FILE = "tst/gruppen/kw-25m-praezision.yaml"


def errors_of(root: Path) -> list[CatalogError]:
    result = load_catalog(root)
    # Ein Verband mit Fehlern wird als Ganzes nicht übernommen.
    assert result.federations == [] or not result.errors
    return result.errors


def test_real_catalog_is_valid(real_catalog_counts: dict[str, int]) -> None:
    result = load_catalog(REAL_CATALOG_DIR)

    assert [str(error) for error in result.errors] == []
    assert [federation.key for federation in result.federations] == ["bds"]
    bds = result.federations[0]
    assert len(bds.groups) == real_catalog_counts["gruppen"]
    assert bds.discipline_count == real_catalog_counts["disziplinen"]
    assert bds.classes is not None
    assert len(bds.classes.klassen) == real_catalog_counts["klassen"]


def test_real_catalog_has_expected_size(real_catalog_counts: dict[str, int]) -> None:
    """Stand laut catalog/README.md. Ändert sich der Katalog, hier bewusst nachziehen."""
    assert real_catalog_counts == {"gruppen": 25, "disziplinen": 191, "klassen": 9}


def test_minimal_catalog_is_valid(minimal_catalog: Path) -> None:
    result = load_catalog(minimal_catalog)

    assert result.errors == []
    assert result.present_keys == {"tst"}
    assert result.federations[0].discipline_count == 2


def test_unknown_field_is_reported_with_file_and_path(minimal_catalog: Path) -> None:
    edit_yaml(
        minimal_catalog / GROUP_FILE,
        lambda data: data["disziplinen"][1].update({"kaliber": "9 mm"}),
    )

    errors = errors_of(minimal_catalog)

    assert errors == [
        CatalogError(
            verband="tst",
            datei=GROUP_FILE,
            pfad="disziplinen[1].kaliber",
            meldung="unbekanntes Feld",
        )
    ]
    assert str(errors[0]) == f"{GROUP_FILE}: disziplinen[1].kaliber: unbekanntes Feld"


def test_unknown_field_in_nested_section(minimal_catalog: Path) -> None:
    def change(data: dict) -> None:
        section = data["ablaeufe"]["praezision-2x10"]["varianten"][0]["abschnitte"][0]
        section["schuss"] = 10

    edit_yaml(minimal_catalog / GROUP_FILE, change)

    [error] = errors_of(minimal_catalog)

    assert error.pfad == "ablaeufe.praezision-2x10.varianten[0].abschnitte[0].schuss"
    assert error.meldung == "unbekanntes Feld"


def test_duplicate_code_within_file(minimal_catalog: Path) -> None:
    edit_yaml(
        minimal_catalog / GROUP_FILE,
        lambda data: data["disziplinen"][1].update({"kennziffer": "1001"}),
    )

    [error] = errors_of(minimal_catalog)

    assert error.datei == GROUP_FILE
    assert error.pfad == "disziplinen[1].kennziffer"
    assert "1001" in error.meldung
    assert "doppelt" in error.meldung


def test_duplicate_code_across_files(minimal_catalog: Path) -> None:
    source = minimal_catalog / GROUP_FILE
    other = source.with_name("lw-50m-praezision.yaml")
    other.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def change(data: dict) -> None:
        data["gruppe"]["id"] = "lw-50m-praezision"
        data["disziplinen"] = [data["disziplinen"][0]]

    edit_yaml(other, change)

    [error] = errors_of(minimal_catalog)

    assert error.datei == "tst/gruppen/lw-50m-praezision.yaml"
    assert error.pfad == "disziplinen[0].kennziffer"
    assert GROUP_FILE in error.meldung


def test_dead_procedure_reference(minimal_catalog: Path) -> None:
    edit_yaml(
        minimal_catalog / GROUP_FILE,
        lambda data: data["disziplinen"][0].update({"ablauf": "gibt-es-nicht"}),
    )

    [error] = errors_of(minimal_catalog)

    assert error.datei == GROUP_FILE
    assert error.pfad == "disziplinen[0].ablauf"
    assert "gibt-es-nicht" in error.meldung


def test_dead_class_merge_reference(minimal_catalog: Path) -> None:
    edit_yaml(
        minimal_catalog / "tst/klassen.yaml",
        lambda data: data["klassen"][1].update({"zusammenlegen_in": ["offen", "herren"]}),
    )

    [error] = errors_of(minimal_catalog)

    assert error.datei == "tst/klassen.yaml"
    assert error.pfad == "klassen[1].zusammenlegen_in[1]"
    assert "herren" in error.meldung


def test_code_must_be_text(minimal_catalog: Path) -> None:
    edit_yaml(
        minimal_catalog / GROUP_FILE,
        lambda data: data["disziplinen"][0].update({"kennziffer": 1001}),
    )

    [error] = errors_of(minimal_catalog)

    assert error.pfad == "disziplinen[0].kennziffer"
    assert "Text" in error.meldung


def test_group_id_must_match_file_name(minimal_catalog: Path) -> None:
    edit_yaml(
        minimal_catalog / GROUP_FILE,
        lambda data: data["gruppe"].update({"id": "anders"}),
    )

    [error] = errors_of(minimal_catalog)

    assert error.pfad == "gruppe.id"


def test_duplicate_yaml_key_is_rejected(minimal_catalog: Path) -> None:
    path = minimal_catalog / GROUP_FILE
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "ablaeufe:\n  praezision-2x10:\n",
            'ablaeufe:\n  praezision-2x10: { beschreibung: "x" }\n  praezision-2x10:\n',
        ),
        encoding="utf-8",
    )

    [error] = errors_of(minimal_catalog)

    assert error.datei == GROUP_FILE
    assert "doppelt" in error.meldung


def test_per_series_list_must_match_series_count(minimal_catalog: Path) -> None:
    def change(data: dict) -> None:
        section = data["ablaeufe"]["praezision-2x10"]["varianten"][0]["abschnitte"][0]
        del section["zeit_je_serie_s"]
        section["zeiten_s"] = [300, 300, 300]

    edit_yaml(minimal_catalog / GROUP_FILE, change)

    [error] = errors_of(minimal_catalog)

    assert error.pfad == "ablaeufe.praezision-2x10.varianten[0].abschnitte[0]"
    assert "zeiten_s" in error.meldung


def _set_positions(minimal_catalog: Path, positions: list[dict], **extra: object) -> None:
    def change(data: dict) -> None:
        section = data["ablaeufe"]["praezision-2x10"]["varianten"][0]["abschnitte"][0]
        section["positionen"] = positions
        section.update(extra)

    edit_yaml(minimal_catalog / GROUP_FILE, change)


TWO_POSITIONS = [
    {"nr": 1, "distanz_m": 20, "anschlaege": [{"haltung": "stehend", "hand": "beidhaendig"}]},
    {
        "nr": 2,
        "distanz_m": 15,
        "anschlaege": [
            {"haltung": "kniend", "hand": "beidhaendig"},
            {"haltung": "stehend", "hand": "schwache_hand"},
        ],
        "scheibe": 2,
    },
]


def test_positions_are_accepted(minimal_catalog: Path) -> None:
    _set_positions(minimal_catalog, TWO_POSITIONS, distanzen_m=[20, 15])

    result = load_catalog(minimal_catalog)

    assert result.errors == []
    group = result.federations[0].groups[0]
    section = group.content.ablaeufe["praezision-2x10"].varianten[0].abschnitte[0]
    assert section.positionen is not None
    assert [len(p.anschlaege) for p in section.positionen] == [1, 2]
    assert section.positionen[1].anschlaege[1].hand == "schwache_hand"


def test_position_hand_is_optional(minimal_catalog: Path) -> None:
    positions = [{"nr": n, "anschlaege": [{"haltung": "kniend"}]} for n in (1, 2)]
    _set_positions(minimal_catalog, positions)

    assert errors_of(minimal_catalog) == []


def test_positions_must_match_series_count(minimal_catalog: Path) -> None:
    _set_positions(minimal_catalog, TWO_POSITIONS[:1])

    [error] = errors_of(minimal_catalog)

    assert error.pfad == "ablaeufe.praezision-2x10.varianten[0].abschnitte[0]"
    assert "positionen" in error.meldung


def test_position_distance_must_match_distances(minimal_catalog: Path) -> None:
    _set_positions(minimal_catalog, TWO_POSITIONS, distanzen_m=[20, 10])

    [error] = errors_of(minimal_catalog)

    assert "positionen[1].distanz_m" in error.meldung


def test_unknown_stance_is_rejected(minimal_catalog: Path) -> None:
    positions = [
        {"nr": n, "anschlaege": [{"haltung": "sitzend", "hand": "beidhaendig"}]} for n in (1, 2)
    ]
    _set_positions(minimal_catalog, positions)

    errors = errors_of(minimal_catalog)

    assert errors
    assert all("haltung" in error.pfad for error in errors)


def _edit_section(minimal_catalog: Path, **fields: object) -> None:
    def change(data: dict) -> None:
        data["ablaeufe"]["praezision-2x10"]["varianten"][0]["abschnitte"][0].update(fields)

    edit_yaml(minimal_catalog / GROUP_FILE, change)


def test_speed_and_falling_plate_fields_are_accepted(minimal_catalog: Path) -> None:
    _edit_section(
        minimal_catalog,
        ringwerte=[10, 7, 0],
        zeit_bei_abbruch_s=60,
        zuschlag_stoerung_vor_erstem_schuss_s=50,
    )
    edit_yaml(
        minimal_catalog / GROUP_FILE,
        lambda data: data["wertung"].update(
            {"unbeendete_serie": "ringe_bis_dahin_zeit_letzter_schuss"}
        ),
    )

    assert errors_of(minimal_catalog) == []


def test_ring_values_must_descend_without_duplicates(minimal_catalog: Path) -> None:
    for values in ([7, 10, 0], [10, 10, 0], []):
        root = minimal_catalog
        _edit_section(root, ringwerte=values)

        [error] = errors_of(root)

        assert "ringwerte" in error.meldung


def test_ring_values_must_not_be_negative(minimal_catalog: Path) -> None:
    _edit_section(minimal_catalog, ringwerte=[10, -1])

    assert errors_of(minimal_catalog)


def test_unknown_unfinished_series_rule_is_rejected(minimal_catalog: Path) -> None:
    edit_yaml(
        minimal_catalog / GROUP_FILE,
        lambda data: data["wertung"].update({"unbeendete_serie": "null_ringe"}),
    )

    [error] = errors_of(minimal_catalog)

    assert error.pfad == "wertung.unbeendete_serie"


def test_abort_seconds_must_be_positive(minimal_catalog: Path) -> None:
    _edit_section(minimal_catalog, zeit_bei_abbruch_s=0)

    errors = errors_of(minimal_catalog)

    # Zahl ist int | float, deshalb meldet Pydantic je Variante einen Fehler.
    assert errors
    assert all("zeit_bei_abbruch_s" in error.pfad for error in errors)


def test_counted_series_and_scoring_breaks_are_accepted(minimal_catalog: Path) -> None:
    _edit_section(minimal_catalog, serien_gewertet=1, trefferaufnahme_nach=[1, 2])

    assert errors_of(minimal_catalog) == []


def test_counted_series_must_not_exceed_series(minimal_catalog: Path) -> None:
    _edit_section(minimal_catalog, serien_gewertet=3)

    [error] = errors_of(minimal_catalog)

    assert "serien_gewertet" in error.meldung


def test_counted_series_must_be_positive(minimal_catalog: Path) -> None:
    _edit_section(minimal_catalog, serien_gewertet=0)

    assert errors_of(minimal_catalog)


def test_scoring_breaks_must_ascend_and_stay_within_series(minimal_catalog: Path) -> None:
    for values in ([2, 1], [1, 1], [1, 3]):
        _edit_section(minimal_catalog, trefferaufnahme_nach=values)

        [error] = errors_of(minimal_catalog)

        assert "trefferaufnahme_nach" in error.meldung


def test_missing_head_file(minimal_catalog: Path) -> None:
    (minimal_catalog / "tst" / "katalog.yaml").unlink()

    [error] = errors_of(minimal_catalog)

    assert error.datei == "tst/katalog.yaml"
    assert error.meldung == "Datei fehlt"


def test_broken_federation_does_not_block_others(minimal_catalog: Path, tmp_path: Path) -> None:
    broken = minimal_catalog / "kaputt"
    broken.mkdir()
    (broken / "katalog.yaml").write_text("schema: [unvollständig", encoding="utf-8")

    result = load_catalog(minimal_catalog)

    assert [federation.key for federation in result.federations] == ["tst"]
    assert result.present_keys == {"tst", "kaputt"}
    assert {error.verband for error in result.errors} == {"kaputt"}


def test_missing_directory_is_an_error_not_an_exception(tmp_path: Path) -> None:
    result = load_catalog(tmp_path / "fehlt")

    assert result.federations == []
    assert result.present_keys is None
    assert len(result.errors) == 1
