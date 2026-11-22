"""Ausgabe einer Tabelle (`Sheet`) als CSV-Datei für Tabellenkalkulationen.

- UTF-8 mit BOM, Trennzeichen `;`, Zeilenende CRLF: Excel öffnet die Datei direkt richtig.
- Zahlen mit Dezimalkomma und normalem Minus (`-12,5`), Zeiten in Sekunden (`12,84`),
  Zeitpunkte als `JJJJ-MM-TT hh:mm` in Ortszeit (in `tables.py` formatiert).
- Schutz vor Formeln (CSV-Injektion): Ein Text, der – auch nach Leerraum – mit `=`, `+`, `-`,
  `@`, Tabulator oder Wagenrücklauf beginnt, bekommt ein `'` vorangestellt; Tabellenkalkulationen
  zeigen ihn dann als Text, statt ihn auszuführen. Das gilt nur für Texte; Zahlen, die der Server
  selbst schreibt, bleiben Zahlen (sonst würde aus `-3,5` Text).
"""

import csv
import io
from decimal import Decimal

from app.modules.export.formatting import number
from app.modules.export.tables import Cell, Sheet

BOM = "﻿"
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\n", "＝", "＋", "－", "＠")


def neutralize(text: str) -> str:
    """Entschärft Text, den eine Tabellenkalkulation als Formel lesen würde."""
    if text.startswith(_FORMULA_START) or text.lstrip().startswith(_FORMULA_START):
        return f"'{text}"
    return text


def cell_text(value: Cell) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):  # pragma: no cover - Tabellen liefern „ja“/„nein“ als Text
        return "ja" if value else "nein"
    if isinstance(value, int | Decimal):
        return number(value)
    return neutralize(value)


def write_csv(sheet: Sheet) -> bytes:
    buffer = io.StringIO(newline="")
    buffer.write(BOM)
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([neutralize(title) for title in sheet.header])
    for row in sheet.rows:
        writer.writerow([cell_text(value) for value in row])
    return buffer.getvalue().encode("utf-8")
