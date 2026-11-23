"""Listen mit den Wörtern des Verbands je Wettbewerb, Einheit „Treffer“, Höchstergebnis und keine
Bemerkung zum Abbruch in öffentlichen Ausgaben."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from app.core.begriffe import begriffe_fuer
from app.modules.export import tables
from app.modules.export.records import PersonName, StartRecord
from tests.export.test_tables import (
    CLASS_NAMES,
    COMPETITION,
    META,
    OPEN,
    group,
    ranking,
    ranking_row,
)

DSB = replace(COMPETITION, id=uuid.uuid4(), code="1.10", name="Luftgewehr", federation="dsb")
BDS = replace(COMPETITION, federation="bds")


def _section(competition, rows, unit="Ringe", tie_word="Ringgleichheit"):  # type: ignore[no-untyped-def]
    found = tables.winner_tables(ranking(group(OPEN, rows)), class_names=CLASS_NAMES)
    return tables.winner_section(competition, unit, found, tie_word=tie_word)


def test_title_and_range_word_per_federation() -> None:
    report = tables.winners_report(META, [_section(DSB, [ranking_row(1, 1, "95")])])
    assert report.title == begriffe_fuer("dsb").ergebnisliste
    assert report.sections[0].subtitle == f"{begriffe_fuer('dsb').schiessstand}: Stand 1"


def test_mixed_federations_use_standard_title() -> None:
    sections = [
        _section(DSB, [ranking_row(1, 1, "95")]),
        _section(BDS, [ranking_row(1, 2, "95")]),
    ]
    assert tables.winners_report(META, sections).title == begriffe_fuer(None).ergebnisliste


def test_hits_unit_in_column_title() -> None:
    report = tables.winners_report(META, [_section(DSB, [ranking_row(1, 1, "20")], "Treffer")])
    titles = [column.title for column in report.sections[0].tables[0].columns]
    assert "Ergebnis (Treffer)" in titles


def test_max_score_note_and_dsb_tie_word_in_lists() -> None:
    rows = [
        ranking_row(
            1,
            1,
            "654.0",
            tied=True,
            tie_reason="max_score",
            tie_note="Höchstergebnis: gleicher Platz",
        ),
        ranking_row(
            1,
            2,
            "654.0",
            tied=True,
            tie_reason="max_score",
            tie_note="Höchstergebnis: gleicher Platz",
        ),
    ]
    section = _section(DSB, rows, tie_word="Ergebnisgleichheit")
    report = tables.winners_report(META, [section])
    cells = [row.cells for row in report.sections[0].tables[0].rows]
    assert cells[0][-1] == "Höchstergebnis: gleicher Platz"
    sheet = tables.winners_sheet([section])
    tie_column = sheet.header.index("Gleichheit")
    assert {row[tie_column] for row in sheet.rows} == {"Ergebnisgleichheit"}


def test_abort_label_comes_from_ranking_and_remark_stays_private() -> None:
    row = ranking_row(
        None,
        9,
        None,
        group="unranked",
        abort_reason="dnf",
        status="aborted",
        abort_label="abgebrochen",
        abort_remark="Waffendefekt",
    )
    report = tables.winners_report(META, [_section(DSB, [row])])
    cells = report.sections[0].tables[0].rows[0].cells
    assert "abgebrochen" in cells[-1]
    assert not any("Waffendefekt" in cell for cell in cells)
    sheet = tables.winners_sheet([_section(DSB, [row])])
    assert not any("Waffendefekt" in str(cell) for cell in sheet.rows[0])


def _start(competition, lane: int | None = 3) -> StartRecord:  # type: ignore[no-untyped-def]
    return StartRecord(
        start_id=uuid.uuid4(),
        entry_id=uuid.uuid4(),
        start_number=1,
        person=PersonName("Person 1", None),
        class_id=OPEN,
        class_short="O",
        class_name="Offene Klasse",
        competition=competition,
        attempt=1,
        status="aborted",
        abort_reason="dnf",
        queue_position=None,
        heat_number=1,
        heat_starts_at=datetime(2027, 3, 6, 9, 0, tzinfo=UTC),
        lane=lane,
    )


def test_startlist_words_per_federation() -> None:
    dsb = begriffe_fuer("dsb")
    report = tables.startlist_report(META, [_start(DSB)], "competition")
    columns = [column.title for column in report.sections[0].tables[0].columns]
    assert dsb.schuetzenstand in columns
    assert report.sections[0].tables[0].rows[0].cells[-1] == dsb.abbruch
    sheet = tables.startlist_sheet([_start(DSB)], "competition")
    assert sheet.rows[0][-1] == dsb.abbruch
    bds_sheet = tables.startlist_sheet([_start(BDS)], "competition")
    assert bds_sheet.rows[0][-1] == "Abbruch (AB)"
