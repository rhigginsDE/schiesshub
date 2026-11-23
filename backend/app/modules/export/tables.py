"""Aufbereitung: aus den Daten (`records.py`) werden neutrale Tabellen.

Alles hier ist rein (keine Datenbank, keine Ausgabe) und deshalb direkt testbar.

- `Report`: gegliedert für das PDF (Abschnitte je Wettbewerb oder Stand, darin Tabellen mit
  fertig formatiertem Text).
- `Sheet`: flach für die CSV-Datei (eine Kopfzeile, Zellen als Text, Zahl oder leer; die
  Zahlenschreibweise und den Schutz vor Formeln übernimmt `csvout.py`).

Rangfolge, Gleichheit, Mehrfachstart, Klassen und Abbrüche kommen fertig aus der Rangliste des
Moduls `ergebnisse` (`winner_tables` ordnet nur zu und kürzt auf `top`). Ein Abbruch nach dem
Kommando „Feuer“ hat dort einen Platz und ein Ergebnis wie jeder andere Start (Sporthandbuch
K 1.14 / L 1.12), gekennzeichnet mit „Abbruch (AB)“. Abgebrochene ohne Platz stehen am Ende
ihrer Gruppe; hier bekommen sie kein Ergebnis, nur den Grund.

Interne Schlüssel (Status, Abbruchgrund, Ablauf einer Serie) erscheinen nie in einer Liste; die
deutschen Texte kommen aus `formatting.py`, die formellen Wörter (Ergebnisliste, Abbruch (AB),
Schützenstand, Schießstand, Ringgleichheit) aus dem Begriffssatz des Verbands
(`app.modules.ergebnisse.begriffe`): je Wettbewerb der seines Verbands
(`CompetitionInfo.federation`); für Teile über mehrere Wettbewerbe (Dokumenttitel, Spaltenköpfe
einer gemischten Tabelle, CSV-Kopfzeile) der gemeinsame Satz, bei gemischten Verbänden der
Standardsatz.
"""

import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from app.core.begriffe import Begriffe
from app.modules.ergebnisse import begriffe
from app.modules.ergebnisse.schemas import RankingOut, RankingRow
from app.modules.export.formatting import (
    abort_text,
    clock,
    date_de,
    iso_local,
    local,
    number,
    row_status_text,
    seconds,
    series_status_text,
    start_status_text,
)
from app.modules.export.records import (
    TIME_MODELS,
    CompetitionInfo,
    Meta,
    PersonName,
    ResultRecord,
    SeriesValue,
    StartlistSort,
    StartRecord,
    TimedSection,
    TimeScore,
    WinnerRow,
    WinnerSection,
    WinnerTable,
)
from app.scoring import ComputedResult
from app.scoring.numbers import cs_to_seconds, format_seconds_value

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


def name_text(person: PersonName, start_number: int) -> str:
    """Name für die Liste; ohne Namensanzeige („nicht anzeigen“) wie auf dem Bildschirm
    „Startnummer 5“ statt eines leeren Felds."""
    return person.name or f"Startnummer {start_number}"


# --- Rechenweg bei Wertung mit Zeit ------------------------------------------------------


def time_score_of(computed: ComputedResult, competition: CompetitionInfo) -> TimeScore | None:
    """Zeit, Sollzeit und Abzug aus der Wertung des Servers; None bei Modellen ohne Zeitabzug.

    Hier wird nichts neu gerechnet: Abzüge und Zeiten stehen so in `computed`; nur bei
    `ringe_minus_zeit` ergibt sich der Abzug als Ringe − Ergebnis.
    """
    if computed.model not in TIME_MODELS:
        return None
    if computed.model == "ringe_minus_zeit":
        deduction = Decimal(computed.rings) - computed.score if computed.rings is not None else None
        return TimeScore(
            model=computed.model,
            rings=computed.rings,
            time_cs=computed.time_cs,
            target_s=None,
            deduction=deduction,
            rounded=competition.time_rounding == "summe_abrunden",
        )
    targets = dict(competition.target_times)
    timed = tuple(
        TimedSection(
            name=section.name,
            time_cs=section.time_cs,
            target_s=targets[section.id],
            deduction=section.deduction,
            floored=section.floored,
            result=section.result,
        )
        for section in computed.sections
        if section.id in targets
    )
    times = [section.time_cs for section in timed]
    deductions = [section.deduction for section in timed]
    return TimeScore(
        model=computed.model,
        rings=computed.rings,
        time_cs=sum(t for t in times if t is not None) if timed and None not in times else None,
        target_s=timed[0].target_s if len(timed) == 1 else None,
        deduction=sum((d for d in deductions if d is not None), Decimal(0))
        if timed and None not in deductions
        else None,
        sections=timed,
    )


NBSP = "\u00a0"


def time_score_text(score: TimeScore) -> str:
    """Kurzer Rechenweg für das PDF: „339 − 13 (93,40 s, Sollzeit 80 s)“ (Mehrdistanz) bzw.
    „182 − 19 (19,87 s, abgerundet)“ (Speed). Das Ergebnis steht in seiner eigenen Spalte.

    Geschützte Leerzeichen halten Zahl und Einheit („93,40 s“), „Sollzeit 80 s“ und „− 13“
    zusammen; muss die Zelle umbrechen, dann nur zwischen diesen Teilen."""
    rings = number(score.rings) if score.rings is not None else "–"
    if score.model == "ringe_minus_zeit":
        if score.time_cs is None or score.deduction is None:
            return ""
        time = f"{seconds(score.time_cs, typographic=True)}{NBSP}s"
        if score.rounded:
            deduction = number(score.deduction, typographic=True)
            return f"{rings} −{NBSP}{deduction} ({time}, abgerundet)"
        return f"{rings} −{NBSP}{time}"
    parts = [rings]
    for section in score.sections:
        label = f"{section.name} " if len(score.sections) > 1 else ""
        target = f"Sollzeit{NBSP}{format_seconds_value(section.target_s)}{NBSP}s"
        if section.time_cs is None or section.deduction is None:
            parts.append(f"({label}Zeit fehlt, {target})")
            continue
        parts.append(
            f"−{NBSP}{number(section.deduction, typographic=True)} "
            f"({label}{seconds(section.time_cs, typographic=True)}{NBSP}s, {target})"
        )
        if section.floored:
            parts.append(f"→ {section.name} {number(section.result, typographic=True)}")
    return " ".join(parts)


def _time_cells(score: TimeScore | None) -> tuple[Cell, ...]:
    """CSV-Spalten „Ringe vor Abzug“, „Gesamtzeit“, „Sollzeit“, „Abzug“."""
    if score is None:
        return (None, None, None, None)
    return (
        score.rings,
        cs_to_seconds(score.time_cs) if score.time_cs is not None else None,
        score.target_s,
        score.deduction,
    )


TIME_HEADERS = ("Ringe vor Abzug", "Gesamtzeit", "Sollzeit", "Abzug")


# --- Begriffe ------------------------------------------------------------------------------


def _terms(competition: CompetitionInfo) -> Begriffe:
    """Begriffssatz eines Wettbewerbs (sein Verband, sonst Standard)."""
    return begriffe.terms_for(competition.federation)


def document_terms(competitions: Iterable[CompetitionInfo]) -> Begriffe:
    """Gemeinsamer Satz mehrerer Wettbewerbe (gemischt oder nur eigene: Standard)."""
    return begriffe.document_terms(competition.federation for competition in competitions)


# --- Ergebnisliste: Zuordnung ------------------------------------------------------------


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


def _winner_row(
    row: RankingRow, person: PersonName, time_score: TimeScore | None = None
) -> WinnerRow:
    return WinnerRow(
        place=row.place,
        tied=row.tied,
        tie_unresolved=row.tie_unresolved,
        tie_reason=row.tie_reason,
        tie_note=row.tie_note,
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
        time_score=time_score,
        abort_label=row.abort_label,
        abort_note=row.abort_note,
    )


def winner_tables(
    ranking: RankingOut,
    *,
    class_names: Mapping[uuid.UUID, str],
    top: int | None = None,
    full_names: Mapping[uuid.UUID, PersonName] | None = None,
    time_scores: Mapping[uuid.UUID, TimeScore] | None = None,
) -> list[WinnerTable]:
    """Tabellen der Ergebnisliste eines Wettbewerbs aus seiner Rangliste.

    - Reihenfolge, Plätze, geteilte Plätze und Abbrüche bleiben, wie die Rangliste sie liefert
      (Abgebrochene ohne Platz am Ende, je Teilnehmer einmal; ob sie dabei sind, entscheidet
      die Rangliste mit `include_aborted`).
    - `top`: nur Zeilen mit Platz bis `top` (bei geteiltem Platz alle Gleichen).
    - `time_scores`: Rechenweg je Start (`start_id`) bei Wertung mit Zeit.
    """
    tables = []
    scores = time_scores or {}
    for group in ranking.groups:
        rows = [
            _winner_row(
                row,
                person_for(row.entry_id, row.display_name, row.club, full_names),
                scores.get(row.start_id),
            )
            for row in group.rows
        ]
        if top is not None:
            rows = [row for row in rows if row.place is not None and row.place <= top]
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
    competition: CompetitionInfo,
    unit: str | None,
    tables: Sequence[WinnerTable],
    *,
    tie_word: str = begriffe.NEUTRAL_TIE,
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
        tie_word=tie_word,
    )


# --- Serien --------------------------------------------------------------------------


def series_text(value: SeriesValue, *, typographic: bool = True) -> str:
    """Ringe, Zeit (mit Zuschlag) oder beides; gestrichene Serien in Klammern."""
    parts = []
    if value.rings is not None:
        # Zehntelwertung: „20,1“ (Dezimalkomma); ganze Ringe unverändert.
        parts.append(number(value.rings))
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


# --- Ergebnisliste: Tabellen -----------------------------------------------------------


def _place_text(row: WinnerRow) -> str:
    return f"{row.place}." if row.place is not None else ""


def _series_status_notes(
    series: Sequence[SeriesValue], headers: Mapping[SeriesKey, str] | None = None
) -> list[str]:
    """„S3: Waffenstörung vor dem ersten Wertungsschuss“ für jede Serie mit besonderem Ablauf."""
    notes = []
    for index, value in enumerate(series):
        if value.status == "normal":
            continue
        key = (value.section_id, value.number)
        name = headers.get(key) if headers else None
        notes.append(f"{name or index + 1}: {series_status_text(value.status)}")
    return notes


def _row_notes(
    row: WinnerRow,
    mark_provisional: bool,
    headers: Mapping[SeriesKey, str] | None = None,
    tie_word: str = begriffe.NEUTRAL_TIE,
) -> list[str]:
    notes = []
    if row.abort_reason is not None:
        notes.append(row.abort_label or abort_text(row.abort_reason) or begriffe.ABORT_FALLBACK)
        if row.abort_note:
            notes.append(row.abort_note)
    elif row.status == "review":
        notes.append("prüfen")
    elif not row.complete:
        notes.append("unvollständig")
    if row.scored:
        notes.extend(_series_status_notes(row.series, headers))
    if row.tie_reason == "max_score" and row.tie_note:
        # Höchstergebnis: gleicher Platz nach Regel (entschieden, aber erklärungsbedürftig).
        notes.append(row.tie_note)
    if row.tie_unresolved:
        # Stechen oder manuell zu entscheiden: der Hinweis der Rangliste; sonst kurz.
        notes.append(
            row.tie_note
            if row.tie_reason in ("shootoff", "manual") and row.tie_note
            else begriffe.tie_unresolved_text(tie_word)
        )
    if mark_provisional and row.status == "provisional":
        notes.append("vorläufig")
    return notes


def provisional_note(until: datetime, meta: Meta) -> str:
    """Hinweis über der Tabelle; das Datum nur, wenn der Tag nicht eindeutig ist."""
    local_day = local(until, meta.tz).date()
    when = f"{clock(until, meta.tz)} Uhr"
    if meta.date_from != meta.date_to or local_day != meta.date_from:
        when = f"{date_de(local_day)}, {when}"
    return f"Vorläufig – Einspruchsfrist läuft bis {when}."


def winners_report(meta: Meta, sections: Sequence[WinnerSection]) -> Report:
    legends: list[str] = []
    out: list[Section] = []
    for section in sections:
        competition = section.competition
        terms = begriffe.terms_for(competition.federation)
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
        with_tens = competition.rings and any(row.tens is not None for row in all_rows)
        with_inner = competition.rings and any(row.inner_tens is not None for row in all_rows)
        # Rechenweg nur bei Wertung mit Zeit (andere Modelle behalten ihr Layout).
        with_time = competition.time_model and any(
            row.time_score is not None and row.scored for row in all_rows
        )
        header_of = dict(zip(keys, headers, strict=True))
        result_title = f"Ergebnis ({section.unit})" if section.unit else "Ergebnis"

        def notes_of(
            table: WinnerTable,
            header_of: dict[SeriesKey, str] = header_of,
            tie_word: str = section.tie_word,
        ) -> Callable[[WinnerRow], list[str]]:
            # „vorläufig“ je Zeile nur, wenn nicht ohnehin die ganze Tabelle vorläufig ist.
            mixed = len({row.status == "provisional" for row in table.rows}) > 1
            return lambda row: _row_notes(row, mixed, header_of, tie_word)

        with_notes = any(notes_of(t)(row) for t in section.tables for row in t.rows)
        columns = [Column("Platz", "right"), Column("Nr.", "right"), Column("Name", wrap=True)]
        if with_club:
            columns.append(Column("Verein", wrap=True))
        if with_class:
            columns.append(Column("Klasse"))
        if with_attempt:
            columns.append(Column("Versuch", "right"))
        columns.append(Column(result_title, "right"))
        if with_time:
            columns.append(Column("Rechenweg", wrap=True))
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
                cells = [
                    _place_text(row),
                    str(row.start_number),
                    name_text(row.person, row.start_number),
                ]
                if with_club:
                    cells.append(row.person.club or "")
                if with_class:
                    cells.append(row.class_short)
                if with_attempt:
                    cells.append(str(row.attempt))
                # Abgebrochen ohne Platz: kein Ergebnis (ein Teilergebnis sähe wie eine
                # Wertung aus); ein Abbruch mit Platz zeigt sein gewertetes Ergebnis.
                shown = row.score if row.scored else None
                cells.append(number(shown, typographic=True) if shown is not None else "–")
                if with_time:
                    cells.append(
                        time_score_text(row.time_score)
                        if row.time_score is not None and shown is not None
                        else ""
                    )
                if with_tens:
                    cells.append(str(row.tens) if row.tens is not None else "")
                if with_inner:
                    cells.append(str(row.inner_tens) if row.inner_tens is not None else "")
                cells.extend(series_text(by_key[key]) if key in by_key else "" for key in keys)
                if with_notes:
                    cells.append(", ".join(notes(row)))
                rows.append(Row(tuple(cells), muted=not row.scored))
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
        subtitle = (
            f"{terms.schiessstand}: {competition.range_name}" if competition.range_name else None
        )
        out.append(Section(competition.title, subtitle, notes_text, tuple(tables)))
    return Report(
        title=document_terms(section.competition for section in sections).ergebnisliste,
        meta=meta,
        sections=tuple(out),
        legend=tuple(legends),
        empty_text=NO_RESULTS,
    )


def _status_cell(row: WinnerRow) -> str:
    if row.abort_reason is not None:
        label = row.abort_label or abort_text(row.abort_reason) or begriffe.ABORT_FALLBACK
        return f"{label} – {row.abort_note}" if row.abort_note else label
    return row_status_text(row.status)


def _series_status_cell(series: Sequence[SeriesValue]) -> str | None:
    """„2: Zeitlimit erreicht (…); 3: Waffenstörung …“ (Serien fortlaufend gezählt)."""
    return "; ".join(_series_status_notes(series)) or None


def winners_sheet(sections: Sequence[WinnerSection], tz: ZoneInfo | None = None) -> Sheet:
    """CSV der Ergebnisliste; Uhrzeiten in `tz` (Ortszeit des Turniers, Standard Europe/Berlin).

    „Zehner“ und „Innenzehner“ nur, wenn ein Wettbewerb der Datei Ringe wertet. „Gleichheit“
    nennt bei einem geteilten Platz das Wort des Wettbewerbs („Ringgleichheit“,
    „Treffergleichheit“, „gleiches Ergebnis“). Ein Abbruch mit Platz hat sein gewertetes
    Ergebnis und „Abbruch (AB)“ unter „Status“; Abgebrochene ohne Platz stehen ohne Ergebnis
    da, mit dem Grund unter „Status“.
    """
    with_tens = any(section.competition.rings for section in sections)
    with_time = any(section.competition.time_model for section in sections)
    sheet = Sheet(
        header=(
            "Kennziffer",
            "Wettbewerb",
            "Wertung",
            "Platz",
            "Gleichheit",
            "Startnummer",
            "Name",
            "Verein",
            "Klasse",
            "Versuch",
            "Ergebnis",
            "Einheit",
            *(("Zehner", "Innenzehner") if with_tens else ()),
            *(TIME_HEADERS if with_time else ()),
            "Teilwerte",
            "Status",
            "Vorläufig bis",
            "Serienstatus",
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
                score = row.score if row.scored else None
                tens: tuple[Cell, ...] = (
                    (row.tens, row.inner_tens) if competition.rings else (None, None)
                )
                ordered = [by_key[key] for key in keys if key in by_key]
                times = _time_cells(row.time_score if score is not None else None)
                sheet.rows.append(
                    (
                        competition.code,
                        competition.name,
                        table.title,
                        row.place,
                        section.tie_word if row.tied else "",
                        row.start_number,
                        name_text(row.person, row.start_number),
                        row.person.club,
                        row.class_short,
                        row.attempt,
                        score,
                        section.unit if score is not None else None,
                        *(tens if with_tens else ()),
                        *(times if with_time else ()),
                        "; ".join(parts) or None,
                        _status_cell(row),
                        iso_local(row.provisional_until, tz)
                        if row.status == "provisional" and row.provisional_until
                        else None,
                        _series_status_cell(ordered),
                    )
                )
    return sheet


# --- Startliste --------------------------------------------------------------------------

_LAST = 1 << 30


def _when(record: StartRecord) -> float:
    return record.heat_starts_at.timestamp() if record.heat_starts_at else float("inf")


def _heat_lane(record: StartRecord) -> int:
    """Schützenstand als Sortierschlüssel nur bei einem Start im Durchgang."""
    if record.heat_starts_at is None or record.lane is None:
        return _LAST
    return record.lane


def _competition_key(record: StartRecord) -> tuple[object, ...]:
    return (record.competition.sort, record.competition.name, str(record.competition.id))


def startlist_sort_key(sort: StartlistSort) -> Callable[[StartRecord], tuple[object, ...]]:
    """Reihenfolge der Startliste.

    - `competition`: je Wettbewerb in der Reihenfolge am Schießstand (Durchgang mit
      Schützenstand bzw. Reihenfolge), dann Startnummer und Versuch – wie die Startliste des
      Moduls `starts`.
    - `start_number`: nach Startnummer, dann Wettbewerb und Versuch.
    - `range`: je Schießstand nach Uhrzeit, Schützenstand und Wettbewerb.

    Der Schützenstand zählt nur innerhalb eines Durchgangs (dort ist er der gebuchte Platz); bei
    der Reihenfolge ist er nur der zuletzt benutzte und würde den 2. Versuch vor den 1. stellen.
    """

    def by_course(record: StartRecord) -> tuple[object, ...]:
        return (
            _when(record),
            _heat_lane(record),
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
                _heat_lane(r),
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
    when = clock(record.heat_starts_at, meta.tz)
    if meta.date_from != meta.date_to:
        when = f"{local(record.heat_starts_at, meta.tz).strftime('%d.%m.')} {when}"
    return f"{record.heat_number} ({when})" if record.heat_number is not None else when


def _startlist_table(
    meta: Meta, records: Sequence[StartRecord], *, with_competition: bool
) -> Table:
    with_heat = any(r.heat_starts_at is not None for r in records)
    with_lane = any(r.lane is not None for r in records)
    with_club = any(r.person.club for r in records)
    with_attempt = any(r.competition.multi_start for r in records)
    with_notes = any(r.status == "aborted" for r in records)
    terms = document_terms(record.competition for record in records)
    columns: list[Column] = []
    if with_heat:
        columns.append(Column(terms.durchgang))
    if with_lane:
        columns.append(Column(terms.schuetzenstand, "right"))
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
        cells += [str(record.start_number), name_text(record.person, record.start_number)]
        if with_club:
            cells.append(record.person.club or "")
        cells.append(record.class_short)
        if with_competition:
            cells.append(record.competition.title)
        if with_attempt:
            cells.append(str(record.attempt))
        if with_notes:
            cells.append(
                abort_text(record.abort_reason, _terms(record.competition))
                or begriffe.ABORT_FALLBACK
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
            terms = document_terms(record.competition for record in members)
            if sort == "competition":
                title = competition.title
                subtitle = (
                    f"{terms.schiessstand}: {competition.range_name}"
                    if competition.range_name
                    else None
                )
                with_competition = False
            else:
                title = competition.range_name or f"Ohne {terms.schiessstand}"
                subtitle = None
                with_competition = True
            table = _startlist_table(meta, members, with_competition=with_competition)
            count = len(members)
            info = f"{count} {'Start' if count == 1 else 'Starts'}"
            subtitle = f"{subtitle} · {info}" if subtitle else info
            sections.append(Section(title, subtitle, tables=(table,)))
    title = document_terms(record.competition for record in records).startliste
    return Report(title=title, meta=meta, sections=tuple(sections), empty_text=NO_STARTS)


def startlist_sheet(
    records: Sequence[StartRecord], sort: StartlistSort, tz: ZoneInfo | None = None
) -> Sheet:
    terms = document_terms(record.competition for record in records)
    sheet = Sheet(
        header=(
            "Startnummer",
            "Name",
            "Verein",
            "Klasse",
            "Klassenname",
            "Kennziffer",
            "Wettbewerb",
            terms.schiessstand,
            "Versuch",
            terms.durchgang,
            "Beginn",
            terms.schuetzenstand,
            "Reihenfolge",
            "Status",
            "Abbruchgrund",
        )
    )
    for record in sort_starts(records, sort):
        sheet.rows.append(
            (
                record.start_number,
                name_text(record.person, record.start_number),
                record.person.club,
                record.class_short,
                record.class_name,
                record.competition.code,
                record.competition.name,
                record.competition.range_name,
                record.attempt,
                record.heat_number,
                iso_local(record.heat_starts_at, tz) if record.heat_starts_at else None,
                record.lane,
                record.queue_position,
                start_status_text(record.status),
                abort_text(record.abort_reason, _terms(record.competition)),
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


def results_sheet(records: Sequence[ResultRecord], tz: ZoneInfo | None = None) -> Sheet:
    ordered = [_ordered_series(record) for record in records]
    width = max((len(series) for series in ordered), default=0)
    used = [
        (index, label, getter)
        for index in range(width)
        for label, getter in SERIES_FIELDS
        if any(index < len(series) and getter(series[index]) is not None for series in ordered)
    ]
    # Zehner nur, wenn ein Wettbewerb der Datei Ringe wertet.
    with_tens = any(record.start.competition.rings for record in records)
    # Wertung mit Zeit: Gesamtzeit (auch die Abschnittszeit der Mehrdistanz), Sollzeit, Abzug.
    with_time = any(record.start.competition.time_model for record in records)
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
        *(("Zehner", "Innenzehner") if with_tens else ()),
        *(TIME_HEADERS if with_time else ()),
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
        special = _series_status_notes(series)
        cells: list[Cell] = [
            start.start_number,
            name_text(start.person, start.start_number),
            start.person.club,
            start.class_short,
            start.competition.code,
            start.competition.name,
            start.attempt,
            start_status_text(start.status),
            abort_text(start.abort_reason, _terms(start.competition)),
            record.score if record.has_result else None,
            record.unit if record.has_result else None,
            ("ja" if record.complete else "nein") if record.has_result else None,
            *((record.tens, record.inner_tens) if with_tens else ()),
            *(_time_cells(record.time_score) if with_time else ()),
            iso_local(record.finalized_at, tz) if record.finalized_at else None,
            iso_local(record.provisional_until, tz) if record.is_provisional else None,
            "ja" if record.needs_review else None,
            ", ".join(struck) or None,
            "; ".join(special) or None,
        ]
        for index, _, getter in used:
            cells.append(getter(series[index]) if index < len(series) else None)
        sheet.rows.append(tuple(cells))
    return sheet
