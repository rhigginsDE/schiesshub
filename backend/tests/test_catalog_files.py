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
