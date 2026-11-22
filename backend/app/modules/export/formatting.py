"""Reine Hilfen für die Schreibweise in Listen: Zahlen, Zeiten, Datum, Dateinamen, Bezeichnungen.

Zahlen stehen mit Dezimalkomma. In der CSV-Datei steht ein normales Minuszeichen (`-`), damit
Tabellenkalkulationen die Zahl erkennen; im PDF das typografische (`−`) wie in der App.
Zeitpunkte speichert der Server in UTC; Listen zeigen sie in der Ortszeit (`LOCAL_TZ`).
"""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.scoring.numbers import cs_to_seconds

# Ortszeit für Uhrzeiten in Listen. Schiesshub hat (noch) keine Zeitzone je Turnier.
LOCAL_TZ = ZoneInfo("Europe/Berlin")

ABORT_LABELS: dict[str, str] = {
    "dns": "nicht angetreten",
    "dnf": "aufgegeben",
    "dsq": "disqualifiziert",
}

START_STATUS_LABELS: dict[str, str] = {
    "registered": "angemeldet",
    "called": "aufgerufen",
    "captured": "erfasst",
    "final": "abgeschlossen",
    "aborted": "abgebrochen",
}

ROW_STATUS_LABELS: dict[str, str] = {
    "final": "endgültig",
    "provisional": "vorläufig",
    "running": "läuft",
    "aborted": "abgebrochen",
    "review": "prüfen",
}


def number(value: Decimal | int, *, typographic: bool = False) -> str:
    """1234.5 → „1234,5“; Nachkommastellen bleiben, wie sie sind (75.20 → „75,20“)."""
    text = format(Decimal(value), "f").replace(".", ",")
    return text.replace("-", "−") if typographic else text


def seconds(cs: int, *, typographic: bool = False) -> str:
    """Hundertstelsekunden als Sekunden: 1284 → „12,84“."""
    return number(cs_to_seconds(cs), typographic=typographic)


def local(moment: datetime) -> datetime:
    return moment.astimezone(LOCAL_TZ)


def clock(moment: datetime) -> str:
    """„14:35“ in Ortszeit."""
    return local(moment).strftime("%H:%M")


def iso_local(moment: datetime) -> str:
    """„2027-03-06 14:35“ in Ortszeit (ISO-Datum, von Tabellenkalkulationen erkannt)."""
    return local(moment).strftime("%Y-%m-%d %H:%M")


def date_de(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def date_range_de(first: date, last: date) -> str:
    """„06.03.2027“ oder „06.–07.03.2027“ oder „30.03.–02.04.2027“."""
    if first == last:
        return date_de(first)
    if (first.year, first.month) == (last.year, last.month):
        return f"{first.day:02d}.–{date_de(last)}"
    if first.year == last.year:
        return f"{first.strftime('%d.%m.')}–{date_de(last)}"
    return f"{date_de(first)}–{date_de(last)}"


def moment_de(moment: datetime) -> str:
    """„06.03.2027, 14:35 Uhr“ in Ortszeit."""
    return local(moment).strftime("%d.%m.%Y, %H:%M Uhr")


_TRANSLIT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
_TRANSLIT_EXTRA = {"ß": "ss", "ẞ": "SS", "ı": "i", "ł": "l", "Ł": "L", "ø": "o", "Ø": "O"}


def safe_file_part(text: str, *, max_length: int = 60) -> str:
    """Teil eines Dateinamens: nur ASCII-Buchstaben, Ziffern und Bindestriche."""
    text = text.translate(_TRANSLIT)
    text = "".join(_TRANSLIT_EXTRA.get(char, char) for char in text)
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-")
    return slug[:max_length].rstrip("-")


def file_name(tournament_name: str, kind: str, day: date, extension: str) -> str:
    """„Vereinspokal-2027_Siegerliste_2027-03-06.pdf“."""
    parts = [safe_file_part(tournament_name) or "Turnier", safe_file_part(kind), day.isoformat()]
    return "_".join(part for part in parts if part) + f".{extension}"
