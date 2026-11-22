"""Aufbereitung: aus den Daten (`records.py`) werden neutrale Tabellen.

Alles hier ist rein (keine Datenbank, keine Ausgabe) und deshalb direkt testbar.

- `Report`: gegliedert für das PDF (Abschnitte je Wettbewerb oder Stand, darin Tabellen mit
  fertig formatiertem Text).
- `Sheet`: flach für die CSV-Datei (eine Kopfzeile, Zellen als Text, Zahl oder leer; die
  Zahlenschreibweise und den Schutz vor Formeln übernimmt `csvout.py`).

Rangfolge, Gleichstand, Mehrfachstart und Klassen kommen fertig aus der Rangliste des Moduls
`ergebnisse` (`winner_tables` ordnet nur zu, filtert und ergänzt die Abbrüche).
"""

import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.modules.ergebnisse.schemas import RankingOut, RankingRow
from app.modules.export.formatting import (
    ABORT_LABELS,
    ROW_STATUS_LABELS,
    START_STATUS_LABELS,
    clock,
    date_de,
    iso_local,
    local,
    number,
    seconds,
)
from app.modules.export.records import (
    CompetitionInfo,
    Meta,
    PersonName,
    ResultRecord,
    SeriesValue,
    StartlistSort,
    StartRecord,
    WinnerRow,
    WinnerSection,
    WinnerTable,
)
from app.modules.starts.schemas import StationStartOut
from app.scoring.numbers import cs_to_seconds

Align = Literal["left", "right", "center"]
Cell = str | int | Decimal | None

NO_STARTS = "Für diese Auswahl gibt es keine Starts."
NO_RESULTS = "Für diese Auswahl gibt es noch keine Ergebnisse."
STRUCK_LEGEND = "Werte in Klammern: gestrichene Serie (zählt nicht zum Ergebnis)."


# --- Neutrale Strukturen -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Column:
    title: str
    align: Align = "left"
    # Darf im PDF umbrechen (Name, Verein); andere Spalten bekommen ihre volle Breite.
    wrap: bool = False


@dataclass(frozen=True, slots=True)
class Row:
    cells: tuple[str, ...]
    # Abgebrochene Starts: im PDF grau.
    muted: bool = False


@dataclass(frozen=True, slots=True)
class Table:
    title: str | None
    columns: tuple[Column, ...]
    rows: tuple[Row, ...]
    empty_text: str | None = None


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    subtitle: str | None = None
    # Hinweise über den Tabellen, z. B. „vorläufig – Einspruchsfrist läuft bis 14:35 Uhr“.
    notes: tuple[str, ...] = ()
    tables: tuple[Table, ...] = ()


@dataclass(frozen=True, slots=True)
class Report:
    title: str
    meta: Meta
    sections: tuple[Section, ...]
    # Erklärungen am Ende (Klammern = gestrichen, Serien-Nummerierung).
    legend: tuple[str, ...] = ()
    # Steht da, wenn es keine Abschnitte gibt.
    empty_text: str = NO_STARTS


@dataclass(slots=True)
class Sheet:
    header: tuple[str, ...]
    rows: list[tuple[Cell, ...]] = field(default_factory=list)


# --- Namen ---------------------------------------------------------------------------


def person_for(
    entry_id: uuid.UUID,
    public_name: str | None,
    public_club: str | None,
    full_names: Mapping[uuid.UUID, PersonName] | None,
) -> PersonName:
    """Öffentlich (`full_names=None`): wie die Sicht es liefert, also nach Anzeige-Einstellung.
    Intern: voller Name und Verein aus `full_names`."""
    if full_names is None:
        return PersonName(public_name, public_club)
    return full_names.get(entry_id, PersonName(public_name, public_club))


# --- Siegerliste: Zuordnung --------------------------------------------------------------


def _series(row: RankingRow) -> tuple[SeriesValue, ...]:
    return tuple(
        SeriesValue(
            section_id=part.section_id,
            number=part.number,
            struck=part.struck,
            status=part.status,
            rings=part.rings,
            time_cs=part.time_cs,
            standing=part.standing,
            total_cs=part.total_cs,
        )
        for part in row.series
    )


def _winner_row(row: RankingRow, person: PersonName) -> WinnerRow:
    return WinnerRow(
        place=row.place,
        tied=row.tied,
        tie_unresolved=row.tie_unresolved,
        group=row.group,
        entry_id=row.entry_id,
        start_number=row.start_number,
        attempt=row.attempt,
        person=person,
        class_id=row.class_id,
        class_short=row.class_short,
        score=row.score,
        complete=row.complete,
        tens=row.tens,
        inner_tens=row.inner_tens,
        series=_series(row),
        status=row.status,
        abort_reason=row.abort_reason,
        provisional_until=row.provisional_until,
    )


def _aborted_row(start: StationStartOut, person: PersonName) -> WinnerRow:
    return WinnerRow(
        place=None,
        tied=False,
        tie_unresolved=False,
        group="aborted",
        entry_id=start.entry_id,
        start_number=start.start_number,
        attempt=start.attempt,
        person=person,
        class_id=start.class_id,
        class_short=start.class_short,
        score=None,
        complete=False,
        tens=None,
        inner_tens=None,
        series=(),
        status="aborted",
        abort_reason=start.abort_reason,
        provisional_until=None,
    )


def winner_tables(
    ranking: RankingOut,
    aborted: Sequence[StationStartOut],
    *,
    class_names: Mapping[uuid.UUID, str],
    top: int | None = None,
    class_id: uuid.UUID | None = None,
    full_names: Mapping[uuid.UUID, PersonName] | None = None,
) -> list[WinnerTable]:
    """Tabellen der Siegerliste eines Wettbewerbs aus seiner Rangliste.

    - Reihenfolge, Plätze und geteilte Plätze bleiben, wie die Rangliste sie liefert.
    - `top`: nur Zeilen mit Platz bis `top` (bei geteiltem Platz alle Gleichen); ohne `top` alle
      Platzierten, danach Zeilen ohne Platz und am Ende „nicht angetreten“/„disqualifiziert“
      (die die Rangliste selbst nicht führt) – je Teilnehmer einmal, und nur, wenn er nicht
      schon mit einem anderen Start in der Liste steht.
    """
    tables = []
    for group in ranking.groups:
        rows = [
            _winner_row(row, person_for(row.entry_id, row.display_name, row.club, full_names))
            for row in group.rows
        ]
        if top is not None:
            rows = [row for row in rows if row.place is not None and row.place <= top]
        else:
            members = set(group.class_ids)
            present = {row.entry_id for row in rows}
            extras: dict[uuid.UUID, WinnerRow] = {}
            for start in sorted(aborted, key=lambda s: (s.start_number, s.attempt)):
                if start.status != "aborted" or start.abort_reason not in ("dns", "dsq"):
                    continue
                if group.class_id is not None and start.class_id not in members:
                    continue
                if class_id is not None and start.class_id != class_id:
                    continue
                if start.entry_id in present or start.entry_id in extras:
                    continue
                person = person_for(start.entry_id, start.display_name, start.club, full_names)
                extras[start.entry_id] = _aborted_row(start, person)
            rows.extend(extras.values())
        if group.class_id is None:
            title = "Gemeinsame Wertung aller Klassen"
        else:
            title = class_names.get(group.class_id) or group.class_name or "Klasse"
            others = [
                class_names.get(other, "?") for other in group.class_ids if other != group.class_id
            ]
            if others:
                title += f" (zusammengelegt mit {', '.join(sorted(others))})"
        tables.append(
            WinnerTable(
                class_id=group.class_id,
                title=title,
                rows=tuple(rows),
                mixed_classes=group.class_id is None or len(set(group.class_ids)) > 1,
            )
        )
    return tables


def winner_section(
    competition: CompetitionInfo, unit: str | None, tables: Sequence[WinnerTable]
) -> WinnerSection:
    pending = [
        row.provisional_until
        for table in tables
        for row in table.rows
        if row.status == "provisional" and row.provisional_until is not None
    ]
    return WinnerSection(
        competition=competition,
        unit=unit,
        tables=tuple(tables),
        provisional_until=max(pending) if pending else None,
    )


# --- Serien --------------------------------------------------------------------------


def series_text(value: SeriesValue, *, typographic: bool = True) -> str:
    """Ringe, Zeit (mit Zuschlag) oder beides; gestrichene Serien in Klammern."""
    parts = []
    if value.rings is not None:
        parts.append(str(value.rings))
    time = value.total_cs if value.total_cs is not None else value.time_cs
    if time is not None:
        parts.append(seconds(time, typographic=typographic))
    text = " / ".join(parts) or "–"
    return f"({text})" if value.struck else text


SeriesKey = tuple[str, int]


def series_keys(
    competition: CompetitionInfo, series_lists: Iterable[Sequence[SeriesValue]]
) -> list[SeriesKey]:
    """Alle vorkommenden Serien in der Reihenfolge der Abschnitte, dann nach Nummer."""
    order = {section_id: index for index, (section_id, _) in enumerate(competition.sections)}
    keys = {(value.section_id, value.number) for values in series_lists for value in values}
    return sorted(keys, key=lambda key: (order.get(key[0], len(order)), key[0], key[1]))


def series_headers(
    competition: CompetitionInfo, keys: Sequence[SeriesKey]
) -> tuple[list[str], str | None]:
    """Spaltenköpfe „S1“, „S2“ … bzw. bei mehreren Abschnitten „1.1“, „2.1“ mit Legende."""
    sections: list[str] = []
    for section_id, _ in keys:
        if section_id not in sections:
            sections.append(section_id)
    if len(sections) <= 1:
        return [f"S{number_}" for _, number_ in keys], None
    names = dict(competition.sections)
    headers = [f"{sections.index(section_id) + 1}.{number_}" for section_id, number_ in keys]
    legend = "Serien: " + ", ".join(
        f"{index + 1}.x = {names.get(section_id, section_id)}"
        for index, section_id in enumerate(sections)
    )
    return headers, legend


# --- Siegerliste: Tabellen -------------------------------------------------------------


def _place_text(row: WinnerRow) -> str:
    return f"{row.place}." if row.place is not None else ""


def _row_notes(row: WinnerRow, mark_provisional: bool) -> list[str]:
    notes = []
    if row.abort_reason is not None:
        notes.append(ABORT_LABELS.get(row.abort_reason, row.abort_reason))
    elif row.status == "review":
        notes.append("prüfen")
    elif not row.complete and row.group == "last":
        notes.append("unvollständig")
    if row.tie_unresolved:
        notes.append("Gleichstand nicht auflösbar")
    if mark_provisional and row.status == "provisional":
        notes.append("vorläufig")
    return notes


def provisional_note(until: datetime, meta: Meta) -> str:
    """Hinweis über der Tabelle; das Datum nur, wenn der Tag nicht eindeutig ist."""
    local_day = local(until).date()
    when = f"{clock(until)} Uhr"
    if meta.date_from != meta.date_to or local_day != meta.date_from:
        when = f"{date_de(local_day)}, {when}"
    return f"Vorläufig – Einspruchsfrist läuft bis {when}."


def winners_report(meta: Meta, sections: Sequence[WinnerSection]) -> Report:
    legends: list[str] = []
    out: list[Section] = []
    for section in sections:
        competition = section.competition
        all_rows = [row for table in section.tables for row in table.rows]
        keys = series_keys(competition, (row.series for row in all_rows))
        headers, legend = series_headers(competition, keys)
        if legend and legend not in legends:
            legends.append(legend)
        struck = any(value.struck for row in all_rows for value in row.series)
        if struck and STRUCK_LEGEND not in legends:
            legends.append(STRUCK_LEGEND)
        with_club = any(row.person.club for row in all_rows)
        with_class = any(table.mixed_classes for table in section.tables)
        with_attempt = competition.multi_start
        with_tens = any(row.tens is not None for row in all_rows)
        with_inner = any(row.inner_tens is not None for row in all_rows)
        result_title = f"Ergebnis ({section.unit})" if section.unit else "Ergebnis"

        def notes_of(table: WinnerTable) -> Callable[[WinnerRow], list[str]]:
            # „vorläufig“ je Zeile nur, wenn nicht ohnehin die ganze Tabelle vorläufig ist.
            mixed = len({row.status == "provisional" for row in table.rows}) > 1
            return lambda row: _row_notes(row, mixed)

        with_notes = any(notes_of(t)(row) for t in section.tables for row in t.rows)
        columns = [Column("Platz", "right"), Column("Nr.", "right"), Column("Name", wrap=True)]
        if with_club:
            columns.append(Column("Verein", wrap=True))
        if with_class:
            columns.append(Column("Klasse"))
        if with_attempt:
            columns.append(Column("Versuch", "right"))
        columns.append(Column(result_title, "right"))
        if with_tens:
            columns.append(Column("10er", "right"))
        if with_inner:
            columns.append(Column("X", "right"))
        columns.extend(Column(header, "right") for header in headers)
        if with_notes:
            columns.append(Column("Hinweis", wrap=True))

        tables = []
        for table in section.tables:
            notes = notes_of(table)
            rows = []
            for row in table.rows:
                by_key = {(value.section_id, value.number): value for value in row.series}
                cells = [_place_text(row), str(row.start_number), row.person.name or ""]
                if with_club:
                    cells.append(row.person.club or "")
                if with_class:
                    cells.append(row.class_short)
                if with_attempt:
                    cells.append(str(row.attempt))
                cells.append(number(row.score, typographic=True) if row.score is not None else "–")
                if with_tens:
                    cells.append(str(row.tens) if row.tens is not None else "")
                if with_inner:
                    cells.append(str(row.inner_tens) if row.inner_tens is not None else "")
                cells.extend(series_text(by_key[key]) if key in by_key else "" for key in keys)
                if with_notes:
                    cells.append(", ".join(notes(row)))
                rows.append(Row(tuple(cells), muted=row.abort_reason is not None))
            tables.append(
                Table(
                    title=table.title,
                    columns=tuple(columns),
                    rows=tuple(rows),
                    empty_text="Noch keine abgeschlossenen Ergebnisse.",
                )
            )
        notes_text = (
            (provisional_note(section.provisional_until, meta),)
            if section.provisional_until is not None
            else ()
        )
        subtitle = f"Stand: {competition.range_name}" if competition.range_name else None
        out.append(Section(competition.title, subtitle, notes_text, tuple(tables)))
    return Report(
        title="Siegerliste",
        meta=meta,
        sections=tuple(out),
        legend=tuple(legends),
        empty_text=NO_RESULTS,
    )


def _status_cell(row: WinnerRow) -> str:
    if row.abort_reason is not None:
        return ABORT_LABELS.get(row.abort_reason, row.abort_reason)
    return ROW_STATUS_LABELS.get(row.status, row.status)


def winners_sheet(sections: Sequence[WinnerSection]) -> Sheet:
    sheet = Sheet(
        header=(
            "Kennziffer",
            "Wettbewerb",
            "Wertung",
            "Platz",
            "Platz geteilt",
            "Startnummer",
            "Name",
            "Verein",
            "Klasse",
            "Versuch",
            "Ergebnis",
            "Einheit",
            "Zehner",
            "Innenzehner",
            "Teilwerte",
            "Status",
            "Vorläufig bis",
        )
    )
    for section in sections:
        competition = section.competition
        keys = series_keys(
            competition, (row.series for table in section.tables for row in table.rows)
        )
        for table in section.tables:
            for row in table.rows:
                by_key = {(value.section_id, value.number): value for value in row.series}
                parts = [
                    series_text(by_key[key], typographic=False) for key in keys if key in by_key
                ]
                sheet.rows.append(
                    (
                        competition.code,
                        competition.name,
                        table.title,
                        row.place,
                        "ja" if row.tied else "",
                        row.start_number,
                        row.person.name,
                        row.person.club,
                        row.class_short,
                        row.attempt,
                        row.score,
                        section.unit if row.score is not None else None,
                        row.tens,
                        row.inner_tens,
                        "; ".join(parts) or None,
                        _status_cell(row),
                        iso_local(row.provisional_until)
                        if row.status == "provisional" and row.provisional_until
                        else None,
                    )
                )
    return sheet


# --- Startliste --------------------------------------------------------------------------

_LAST = 1 << 30


def _when(record: StartRecord) -> float:
    return record.heat_starts_at.timestamp() if record.heat_starts_at else float("inf")


def _competition_key(record: StartRecord) -> tuple[object, ...]:
    return (record.competition.sort, record.competition.name, str(record.competition.id))


def startlist_sort_key(sort: StartlistSort) -> Callable[[StartRecord], tuple[object, ...]]:
    """Reihenfolge der Startliste.

    - `competition`: je Wettbewerb in der Reihenfolge am Stand (Durchgang, Bahn, Reihenfolge),
      dann Startnummer und Versuch – wie die Startliste des Moduls `starts`.
    - `start_number`: nach Startnummer, dann Wettbewerb und Versuch.
    - `range`: je Stand nach Uhrzeit, Bahn und Wettbewerb.
    """

    def by_course(record: StartRecord) -> tuple[object, ...]:
        return (
            _when(record),
            record.lane if record.lane is not None else _LAST,
            record.queue_position if record.queue_position is not None else _LAST,
            record.start_number,
            record.attempt,
        )

    match sort:
        case "start_number":
            return lambda r: (r.start_number, *_competition_key(r), r.attempt)
        case "range":
            return lambda r: (
                r.competition.range_sort if r.competition.range_sort is not None else _LAST,
                r.competition.range_name or "",
                str(r.competition.range_id),
                _when(r),
                r.lane if r.lane is not None else _LAST,
                *_competition_key(r),
                r.queue_position if r.queue_position is not None else _LAST,
                r.start_number,
                r.attempt,
            )
        case _:
            return lambda r: (*_competition_key(r), *by_course(r))


def sort_starts(records: Iterable[StartRecord], sort: StartlistSort) -> list[StartRecord]:
    return sorted(records, key=startlist_sort_key(sort))


def _heat_text(record: StartRecord, meta: Meta) -> str:
    if record.heat_starts_at is None:
        return ""
    when = clock(record.heat_starts_at)
    if meta.date_from != meta.date_to:
        when = f"{local(record.heat_starts_at).strftime('%d.%m.')} {when}"
    return f"{record.heat_number} ({when})" if record.heat_number is not None else when


def _startlist_table(
    meta: Meta, records: Sequence[StartRecord], *, with_competition: bool
) -> Table:
    with_heat = any(r.heat_starts_at is not None for r in records)
    with_lane = any(r.lane is not None for r in records)
    with_club = any(r.person.club for r in records)
    with_attempt = any(r.competition.multi_start for r in records)
    with_notes = any(r.status == "aborted" for r in records)
    columns: list[Column] = []
    if with_heat:
        columns.append(Column("Durchgang"))
    if with_lane:
        columns.append(Column("Bahn", "right"))
    columns += [Column("Nr.", "right"), Column("Name", wrap=True)]
    if with_club:
        columns.append(Column("Verein", wrap=True))
    columns.append(Column("Klasse"))
    if with_competition:
        columns.append(Column("Wettbewerb", wrap=True))
    if with_attempt:
        columns.append(Column("Versuch", "right"))
    if with_notes:
        columns.append(Column("Hinweis"))
    rows = []
    for record in records:
        cells: list[str] = []
        if with_heat:
            cells.append(_heat_text(record, meta))
        if with_lane:
            cells.append(str(record.lane) if record.lane is not None else "")
        cells += [str(record.start_number), record.person.name or ""]
        if with_club:
            cells.append(record.person.club or "")
        cells.append(record.class_short)
        if with_competition:
            cells.append(record.competition.title)
        if with_attempt:
            cells.append(str(record.attempt))
        if with_notes:
            cells.append(
                ABORT_LABELS.get(record.abort_reason or "", "abgebrochen")
                if record.status == "aborted"
                else ""
            )
        rows.append(Row(tuple(cells), muted=record.status == "aborted"))
    return Table(title=None, columns=tuple(columns), rows=tuple(rows), empty_text=NO_STARTS)


def startlist_report(meta: Meta, records: Sequence[StartRecord], sort: StartlistSort) -> Report:
    ordered = sort_starts(records, sort)
    sections: list[Section] = []
    if sort == "start_number":
        if ordered:
            table = _startlist_table(meta, ordered, with_competition=True)
            sections.append(Section("Alle Starts nach Startnummer", tables=(table,)))
    else:
        groups: dict[object, list[StartRecord]] = {}
        for record in ordered:
            key = record.competition.id if sort == "competition" else record.competition.range_id
            groups.setdefault(key, []).append(record)
        for members in groups.values():
            competition = members[0].competition
            if sort == "competition":
                title = competition.title
                subtitle = f"Stand: {competition.range_name}" if competition.range_name else None
                with_competition = False
            else:
                title = competition.range_name or "Ohne Stand"
                subtitle = None
                with_competition = True
            table = _startlist_table(meta, members, with_competition=with_competition)
            count = len(members)
            info = f"{count} {'Start' if count == 1 else 'Starts'}"
            subtitle = f"{subtitle} · {info}" if subtitle else info
            sections.append(Section(title, subtitle, tables=(table,)))
    return Report(title="Startliste", meta=meta, sections=tuple(sections), empty_text=NO_STARTS)


def startlist_sheet(records: Sequence[StartRecord], sort: StartlistSort) -> Sheet:
    sheet = Sheet(
        header=(
            "Startnummer",
            "Name",
            "Verein",
            "Klasse",
            "Klassenname",
            "Kennziffer",
            "Wettbewerb",
            "Stand",
            "Versuch",
            "Durchgang",
            "Beginn",
            "Bahn",
            "Reihenfolge",
            "Status",
            "Abbruchgrund",
        )
    )
    for record in sort_starts(records, sort):
        sheet.rows.append(
            (
                record.start_number,
                record.person.name,
                record.person.club,
                record.class_short,
                record.class_name,
                record.competition.code,
                record.competition.name,
                record.competition.range_name,
                record.attempt,
                record.heat_number,
                iso_local(record.heat_starts_at) if record.heat_starts_at else None,
                record.lane,
                record.queue_position,
                START_STATUS_LABELS.get(record.status, record.status),
                ABORT_LABELS.get(record.abort_reason) if record.abort_reason else None,
            )
        )
    return sheet


# --- Rohexport der Ergebnisse ------------------------------------------------------------

# Teilwerte je Serie in festen Spalten: „Serie <n> <Feld>“. Die Serien sind über alle Abschnitte
# der Disziplin fortlaufend nummeriert (Abschnitt 1: Serie 1–4, Abschnitt 2: Serie 5–8 …).
# Es erscheinen nur Felder, die in der Datei überhaupt vorkommen.
SERIES_FIELDS: tuple[tuple[str, Callable[[SeriesValue], Cell]], ...] = (
    ("Ringe", lambda s: s.rings),
    ("Zeit", lambda s: cs_to_seconds(s.time_cs) if s.time_cs is not None else None),
    ("Zeit mit Zuschlag", lambda s: cs_to_seconds(s.total_cs) if s.total_cs is not None else None),
    ("Stehend", lambda s: s.standing),
)


def _ordered_series(record: ResultRecord) -> list[SeriesValue]:
    keys = series_keys(record.start.competition, [record.series])
    by_key = {(value.section_id, value.number): value for value in record.series}
    return [by_key[key] for key in keys]


def results_sheet(records: Sequence[ResultRecord]) -> Sheet:
    ordered = [_ordered_series(record) for record in records]
    width = max((len(series) for series in ordered), default=0)
    used = [
        (index, label, getter)
        for index in range(width)
        for label, getter in SERIES_FIELDS
        if any(index < len(series) and getter(series[index]) is not None for series in ordered)
    ]
    header = (
        "Startnummer",
        "Name",
        "Verein",
        "Klasse",
        "Kennziffer",
        "Wettbewerb",
        "Versuch",
        "Status",
        "Abbruchgrund",
        "Ergebnis",
        "Einheit",
        "Vollständig",
        "Zehner",
        "Innenzehner",
        "Abgeschlossen am",
        "Vorläufig bis",
        "Prüfen",
        "Gestrichene Serien",
        "Serienstatus",
        *(f"Serie {index + 1} {label}" for index, label, _ in used),
    )
    sheet = Sheet(header=header)
    for record, series in zip(records, ordered, strict=True):
        start = record.start
        struck = [str(i + 1) for i, value in enumerate(series) if value.struck]
        special = [
            f"{i + 1}: {value.status}" for i, value in enumerate(series) if value.status != "normal"
        ]
        cells: list[Cell] = [
            start.start_number,
            start.person.name,
            start.person.club,
            start.class_short,
            start.competition.code,
            start.competition.name,
            start.attempt,
            START_STATUS_LABELS.get(start.status, start.status),
            ABORT_LABELS.get(start.abort_reason) if start.abort_reason else None,
            record.score if record.has_result else None,
            record.unit if record.has_result else None,
            ("ja" if record.complete else "nein") if record.has_result else None,
            record.tens,
            record.inner_tens,
            iso_local(record.finalized_at) if record.finalized_at else None,
            iso_local(record.provisional_until) if record.is_provisional else None,
            "ja" if record.needs_review else None,
            ", ".join(struck) or None,
            "; ".join(special) or None,
        ]
        for index, _, getter in used:
            cells.append(getter(series[index]) if index < len(series) else None)
        sheet.rows.append(tuple(cells))
    return sheet
