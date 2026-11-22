"""CSV-Import und -Export der Personen.

Import:

- Kodierung UTF-8 mit oder ohne BOM. Ist die Datei kein gültiges UTF-8, wird sie als
  Windows-1252 gelesen (Excel „CSV (Trennzeichen-getrennt)“ auf deutschen Rechnern).
- Trennzeichen `;`, `,` oder Tabulator, aus der Kopfzeile erkannt.
- Spalten `name`, `club`, `member_no`, `display_mode`, `show_club`, englisch oder deutsch und
  mit üblichen Synonymen benannt (ohne Rücksicht auf Groß-/Kleinschreibung, Leerzeichen,
  Bindestriche und Umlaut-Schreibweise). Statt `name` gehen auch getrennte Spalten „Vorname“
  und „Nachname“ (bzw. „Name“/„Familienname“); sie werden zu „Vorname Nachname“ zusammengesetzt,
  so wie Namen im Modul gespeichert werden.
- Alle anderen Spalten (Straße, E-Mail, Geburtsdatum …) werden ignoriert: Ihre Werte werden
  weder gelesen noch gespeichert oder protokolliert. Nur die Spaltennamen gehen in die Antwort.

Export: UTF-8 mit BOM und `;`, damit Tabellenkalkulationen die Datei direkt öffnen; die Datei
lässt sich unverändert wieder importieren.

Zellen, die mit `=`, `+`, `-`, `@` beginnen, bekommen im Export ein `'` vorangestellt, damit
Tabellenkalkulationen sie nicht als Formel ausführen. Der Import entfernt dieses Zeichen wieder.
"""

import csv
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.modules.teilnehmer.names import DisplayMode, clean_text, fold
from app.modules.teilnehmer.schemas import MEMBER_NO_MAX, NAME_MAX

COLUMNS = ("name", "club", "member_no", "display_mode", "show_club")

# Interne Zielspalten beim Import: zusätzlich zu COLUMNS die getrennten Namensteile.
_FIRST = "first_name"
_LAST = "last_name"

# Lesbare Bezeichnung je Zielspalte für Meldungen.
_LABELS = {
    "name": "Name",
    "club": "Verein",
    "member_no": "Mitgliedsnummer",
    "display_mode": "Anzeige",
    "show_club": "Verein anzeigen",
    _FIRST: "Vorname",
    _LAST: "Nachname",
}


def _header_key(raw: str) -> str:
    """Vergleichsform eines Spaltennamens: „Mitglieds-Nr.“, „mitglieds_nr“ → „mitgliedsnr“."""
    return re.sub(r"[^0-9a-z]", "", fold(raw))


# Spaltennamen je Zielspalte. „name“ steht hier nicht: Es bedeutet den ganzen Namen, neben
# einer Spalte „Vorname“ aber den Nachnamen (siehe `_map_header`).
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "name": (
        "vor- und nachname",
        "vor-/nachname",
        "vorname nachname",
        "vollständiger name",
        "voller name",
        "full name",
    ),
    _FIRST: ("vorname", "vornamen", "first name", "first_name", "firstname", "given name"),
    _LAST: ("nachname", "familienname", "zuname", "last name", "last_name", "lastname", "surname"),
    "club": ("club", "club_name", "verein", "vereinsname", "verein name"),
    "member_no": (
        "member_no",
        "member number",
        "mitgliedsnummer",
        "mitglieds-nr.",
        "mitgliedsnr",
        "mitgliedsnr.",
        "mitgl.-nr.",
        "mitgl.nr.",
        "mitgliedernummer",
    ),
    "display_mode": ("display_mode", "anzeige"),
    "show_club": ("show_club", "verein anzeigen"),
}

HEADER_ALIASES: dict[str, str] = {
    _header_key(alias): column for column, aliases in _SYNONYMS.items() for alias in aliases
}
_NAME_KEY = _header_key("name")

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
    # Was sich aus der Zeile lesen ließ, damit die Vorschau die Zeile erkennbar zeigen kann.
    name: str | None = None
    club: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedFile:
    rows: list[ImportRow | ImportRowError]
    # Spaltennamen aus der Kopfzeile, die nicht übernommen werden (in Reihenfolge, ohne Doppel).
    ignored_columns: list[str] = field(default_factory=list)


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return content.decode("cp1252")
    except UnicodeDecodeError as exc:
        raise ImportFormatError(
            "Die Datei enthält Zeichen, die sich nicht lesen lassen. Bitte in Excel über "
            "„Speichern unter“ als „CSV UTF-8“ speichern und erneut wählen."
        ) from exc


def _detect_delimiter(text: str) -> str:
    header = next((line for line in text.splitlines() if line.strip()), "")
    counts = {delimiter: header.count(delimiter) for delimiter in (";", ",", "\t")}
    best = max(counts, key=lambda delimiter: counts[delimiter])
    return best if counts[best] > 0 else ";"


def _unescape(value: str) -> str:
    if len(value) > 1 and value[0] == "'" and value[1] in _FORMULA_START:
        return value[1:]
    return value


def _escape(value: str) -> str:
    return f"'{value}" if value.startswith(_FORMULA_START) else value


def _map_header(header: list[str]) -> tuple[list[str | None], list[str]]:
    """Zielspalte je Spalte der Datei (None: wird ignoriert) und die ignorierten Spaltennamen."""
    keys = [_header_key(raw) for raw in header]
    # „Name“ neben „Vorname“ ist der Nachname, sonst der ganze Name.
    has_first = any(HEADER_ALIASES.get(key) == _FIRST for key in keys)
    columns: list[str | None] = []
    seen: dict[str, str] = {}
    ignored: list[str] = []
    for raw, key in zip(header, keys, strict=True):
        label = clean_text(raw)
        if not key:
            # Leere Kopfzelle (oft ein Semikolon zu viel am Zeilenende): still übergehen.
            columns.append(None)
            if label and label not in ignored:
                ignored.append(label)
            continue
        column = (_LAST if has_first else "name") if key == _NAME_KEY else HEADER_ALIASES.get(key)
        if column is None:
            columns.append(None)
            if label not in ignored:
                ignored.append(label)
            continue
        if column in seen:
            if fold(seen[column]) == fold(label):
                raise ImportFormatError(f"Die Spalte „{label}“ kommt doppelt vor.")
            raise ImportFormatError(
                f"Die Spalten „{seen[column]}“ und „{label}“ meinen beide „{_LABELS[column]}“. "
                "Bitte eine davon löschen oder umbenennen."
            )
        seen[column] = label
        columns.append(column)

    if "name" in seen and (_FIRST in seen or _LAST in seen):
        other = seen.get(_FIRST) or seen[_LAST]
        raise ImportFormatError(
            f"Die Datei hat eine Spalte für den ganzen Namen („{seen['name']}“) und zusätzlich "
            f"„{other}“. Bitte nur das eine oder das andere behalten."
        )
    if _FIRST in seen and _LAST not in seen:
        raise ImportFormatError(
            f"Zur Spalte „{seen[_FIRST]}“ fehlt die Spalte „Nachname“. Bitte eine Spalte "
            "„Nachname“ ergänzen."
        )
    if _LAST in seen and _FIRST not in seen:
        raise ImportFormatError(
            f"Zur Spalte „{seen[_LAST]}“ fehlt die Spalte „Vorname“. Steht der ganze Name in "
            "einer Spalte, diese bitte „Name“ nennen."
        )
    if "name" not in seen and _FIRST not in seen:
        raise ImportFormatError(
            "Die Kopfzeile braucht eine Spalte „Name“ (oder die Spalten „Vorname“ und "
            "„Nachname“). Die erste Zeile der Datei muss die Spaltennamen enthalten."
        )
    return columns, ignored


def _parse_row(line: int, values: dict[str, str]) -> ImportRow | ImportRowError:
    split = _FIRST in values or _LAST in values
    if split:
        name = clean_text(f"{values.get(_FIRST, '')} {values.get(_LAST, '')}")
    else:
        name = clean_text(values.get("name", ""))
    club = clean_text(values.get("club", "")) or None

    def error(message: str) -> ImportRowError:
        return ImportRowError(line, message, name=name or None, club=club)

    if not name:
        return error("Vorname und Nachname fehlen." if split else "Der Name fehlt.")
    if len(name) > NAME_MAX:
        return error(f"Der Name ist länger als {NAME_MAX} Zeichen.")
    if club is not None and len(club) > NAME_MAX:
        return error(f"Der Vereinsname ist länger als {NAME_MAX} Zeichen.")
    member_no = clean_text(values.get("member_no", "")) or None
    if member_no is not None and len(member_no) > MEMBER_NO_MAX:
        return error(f"Die Mitgliedsnummer ist länger als {MEMBER_NO_MAX} Zeichen.")

    raw_mode = values.get("display_mode", "").strip().casefold()
    display_mode = DISPLAY_MODE_VALUES.get(raw_mode or "full")
    if display_mode is None:
        return error(
            f"Bei „Anzeige“ steht „{values['display_mode'].strip()}“. Erlaubt sind voll, kurz "
            "oder verborgen (leer = voll)."
        )
    raw_show = values.get("show_club", "").strip().casefold()
    if not raw_show or raw_show in TRUE_VALUES:
        show_club = True
    elif raw_show in FALSE_VALUES:
        show_club = False
    else:
        return error(
            f"Bei „Verein anzeigen“ steht „{values['show_club'].strip()}“. Erlaubt sind ja oder "
            "nein (leer = ja)."
        )
    return ImportRow(line, name, club, member_no, display_mode, show_club)


def parse_person_csv(content: bytes) -> ParsedFile:
    """Liest die Datei. Fehler der ganzen Datei werfen `ImportFormatError`, Zeilenfehler nicht.

    Werte ignorierter Spalten werden nicht angefasst; sie verlassen diese Funktion nie.
    """
    text = _decode(content)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_detect_delimiter(text))
    try:
        header = next((row for row in reader if any(cell.strip() for cell in row)), None)
        if header is None:
            raise ImportFormatError("Die Datei ist leer.")
        columns, ignored = _map_header(header)
        rows: list[ImportRow | ImportRowError] = []
        for cells in reader:
            line = reader.line_num
            if not any(cell.strip() for cell in cells):
                continue
            if any(cell.strip() for cell in cells[len(columns) :]):
                rows.append(
                    ImportRowError(
                        line,
                        f"Die Zeile hat {len(cells)} Werte, die Kopfzeile aber nur "
                        f"{len(columns)} Spalten. Oft steht ein Trennzeichen (; oder ,) "
                        "im Namen; dann den Wert in Anführungszeichen setzen.",
                    )
                )
                continue
            values = {
                column: _unescape(cell)
                for column, cell in zip(columns, cells, strict=False)
                if column is not None
            }
            rows.append(_parse_row(line, values))
    except csv.Error as exc:
        raise ImportFormatError(
            f"Die Datei ist kein gültiges CSV: Ab Zeile {reader.line_num} lässt sie sich nicht "
            "als Tabelle lesen. Häufige Ursache ist ein Anführungszeichen ohne Gegenstück."
        ) from exc
    return ParsedFile(rows=rows, ignored_columns=ignored)


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
