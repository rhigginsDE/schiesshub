"""Reine Funktionen: Abkürzung, Anzeigename, Vergleichsform und Suchindex."""

from uuid import UUID, uuid4

import pytest

from app.modules.teilnehmer.index import PersonIndex
from app.modules.teilnehmer.names import abbreviate_name, clean_text, display_name, fold


@pytest.mark.parametrize(
    ("name", "short"),
    [
        ("Markus Brandt", "M. Brandt"),
        # Mehrere Vornamen
        ("Hans Peter Müller", "H. P. Müller"),
        ("Anna Maria Luise Schmidt", "A. M. L. Schmidt"),
        # Vorname mit Bindestrich
        ("Hans-Peter Müller", "H.-P. Müller"),
        # Doppelname bleibt vollständig
        ("Anna Müller-Lüdenscheidt", "A. Müller-Lüdenscheidt"),
        # Namenszusätze gehören zum Nachnamen
        ("Ludwig van Beethoven", "L. van Beethoven"),
        ("Ursula von der Leyen", "U. von der Leyen"),
        ("Karl-Theodor zu Guttenberg", "K.-T. zu Guttenberg"),
        ("Vincent Van Gogh", "V. Van Gogh"),
        ("Kurt de la Cruz", "K. de la Cruz"),
        # Nur Zusatz und Nachname: nichts abzukürzen
        ("von Brandt", "von Brandt"),
        # Einzelner Name
        ("Markus", "Markus"),
        # Schon abgekürzter Vorname, überflüssiger Leerraum
        ("  J.   Brandt ", "J. Brandt"),
        ("Élodie Brandt", "É. Brandt"),
    ],
)
def test_abbreviate_name(name: str, short: str) -> None:
    assert abbreviate_name(name) == short


def test_display_name_by_mode() -> None:
    assert display_name("Markus  Brandt", "full") == "Markus Brandt"
    assert display_name("Markus Brandt", "short") == "M. Brandt"
    assert display_name("Markus Brandt", "hidden") is None


def test_clean_text_normalizes_unicode_and_whitespace() -> None:
    decomposed = "Köhler"  # „Köhler“ mit kombinierendem Trema
    assert clean_text(f"  Jürgen \t {decomposed}  ") == "Jürgen Köhler"


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Köhler", "koehler"),
        ("Köhler", "kohler"),
        ("KÖHLER", "Koehler"),
        ("Jürgen", "juergen"),
        ("Bärbel", "baerbel"),
        ("Weiß", "weiss"),
        ("Élodie", "elodie"),
        ("Köhler", "Köhler"),
    ],
)
def test_fold_makes_spellings_equal(left: str, right: str) -> None:
    assert fold(left) == fold(right)


def test_fold_keeps_different_names_apart() -> None:
    assert fold("Brandt") != fold("Brand")
    assert fold("Müller") != fold("Möller")


def _index() -> tuple[PersonIndex, dict[str, UUID], UUID]:
    club = uuid4()
    ids = {name: uuid4() for name in ("Markus Brandt", "Jürgen Köhler", "Anna Bergmann")}
    index = PersonIndex()
    index.load(
        [
            (ids["Markus Brandt"], "Markus Brandt", "4711", club),
            (ids["Jürgen Köhler"], "Jürgen Köhler", None, None),
            (ids["Anna Bergmann"], "Anna Bergmann", "B-0815", club),
        ],
        [(club, "SV Brandenburg")],
    )
    return index, ids, club


def test_index_search_ranks_prefix_before_word_prefix_before_substring() -> None:
    index, ids, _ = _index()
    for name in ("Klaus Schönberg", "Bergner Klaus", "Bernd Abrams"):
        ids[name] = uuid4()
        index.put_person(ids[name], name, None, None)

    # Name beginnt mit „berg“ · ein Wort beginnt damit · nur Teiltreffer.
    assert index.search("berg") == [
        ids["Bergner Klaus"],
        ids["Anna Bergmann"],
        ids["Klaus Schönberg"],
    ]
    # Wortanfang im Namen oder im Vereinsnamen („SV Brandenburg“) vor Teiltreffer („Abrams“);
    # innerhalb gleichen Rangs nach Name.
    assert index.search("bra") == [ids["Anna Bergmann"], ids["Markus Brandt"], ids["Bernd Abrams"]]


def test_index_search_matches_all_words_in_any_field() -> None:
    index, ids, _ = _index()

    assert index.search("brandt markus") == [ids["Markus Brandt"]]
    assert index.search("anna brandenburg") == [ids["Anna Bergmann"]]
    assert index.search("4711") == [ids["Markus Brandt"]]
    assert index.search("0815") == [ids["Anna Bergmann"]]
    assert index.search("KOEHLER") == [ids["Jürgen Köhler"]]
    assert index.search("kohler") == [ids["Jürgen Köhler"]]
    assert index.search("nichts") == []


def test_index_empty_query_lists_all_by_name() -> None:
    index, ids, _ = _index()

    assert index.search("  ") == [ids["Anna Bergmann"], ids["Jürgen Köhler"], ids["Markus Brandt"]]


def test_index_duplicates_need_same_folded_name_and_club() -> None:
    index, ids, club = _index()

    assert index.duplicates("markus  BRANDT", club) == [ids["Markus Brandt"]]
    assert index.duplicates("Markus Brandt", None) == []
    assert index.duplicates("Juergen Kohler", None) == [ids["Jürgen Köhler"]]
    assert index.duplicates("Markus Brandt", club, exclude=ids["Markus Brandt"]) == []


def test_index_follows_club_rename_merge_and_removal() -> None:
    index, ids, club = _index()
    other = uuid4()
    index.put_club(other, "Schützengilde Nord")

    index.put_club(club, "SG Süd")
    assert index.search("brandenburg") == []
    assert index.search("sud") == [ids["Anna Bergmann"], ids["Markus Brandt"]]

    index.move_club_members(club, other)
    index.remove_club(club)
    assert index.search("nord") == [ids["Anna Bergmann"], ids["Markus Brandt"]]
    assert index.duplicates("Markus Brandt", other) == [ids["Markus Brandt"]]

    index.remove_person(ids["Markus Brandt"])
    assert index.search("nord") == [ids["Anna Bergmann"]]
    assert len(index) == 2
