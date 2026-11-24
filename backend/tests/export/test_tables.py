"""Aufbereitung ohne Datenbank: Schreibweisen, Dateinamen, CSV, Siegerliste aus der Rangliste."""

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.modules.ergebnisse.schemas import RankingGroup, RankingOut, RankingRow, SeriesPart
from app.modules.export import tables
from app.modules.export.csvout import cell_text, neutralize, write_csv
from app.modules.export.formatting import date_range_de, file_name, number, seconds
from app.modules.export.records import (
    CompetitionInfo,
    Meta,
    PersonName,
    SeriesValue,
    StartRecord,
)
from tests.export.conftest import read_csv

OPEN = uuid.uuid4()
LADIES = uuid.uuid4()
CLASS_NAMES = {OPEN: "Offene Klasse", LADIES: "Damenklasse"}
NOW = datetime(2027, 3, 6, 13, 0, tzinfo=UTC)
META = Meta("Vereinspokal", "SV Musterstadt", date(2027, 3, 6), date(2027, 3, 6), NOW, "public")
COMPETITION = CompetitionInfo(
    id=uuid.uuid4(),
    code="1001",
    name="Pistole bis 9 mm",
    sort=1,
    range_id=None,
    range_name="Stand 1",
    range_sort=1,
    multi_start=False,
    planning="queue",
    sections=(("praezision", "Präzision"),),
)


def ranking_row(
    place: int | None,
    number_: int,
    score: str | None,
    *,
    entry: uuid.UUID | None = None,
    klass: uuid.UUID = OPEN,
    **fields: Any,
) -> RankingRow:
    values: dict[str, Any] = {
        "place": place,
        "tied": False,
        "tie_unresolved": False,
        "group": "ranked",
        "start_id": uuid.uuid4(),
        "entry_id": entry or uuid.uuid4(),
        "start_number": number_,
        "attempt": 1,
        "display_name": f"Person {number_}",
        "club": None,
        "class_id": klass,
        "class_short": "O" if klass == OPEN else "D",
        "score": Decimal(score) if score is not None else None,
        "score_text": f"{score} Ringe" if score is not None else None,
        "complete": True,
        "tens": None,
        "inner_tens": None,
        "series": [],
        "status": "final",
        "abort_reason": None,
        "provisional_until": None,
    }
    values.update(fields)
    return RankingRow(**values)


def ranking(*groups: RankingGroup, combined: bool = False) -> RankingOut:
    return RankingOut(
        competition_id=COMPETITION.id,
        competition_name=COMPETITION.name,
        scope="final",
        include_provisional=True,
        merged=False,
        combined=combined,
        multi_start_rule="best",
        direction="absteigend",
        unit="Ringe",
        generated_at=NOW,
        groups=list(groups),
    )


def group(class_id: uuid.UUID | None, rows: list[RankingRow], members=None) -> RankingGroup:
    return RankingGroup(
        class_id=class_id,
        class_name=CLASS_NAMES.get(class_id) if class_id else None,
        class_short=None,
        class_ids=members or ([class_id] if class_id else [OPEN, LADIES]),
        rows=rows,
    )


# --- Schreibweisen -------------------------------------------------------------------------


def test_numbers_and_times() -> None:
    assert number(Decimal("75.20")) == "75,20"
    assert number(Decimal("-3.5")) == "-3,5"
    assert number(Decimal("-3.5"), typographic=True) == "−3,5"
    assert number(187) == "187"
    assert seconds(1284) == "12,84"
    assert seconds(900) == "9,00"


def test_date_ranges() -> None:
    assert date_range_de(date(2027, 3, 6), date(2027, 3, 6)) == "06.03.2027"
    assert date_range_de(date(2027, 3, 6), date(2027, 3, 7)) == "06.–07.03.2027"
    assert date_range_de(date(2027, 3, 30), date(2027, 4, 2)) == "30.03.–02.04.2027"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Vereinspokal 2027", "Vereinspokal-2027_Startliste_2027-03-06.pdf"),
        ("Königsschießen / Süd", "Koenigsschiessen-Sued_Startliste_2027-03-06.pdf"),
        ('a<b>:"c"|?*', "a-b-c_Startliste_2027-03-06.pdf"),
        ("Łódź Cup ıı", "Lodz-Cup-ii_Startliste_2027-03-06.pdf"),
        ("///", "Turnier_Startliste_2027-03-06.pdf"),
    ],
)
def test_file_names_are_safe(name: str, expected: str) -> None:
    assert file_name(name, "Startliste", date(2027, 3, 6), "pdf") == expected


# --- CSV -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dangerous", ["=SUMME(A1)", "+49 123", "-2+3", "@cmd", "\t=1", "  =HYPERLINK()", "＝1"]
)
def test_formula_injection_is_neutralized(dangerous: str) -> None:
    assert neutralize(dangerous) == f"'{dangerous}"


def test_harmless_text_and_numbers_stay() -> None:
    assert neutralize("Jürgen Maier") == "Jürgen Maier"
    assert neutralize("O'Brien") == "O'Brien"
    # Zahlen des Servers bleiben Zahlen, auch negative.
    assert cell_text(Decimal("-3.50")) == "-3,50"
    assert cell_text(12) == "12"
    assert cell_text(None) == ""


def test_csv_file_format() -> None:
    sheet = tables.Sheet(header=("Name", "Ergebnis", "Zeit"))
    sheet.rows.append(("=1+1", Decimal("92.5"), Decimal("12.84")))
    sheet.rows.append(("Müller; Sohn", 90, None))
    content = write_csv(sheet)
    assert content.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in content
    rows = read_csv(content)
    assert rows == [
        ["Name", "Ergebnis", "Zeit"],
        ["'=1+1", "92,5", "12,84"],
        ["Müller; Sohn", "90", ""],
    ]
    assert content.decode("utf-8-sig").splitlines()[1] == "'=1+1;92,5;12,84"


# --- Siegerliste aus der Rangliste ---------------------------------------------------------


def test_ties_order_and_aborted_at_end() -> None:
    rows = [
        ranking_row(1, 7, "95"),
        ranking_row(2, 3, "92", tied=True),
        ranking_row(2, 5, "92", tied=True),
        # Abgebrochene liefert die Rangliste ohne Platz am Ende (mit Teilergebnis).
        ranking_row(None, 9, "80", group="unranked", abort_reason="dnf", status="aborted"),
        ranking_row(None, 11, None, group="unranked", abort_reason="dns", status="aborted"),
        ranking_row(None, 12, None, group="unranked", abort_reason="dsq", status="aborted"),
    ]
    result = tables.winner_tables(ranking(group(OPEN, rows)), class_names=CLASS_NAMES)
    (table,) = result
    assert table.title == "Offene Klasse"
    assert [(r.place, r.start_number, r.group) for r in table.rows] == [
        (1, 7, "ranked"),
        (2, 3, "ranked"),
        (2, 5, "ranked"),
        (None, 9, "unranked"),
        (None, 11, "unranked"),
        (None, 12, "unranked"),
    ]
    report = tables.winners_report(META, [tables.winner_section(COMPETITION, "Ringe", result)])
    cells = [row.cells for row in report.sections[0].tables[0].rows]
    assert [c[0] for c in cells] == ["1.", "2.", "2.", "", "", ""]
    assert cells[3][-1] == "Abbruch (AB)"
    assert "80" not in cells[3]  # kein Teilergebnis bei Abgebrochenen
    assert cells[4][-1] == "nicht angetreten"
    assert cells[5][-1] == "disqualifiziert"
    assert report.sections[0].tables[0].rows[4].muted


def test_top_keeps_shared_places_and_drops_aborted() -> None:
    rows = [
        ranking_row(1, 1, "95"),
        ranking_row(2, 2, "92", tied=True),
        ranking_row(2, 3, "92", tied=True),
        ranking_row(4, 4, "90"),
    ]
    (table,) = tables.winner_tables(
        ranking(group(OPEN, [*rows, ranking_row(None, 9, None, group="unranked")])),
        class_names=CLASS_NAMES,
        top=2,
    )
    assert [r.start_number for r in table.rows] == [1, 2, 3]


def test_merged_title_and_class_column() -> None:
    rows = [ranking_row(1, 1, "95", klass=LADIES), ranking_row(2, 2, "90")]
    result = tables.winner_tables(
        ranking(group(OPEN, rows, members=[OPEN, LADIES])), class_names=CLASS_NAMES
    )
    assert result[0].title == "Offene Klasse (zusammengelegt mit Damenklasse)"
    assert result[0].mixed_classes
    report = tables.winners_report(META, [tables.winner_section(COMPETITION, "Ringe", result)])
    columns = [c.title for c in report.sections[0].tables[0].columns]
    assert "Klasse" in columns
    combined = tables.winner_tables(ranking(group(None, rows), combined=True), class_names={})
    assert combined[0].title == "Gemeinsame Wertung aller Klassen"


def test_names_public_and_full() -> None:
    entry = uuid.uuid4()
    rows = [
        ranking_row(1, 1, "95", entry=entry, display_name="D. Yılmaz", club=None),
        ranking_row(2, 2, "90", display_name=None, club=None),
    ]
    (public,) = tables.winner_tables(ranking(group(OPEN, rows)), class_names=CLASS_NAMES)
    assert [(r.person.name, r.person.club) for r in public.rows] == [
        ("D. Yılmaz", None),
        (None, None),
    ]
    full = {entry: PersonName("Deniz Yılmaz", "SV Nord")}
    (internal,) = tables.winner_tables(
        ranking(group(OPEN, rows)), class_names=CLASS_NAMES, full_names=full
    )
    assert internal.rows[0].person == PersonName("Deniz Yılmaz", "SV Nord")
    report = tables.winners_report(META, [tables.winner_section(COMPETITION, "Ringe", [public])])
    table = report.sections[0].tables[0]
    # Ohne Verein in der Liste keine Spalte „Verein“; ohne Namen „Startnummer N“ (wie der
    # Bildschirm).
    assert [c.title for c in table.columns][:3] == ["Platz", "Nr.", "Name"]
    assert "Verein" not in [c.title for c in table.columns]
    assert table.rows[1].cells[:3] == ("2.", "2", "Startnummer 2")


def test_series_struck_and_provisional_note() -> None:
    def part(number_: int, rings: int, struck: bool = False) -> SeriesPart:
        return SeriesPart(
            section_id="praezision",
            number=number_,
            struck=struck,
            status="normal",
            rings=rings,
            time_cs=None,
            standing=None,
            total_cs=None,
        )

    until = datetime(2027, 3, 6, 13, 35, tzinfo=UTC)
    rows = [
        ranking_row(
            1,
            1,
            "95",
            series=[part(1, 48), part(2, 47), part(3, 40, struck=True)],
            status="provisional",
            provisional_until=until,
            tens=5,
        ),
        ranking_row(2, 2, "90", series=[part(1, 45), part(2, 45)], tens=3),
    ]
    result = tables.winner_tables(ranking(group(OPEN, rows)), class_names=CLASS_NAMES)
    section = tables.winner_section(COMPETITION, "Ringe", result)
    assert section.provisional_until == until
    report = tables.winners_report(META, [section])
    rendered = report.sections[0]
    # 13:35 UTC = 14:35 Ortszeit (März, MEZ)
    assert rendered.notes == ("Vorläufig – Einspruchsfrist läuft bis 14:35 Uhr.",)
    table = rendered.tables[0]
    titles = [c.title for c in table.columns]
    assert titles == [
        "Platz",
        "Nr.",
        "Name",
        "Ergebnis (Ringe)",
        "10er",
        "S1",
        "S2",
        "S3",
        "Hinweis",
    ]
    assert table.rows[0].cells[5:8] == ("48", "47", "(40)")
    assert table.rows[0].cells[-1] == "vorläufig"  # nur eine von zwei Zeilen ist vorläufig
    assert table.rows[1].cells[-1] == ""
    assert tables.STRUCK_LEGEND in report.legend
    sheet = tables.winners_sheet([section])
    first = dict(zip(sheet.header, sheet.rows[0], strict=True))
    assert first["Teilwerte"] == "48; 47; (40)"
    assert first["Status"] == "vorläufig"
    assert first["Vorläufig bis"] == "2027-03-06 14:35"


def test_series_text_variants() -> None:
    def value(**fields: Any) -> SeriesValue:
        base = {
            "section_id": "a",
            "number": 1,
            "struck": False,
            "status": "normal",
            "rings": None,
            "time_cs": None,
            "standing": None,
            "total_cs": None,
        }
        return SeriesValue(**{**base, **fields})

    assert tables.series_text(value(rings=48)) == "48"
    assert tables.series_text(value(time_cs=1284)) == "12,84"
    assert tables.series_text(value(time_cs=1284, total_cs=1784)) == "17,84"
    assert tables.series_text(value(rings=48, time_cs=1000)) == "48 / 10,00"
    assert tables.series_text(value(rings=40, struck=True)) == "(40)"
    two = replace(COMPETITION, sections=(("a", "Präzision"), ("b", "Duell")))
    keys = tables.series_keys(two, [[value(section_id="b"), value(section_id="a", number=2)]])
    assert keys == [("a", 2), ("b", 1)]
    headers, legend = tables.series_headers(two, keys)
    assert headers == ["1.2", "2.1"]
    assert legend == "Serien: 1.x = Präzision, 2.x = Duell"


# --- Startliste ------------------------------------------------------------------------------


def start(number_: int, competition: CompetitionInfo, **fields: Any) -> StartRecord:
    values: dict[str, Any] = {
        "start_id": uuid.uuid4(),
        "entry_id": uuid.uuid4(),
        "start_number": number_,
        "person": PersonName(f"Person {number_}", None),
        "class_id": OPEN,
        "class_short": "O",
        "class_name": "Offene Klasse",
        "competition": competition,
        "attempt": 1,
        "status": "registered",
        "abort_reason": None,
        "queue_position": None,
        "heat_number": None,
        "heat_starts_at": None,
        "lane": None,
    }
    values.update(fields)
    return StartRecord(**values)


def test_startlist_sorting() -> None:
    other = CompetitionInfo(
        id=uuid.uuid4(),
        code="1002",
        name="Pistole über 9 mm",
        sort=2,
        range_id=uuid.uuid4(),
        range_name="Stand A",
        range_sort=0,
        multi_start=True,
        planning="queue",
    )
    records = [
        start(5, COMPETITION, queue_position=2),
        start(2, COMPETITION, queue_position=1),
        start(1, other, queue_position=1),
        start(2, other, queue_position=2, attempt=1),
    ]
    by_number = tables.sort_starts(records, "start_number")
    assert [(r.start_number, r.competition.code) for r in by_number] == [
        (1, "1002"),
        (2, "1001"),
        (2, "1002"),
        (5, "1001"),
    ]
    by_competition = tables.sort_starts(records, "competition")
    assert [(r.competition.code, r.start_number) for r in by_competition] == [
        ("1001", 2),
        ("1001", 5),
        ("1002", 1),
        ("1002", 2),
    ]
    by_range = tables.sort_starts(records, "range")
    assert [r.competition.range_name for r in by_range] == [
        "Stand A",
        "Stand A",
        "Stand 1",
        "Stand 1",
    ]
    report = tables.startlist_report(META, records, "competition")
    assert [s.title for s in report.sections] == [
        "1001 · Pistole bis 9 mm",
        "1002 · Pistole über 9 mm",
    ]
    assert report.sections[0].subtitle == "Schießstand: Stand 1 · 2 Starts"
    # Mehrfachstart nur im zweiten Wettbewerb: dort die Spalte „Versuch“.
    assert "Versuch" not in [c.title for c in report.sections[0].tables[0].columns]
    assert "Versuch" in [c.title for c in report.sections[1].tables[0].columns]
    empty = tables.startlist_report(META, [], "competition")
    assert empty.sections == ()
    assert empty.empty_text == tables.NO_STARTS


def test_resolved_tie_is_explained_in_note_column() -> None:
    note = "Ringgleichheit, entschieden nach: Anzahl der Zehner"
    rows = [
        ranking_row(1, 7, "92", tie_reason="resolved", tie_criterion="zehner", tie_note=note),
        ranking_row(2, 3, "92", tie_reason="resolved", tie_criterion="zehner", tie_note=note),
        ranking_row(3, 5, "90"),
    ]
    result = tables.winner_tables(ranking(group(OPEN, rows)), class_names=CLASS_NAMES)
    report = tables.winners_report(META, [tables.winner_section(COMPETITION, "Ringe", result)])
    cells = [row.cells for row in report.sections[0].tables[0].rows]
    assert [c[-1] for c in cells] == [note, note, ""]


def test_note_column_uses_long_tie_note() -> None:
    short = "Ringgleichheit, entschieden nach: letzte Zehnerserie"
    long = f"{short}, dann rückwärts in 10-Schuss-Serien (Wurfscheibe: je Serie)"
    tie = {
        "tie_reason": "resolved",
        "tie_criterion": "letzte_serie_rueckwaerts",
        "tie_note": short,
        "tie_note_long": long,
    }
    rows = [ranking_row(1, 7, "190", **tie), ranking_row(2, 3, "190", **tie)]
    result = tables.winner_tables(ranking(group(OPEN, rows)), class_names=CLASS_NAMES)
    report = tables.winners_report(META, [tables.winner_section(COMPETITION, "Ringe", result)])
    cells = [row.cells for row in report.sections[0].tables[0].rows]
    assert [c[-1] for c in cells] == [long, long]
