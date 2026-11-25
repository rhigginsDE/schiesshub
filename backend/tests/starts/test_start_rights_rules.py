"""Startrecht laut DM-Tabelle: reine Auswertung mit der echten `catalog/dsb/startrecht.yaml`."""

import pytest

from app.modules.katalog.loader import load_catalog
from app.modules.starts.start_rights import (
    CatalogClass,
    StartRightResult,
    StartRightsTable,
    assess,
)
from tests.conftest import REAL_CATALOG_DIR

STAND = "DM 2025–2028 (Sportschießen), DM 2026–2028 (Bogen)"
PREFIX = f"Laut DM-Tabelle des DSB (Stand: {STAND})"


@pytest.fixture(scope="module")
def catalog() -> tuple[StartRightsTable, dict[str, CatalogClass]]:
    dsb = next(f for f in load_catalog(REAL_CATALOG_DIR).federations if f.key == "dsb")
    assert dsb.start_rights is not None
    assert dsb.classes is not None
    by_id = {
        klasse.id: CatalogClass(nummer=klasse.nummer, satz=klasse.satz, name=klasse.name)
        for klasse in dsb.classes.klassen
        if klasse.nummer is not None and klasse.satz is not None
    }
    table = StartRightsTable(
        federation=dsb.head.verband.kuerzel,
        stand=dsb.start_rights.stand_tabelle,
        entries=dsb.start_rights.startrecht,
        classes={(k.satz, k.nummer): k for k in by_id.values()},
    )
    return table, by_id


def check(
    catalog: tuple[StartRightsTable, dict[str, CatalogClass]], code: str, class_id: str
) -> StartRightResult:
    table, classes = catalog
    return assess(table, code, classes[class_id])


def only(result: StartRightResult) -> tuple[str, str, str, str]:
    assert len(result.notices) == 1
    notice = result.notices[0]
    return notice.code, notice.severity, notice.message_de, notice.source


def test_stand_comes_from_the_file(catalog) -> None:
    assert catalog[0].stand == STAND
    assert catalog[0].federation == "DSB"


@pytest.mark.parametrize(
    ("code", "class_id"),
    [
        ("1.10", "herren-1"),  # Luftgewehr, Einzel
        ("1.10", "schueler-w"),
        ("1.20", "jugend-m"),  # LG 3-Stellung, Einzel
        ("1.12", "damen-1"),  # Mix Team (verbundene Zellen)
        ("8.22", "herren-1"),  # KK Staffel: nur Mannschaft
        ("12.10", "blasrohr-schueler-1-m"),  # Blasrohr: Schüler nach Satz blasrohr
        ("12.10", "herren-1"),  # Blasrohr: übrige nach Satz sportschiessen
        ("1.10", "para-sh1-ab1-m"),  # Eintrag para-1.10, Kennziffer 1.10
        ("6.10", "bogen-herren"),
    ],
)
def test_eligible_classes_say_nothing(catalog, code: str, class_id: str) -> None:
    result = check(catalog, code, class_id)
    assert result.status == "startberechtigt"
    assert result.notices == ()


def test_starts_with_other_class_is_a_hint(catalog) -> None:
    result = check(catalog, "1.30", "damen-4")
    assert result.status == "startet_bei"
    assert only(result) == (
        "startet_bei",
        "hint",
        f"{PREFIX} startet Klasse Damen IV (17) in Zimmerstutzen (1.30) bei Klasse Damen III (15).",
        f"Startrecht-Tabelle DSB zur Deutschen Meisterschaft, Stand: {STAND}; "
        "Eintrag 1.30 „Zimmerstutzen“",
    )


def test_starts_with_other_class_in_para_entry(catalog) -> None:
    result = check(catalog, "1.10", "para-sh1-ab1-w")
    code, severity, message, source = only(result)
    assert (code, severity) == ("startet_bei", "hint")
    assert message == (
        f"{PREFIX} startet Klasse SH1/AB1 weiblich ohne Hilfsmittel (93) in Luftgewehr (1.10) "
        "bei Klasse SH1/AB1 männlich ohne Hilfsmittel (92)."
    )
    assert source.endswith("Eintrag para-1.10 „Luftgewehr“")


@pytest.mark.parametrize(
    ("code", "class_id", "label", "competition"),
    [
        ("1.30", "junioren-2-m", "Junioren II männlich (42)", "Zimmerstutzen (1.30)"),
        ("1.40", "damen-4", "Damen IV (17)", "KK - 3x20 (3 Pos.) (1.40)"),
        ("12.10", "junioren-2-w", "Junioren II weiblich (43)", "Blasrohr (12.10)"),
    ],
)
def test_green_cell_is_a_hint(catalog, code: str, class_id: str, label: str, competition: str):
    _, classes = catalog
    assert classes[class_id].label == label
    result = check(catalog, code, class_id)
    assert result.status == "startmoeglichkeit_0711"
    assert only(result)[:3] == (
        "startmoeglichkeit_0711",
        "hint",
        f"{PREFIX} ist Klasse {label} in {competition} nicht eigens ausgeschrieben; "
        "Startmöglichkeit nach SpO 0.7.1.1 in der nächsthöheren bzw. leistungsstärkeren "
        "ausgeschriebenen Klasse.",
    )


@pytest.mark.parametrize(
    ("code", "class_id", "text"),
    [
        ("1.30", "schueler-m", "Klasse Schüler männlich (20) in Zimmerstutzen (1.30)"),
        ("1.20", "herren-1", "Klasse Herren I (10) in 10m Luftgewehr 3-Stellung (1.20)"),
        ("1.12", "schueler-w", "Klasse Schüler weiblich (21) in 10m Luftgewehr Mix Team (1.12)"),
    ],
)
def test_red_cell_is_a_warning(catalog, code: str, class_id: str, text: str) -> None:
    result = check(catalog, code, class_id)
    assert result.status == "kein_startrecht"
    assert only(result)[:3] == (
        "kein_startrecht",
        "warning",
        f"{PREFIX} hat {text} kein Startrecht.",
    )


def test_bow_schoolchildren_get_the_schoolchildren_championship_note(catalog) -> None:
    result = check(catalog, "6.10", "bogen-schueler-a-m")
    code, severity, message, source = only(result)
    assert (code, severity) == ("kein_startrecht", "warning")
    assert message.startswith(f"{PREFIX} hat Klasse ")
    assert "in Recurve (6.10, DM Bogen im Freien) kein Startrecht." in message
    assert message.endswith(
        " Bei der Deutschen Schülermeisterschaft ist die Klasse laut Tabelle ausgeschrieben."
    )
    assert source.endswith("Eintrag 6.10 „Recurve“")


def test_class_in_no_column_is_not_advertised(catalog) -> None:
    # Bogen 6.10: Schüler C (24/25) steht in keiner Spalte, auch nicht bei der Schülermeisterschaft.
    _, classes = catalog
    label = classes["bogen-schueler-c-m"].label
    result = check(catalog, "6.10", "bogen-schueler-c-m")
    assert result.status == "nicht_ausgeschrieben"
    assert only(result)[:3] == (
        "nicht_ausgeschrieben",
        "warning",
        f"{PREFIX} ist Klasse {label} in Recurve (6.10, DM Bogen im Freien) nicht ausgeschrieben.",
    )


def test_class_of_another_set_is_not_advertised(catalog) -> None:
    # Auflage-Klasse in Luftgewehr (freihand): Die Tabelle für 1.10 nennt nur Kugel und Para.
    result = check(catalog, "1.10", "auflage-senioren-1-m")
    code, severity, message, _ = only(result)
    assert (code, severity) == ("nicht_ausgeschrieben", "warning")
    assert "in Luftgewehr (1.10) nicht ausgeschrieben." in message


def test_class_of_another_set_gets_no_schoolchildren_note(catalog) -> None:
    # Schüler (Kugel, Nummer 20) in Recurve: Die 20 der Bogentabelle ist Schüler A (Bogen).
    result = check(catalog, "6.10", "schueler-m")
    code, _, message, _ = only(result)
    assert code == "nicht_ausgeschrieben"
    assert message.endswith("in Recurve (6.10, DM Bogen im Freien) nicht ausgeschrieben.")


def test_number_belongs_to_first_set_that_knows_it(catalog) -> None:
    # Blasrohr: Nummer 20 ist dort Schüler nach Satz blasrohr, nicht Schüler (Kugel).
    result = check(catalog, "12.10", "schueler-m")
    assert result.status == "nicht_ausgeschrieben"
    assert "in Blasrohr (12.10) nicht ausgeschrieben." in only(result)[2]


@pytest.mark.parametrize("code", ["1.31", "4401", "gibt-es-nicht"])
def test_competition_without_entry_says_nothing(catalog, code: str) -> None:
    result = check(catalog, code, "herren-1")
    assert result.status == "keine_angabe"
    assert result.notices == ()


def test_no_table_no_class_no_code_say_nothing(catalog) -> None:
    table, classes = catalog
    assert assess(None, "1.10", classes["herren-1"]).status == "keine_angabe"
    assert assess(table, "1.10", None).status == "keine_angabe"
    assert assess(table, None, classes["herren-1"]).status == "keine_angabe"


def test_every_entry_and_class_of_its_set_gives_a_result(catalog) -> None:
    """Keine Ausnahme für irgendeine Kombination aus der echten Tabelle."""
    table, classes = catalog
    for key, eintrag in table.entries.items():
        sets = [eintrag.satz] if isinstance(eintrag.satz, str) else eintrag.satz
        for klasse in classes.values():
            if klasse.satz in sets:
                result = assess(table, eintrag.kennziffer or key, klasse)
                assert result.status != "keine_angabe"
                assert all(n.message_de.startswith(PREFIX) for n in result.notices)
