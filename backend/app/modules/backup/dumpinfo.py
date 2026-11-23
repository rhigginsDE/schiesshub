"""Inhalt eines Datenbank-Abzugs lesen, ohne ihn einzuspielen.

`pg_restore --data-only --table=…` gibt die Zeilen einzelner Tabellen als `COPY … FROM stdin`
aus. Hier wird dieses Textformat gelesen (Spaltennamen aus der COPY-Zeile, `\\N` als NULL,
Escape-Folgen nach der PostgreSQL-Dokumentation „COPY, Text Format“). Damit lassen sich vor einer
Wiederherstellung Schema-Stand, Turniere, Starts und Ergebnis-Ereignisse der Sicherung zeigen.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.modules.backup import pgtools

# Was die Vorschau braucht. Tabellen, die es in einer alten Sicherung noch nicht gab, fehlen.
PREVIEW_TABLES = [
    "alembic_version",
    "tournament",
    "competition",
    "start",
    "result_event",
    "result_current",
    "role",
    "user_account",
    "device",
    "session",
    "person",
    "setting",
]

_COPY = re.compile(r"^COPY (?:\"?[\w]+\"?\.)?\"?(\w+)\"? \((.*)\) FROM stdin;$")
_ESCAPES = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
_OCTAL = re.compile(r"[0-7]{1,3}")
_HEX = re.compile(r"x[0-9a-fA-F]{1,2}")

type Row = dict[str, str | None]


def _unescape(value: str) -> str | None:
    if value == "\\N":
        return None
    if "\\" not in value:
        return value
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\" or index + 1 >= len(value):
            out.append(char)
            index += 1
            continue
        nxt = value[index + 1]
        if nxt in _ESCAPES:
            out.append(_ESCAPES[nxt])
            index += 2
        elif match := _OCTAL.match(value, index + 1):
            out.append(chr(int(match.group(), 8)))
            index = match.end()
        elif match := _HEX.match(value, index + 1):
            out.append(chr(int(match.group()[1:], 16)))
            index = match.end()
        else:
            out.append(nxt)
            index += 2
    return "".join(out)


def parse_copy(text: str) -> dict[str, list[Row]]:
    """Alle COPY-Blöcke eines SQL-Texts: Tabelle -> Zeilen (Spalte -> Wert oder None)."""
    tables: dict[str, list[Row]] = {}
    # Nur an Zeilenvorschub trennen: Andere Umbrüche (etwa U+2028) können in Werten stehen.
    lines = iter(text.split("\n"))
    for line in lines:
        match = _COPY.match(line)
        if match is None:
            continue
        columns = [column.strip().strip('"') for column in match.group(2).split(",")]
        rows = tables.setdefault(match.group(1), [])
        for data in lines:
            if data == "\\.":
                break
            values = data.split("\t")
            rows.append(dict(zip(columns, (_unescape(value) for value in values), strict=False)))
    return tables


@dataclass(slots=True)
class DumpInfo:
    """Was aus einem Abzug für die Vorschau gelesen wurde. Fehlende Tabellen sind `None`."""

    tables: dict[str, list[Row]] = field(default_factory=dict)

    def rows(self, table: str) -> list[Row] | None:
        return self.tables.get(table)

    @property
    def schema_revisions(self) -> list[str]:
        rows = self.tables.get("alembic_version") or []
        return sorted(row["version_num"] for row in rows if row.get("version_num"))


async def read_dump(dump: Path, tables: list[str] | None = None) -> DumpInfo:
    output = await pgtools.table_data(dump, tables or PREVIEW_TABLES)
    return DumpInfo(parse_copy(output.decode("utf-8", "replace")))
