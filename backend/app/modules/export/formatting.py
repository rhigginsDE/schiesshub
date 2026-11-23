"""Reine Hilfen für die Schreibweise in Listen: Zahlen, Zeiten, Datum, Dateinamen, Bezeichnungen.

Zahlen stehen mit Dezimalkomma. In der CSV-Datei steht ein normales Minuszeichen (`-`), damit
Tabellenkalkulationen die Zahl erkennen; im PDF das typografische (`−`) wie in der App.
Zeitpunkte speichert der Server in UTC; Listen zeigen sie in der Ortszeit des Turniers
(`settings.timezone`, über `Meta.tz`); ohne Angabe gilt `LOCAL_TZ` (Europe/Berlin).
"""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.core.begriffe import Begriffe
from app.core.localtime import DEFAULT_TIMEZONE, zone
from app.modules.ergebnisse import begriffe
from app.scoring.numbers import cs_to_seconds
from app.scoring.status import STATUS_LABELS

# Standard-Ortszeit, wenn das Turnier keine eigene Zeitzone hat.
LOCAL_TZ: ZoneInfo = zone(DEFAULT_TIMEZONE)

# Formelle Wörter (Ergebnisliste, Abbruch (AB), Schützenstand, Schießstand, Ringgleichheit)
# stehen im Begriffssatz des Verbands (`app.core.begriffe`), ausgewählt über
# `app.modules.ergebnisse.begriffe`.

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

# Ablauf einer Serie: dieselben Texte wie in der Eingabemaske (`app.scoring.status`).
SERIES_STATUS_LABELS: dict[str, str] = dict(STATUS_LABELS)


# --- Übersetzungsstelle: interne Schlüssel erscheinen in keiner Liste ------------------


def abort_text(reason: str | None, terms: Begriffe | None = None) -> str | None:
    """„dnf“ → „Abbruch (AB)“ (Begriffssatz `terms`, ohne Angabe der Standardsatz); unbekannte
    Schlüssel als „abgebrochen“."""
    return begriffe.abort_label(reason, terms)


def start_status_text(status: str) -> str:
    return START_STATUS_LABELS.get(status, "unbekannt")


def row_status_text(status: str) -> str:
    return ROW_STATUS_LABELS.get(status, "unbekannt")


def series_status_text(status: str) -> str:
    return SERIES_STATUS_LABELS.get(status, "besonderer Ablauf")


def number(value: Decimal | int, *, typographic: bool = False) -> str:
    """1234.5 → „1234,5“; Nachkommastellen bleiben, wie sie sind (75.20 → „75,20“)."""
    text = format(Decimal(value), "f").replace(".", ",")
    return text.replace("-", "−") if typographic else text


def seconds(cs: int, *, typographic: bool = False) -> str:
    """Hundertstelsekunden als Sekunden: 1284 → „12,84“."""
    return number(cs_to_seconds(cs), typographic=typographic)


def local(moment: datetime, tz: ZoneInfo | None = None) -> datetime:
    return moment.astimezone(tz or LOCAL_TZ)


def clock(moment: datetime, tz: ZoneInfo | None = None) -> str:
    """„14:35“ in Ortszeit."""
    return local(moment, tz).strftime("%H:%M")


def iso_local(moment: datetime, tz: ZoneInfo | None = None) -> str:
    """„2027-03-06 14:35“ in Ortszeit (ISO-Datum, von Tabellenkalkulationen erkannt)."""
    return local(moment, tz).strftime("%Y-%m-%d %H:%M")


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


def moment_de(moment: datetime, tz: ZoneInfo | None = None) -> str:
    """„06.03.2027, 14:35 Uhr“ in Ortszeit."""
    return local(moment, tz).strftime("%d.%m.%Y, %H:%M Uhr")


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
    """„Vereinspokal-2027_Ergebnisliste_2027-03-06.pdf“."""
    parts = [safe_file_part(tournament_name) or "Turnier", safe_file_part(kind), day.isoformat()]
    return "_".join(part for part in parts if part) + f".{extension}"
