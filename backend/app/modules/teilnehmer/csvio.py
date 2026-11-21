"""CSV-Import und -Export der Personen.

Import: UTF-8 mit oder ohne BOM, Trennzeichen `;` oder `,` (aus der Kopfzeile erkannt), Spalten
`name`, `club`, `member_no`, `display_mode`, `show_club` – englisch oder deutsch benannt.
Export: UTF-8 mit BOM und `;`, damit Tabellenkalkulationen die Datei direkt öffnen; die Datei
lässt sich unverändert wieder importieren.

Zellen, die mit `=`, `+`, `-`, `@` beginnen, bekommen im Export ein `'` vorangestellt, damit
Tabellenkalkulationen sie nicht als Formel ausführen. Der Import entfernt dieses Zeichen wieder.
"""

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass

from app.modules.teilnehmer.names import DisplayMode, clean_text
from app.modules.teilnehmer.schemas import MEMBER_NO_MAX, NAME_MAX

COLUMNS = ("name", "club", "member_no", "display_mode", "show_club")

HEADER_ALIASES: dict[str, str] = {
    "name": "name",
    "club": "club",
    "verein": "club",
    "member_no": "member_no",
    "mitgliedsnummer": "member_no",
    "display_mode": "display_mode",
    "anzeige": "display_mode",
    "show_club": "show_club",
    "verein anzeigen": "show_club",
}

DISPLAY_MODE_VALUES: dict[str, DisplayMode] = {
    "full": "full",
    "voll": "full",
    "short": "short",
    "kurz": "short",
    "abgekürzt": "short",
    "hidden": "hidden",
    "verborgen": "hidden",
    "aus": "hidden",
}

TRUE_VALUES = frozenset({"true", "ja", "yes", "1", "x", "wahr"})
FALSE_VALUES = frozenset({"false", "nein", "no", "0", "falsch"})

_FORMULA_START = ("=", "+", "-", "@")


class ImportFormatError(Exception):
    """Die Datei als Ganzes ist unbrauchbar. Die Meldung ist für Anwender gedacht."""


@dataclass(frozen=True, slots=True)
class ImportRow:
    line: int
    name: str
    club: str | None
    member_no: str | None
    display_mode: DisplayMode
    show_club: bool


@dataclass(frozen=True, slots=True)
class ImportRowError:
    line: int
    message: str


def _detect_delimiter(text: str) -> str:
    header = next((line for line in text.splitlines() if line.strip()), "")
    return "," if header.count(",") > header.count(";") else ";"


def _unescape(value: str) -> str:
    if len(value) > 1 and value[0] == "'" and value[1] in _FORMULA_START:
        return value[1:]
    return value


def _escape(value: str) -> str:
    return f"'{value}" if value.startswith(_FORMULA_START) else value


def _map_header(header: list[str]) -> list[str]:
    columns: list[str] = []
    for raw in header:
        key = " ".join(raw.strip().casefold().split())
        column = HEADER_ALIASES.get(key)
        if column is None:
            raise ImportFormatError(
                f"Die Spalte „{raw.strip()}“ ist unbekannt. Erlaubt sind: name/Name, "
                "club/Verein, member_no/Mitgliedsnummer, display_mode/Anzeige, "
                "show_club/Verein anzeigen."
            )
        if column in columns:
            raise ImportFormatError(f"Die Spalte „{raw.strip()}“ kommt doppelt vor.")
        columns.append(column)
    if "name" not in columns:
        raise ImportFormatError("Die Kopfzeile braucht eine Spalte „name“ oder „Name“.")
    return columns


def _parse_row(line: int, values: dict[str, str]) -> ImportRow | ImportRowError:
    name = clean_text(values.get("name", ""))
    if not name:
        return ImportRowError(line, "Der Name fehlt.")
    if len(name) > NAME_MAX:
        return ImportRowError(line, f"Der Name ist länger als {NAME_MAX} Zeichen.")
    club = clean_text(values.get("club", "")) or None
    if club is not None and len(club) > NAME_MAX:
        return ImportRowError(line, f"Der Vereinsname ist länger als {NAME_MAX} Zeichen.")
    member_no = clean_text(values.get("member_no", "")) or None
    if member_no is not None and len(member_no) > MEMBER_NO_MAX:
        return ImportRowError(line, f"Die Mitgliedsnummer ist länger als {MEMBER_NO_MAX} Zeichen.")

    raw_mode = values.get("display_mode", "").strip().casefold()
    display_mode = DISPLAY_MODE_VALUES.get(raw_mode or "full")
    if display_mode is None:
        return ImportRowError(
            line,
            f"Die Anzeige „{values['display_mode'].strip()}“ ist unbekannt "
            "(erlaubt: full, short, hidden bzw. voll, kurz, verborgen).",
        )
    raw_show = values.get("show_club", "").strip().casefold()
    if not raw_show or raw_show in TRUE_VALUES:
        show_club = True
    elif raw_show in FALSE_VALUES:
        show_club = False
    else:
        return ImportRowError(
            line,
            f"„{values['show_club'].strip()}“ ist bei „Verein anzeigen“ nicht erlaubt "
            "(erlaubt: true/false, ja/nein, 1/0).",
        )
    return ImportRow(line, name, club, member_no, display_mode, show_club)


def parse_person_csv(content: bytes) -> list[ImportRow | ImportRowError]:
    """Liest die Datei. Fehler der ganzen Datei werfen `ImportFormatError`, Zeilenfehler nicht."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFormatError(
            "Die Datei ist nicht in UTF-8 kodiert. Bitte als „CSV UTF-8“ speichern."
        ) from exc
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_detect_delimiter(text))
    try:
        header = next((row for row in reader if any(cell.strip() for cell in row)), None)
        if header is None:
            raise ImportFormatError("Die Datei ist leer.")
        columns = _map_header(header)
        rows: list[ImportRow | ImportRowError] = []
        for cells in reader:
            line = reader.line_num
            if not any(cell.strip() for cell in cells):
                continue
            if len(cells) > len(columns):
                rows.append(
                    ImportRowError(
                        line,
                        f"Die Zeile hat {len(cells)} Werte, die Kopfzeile nur {len(columns)} "
                        "Spalten.",
                    )
                )
                continue
            values = {column: _unescape(cell) for column, cell in zip(columns, cells, strict=False)}
            rows.append(_parse_row(line, values))
    except csv.Error as exc:
        raise ImportFormatError(
            f"Die Datei ist kein gültiges CSV (Zeile {reader.line_num}): {exc}."
        ) from exc
    return rows


@dataclass(frozen=True, slots=True)
class ExportRow:
    name: str
    club: str | None
    member_no: str | None
    display_mode: str
    show_club: bool


def write_person_csv(rows: Iterable[ExportRow]) -> str:
    buffer = io.StringIO(newline="")
    buffer.write("﻿")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow(
            [
                _escape(row.name),
                _escape(row.club or ""),
                _escape(row.member_no or ""),
                row.display_mode,
                "true" if row.show_club else "false",
            ]
        )
    return buffer.getvalue()
