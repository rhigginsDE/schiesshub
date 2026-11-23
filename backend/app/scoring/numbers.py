"""Zahlen ohne Rundungsfehler und ihre deutsche Schreibweise.

Zeiten sind ganze Hundertstelsekunden (`*_cs`), alles andere `Decimal`. Gleitkommazahlen aus
dem Katalog (YAML) werden über ihre Textform umgewandelt, damit aus 0.1 nicht
0.1000000000000000055 wird.
"""

import re
from decimal import Decimal, InvalidOperation

CS_PER_SECOND = 100
TENTH = Decimal("0.1")
_DECIMAL_TEXT = re.compile(r"^\d+(?:[.,]\d+)?$")


def to_decimal(value: object) -> Decimal:
    """Zahl aus Katalog oder JSON als `Decimal`; Wahrheitswerte und Text sind Fehler."""
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        raise ValueError("Zahl erwartet")
    result = Decimal(str(value)) if isinstance(value, float) else Decimal(value)
    if not result.is_finite():
        raise ValueError("endliche Zahl erwartet")
    return result


def is_hundredths(value: Decimal) -> bool:
    """True, wenn der Wert auf Hundertstel genau ist (0,01-Schritte)."""
    scaled = value * CS_PER_SECOND
    return scaled == scaled.to_integral_value()


def seconds_to_cs(seconds: Decimal) -> int:
    if not is_hundredths(seconds):
        raise ValueError(f"{seconds} s ist nicht auf Hundertstelsekunden genau")
    return int(seconds * CS_PER_SECOND)


def cs_to_seconds(cs: int) -> Decimal:
    """1284 → Decimal('12.84'); behält immer zwei Nachkommastellen."""
    return Decimal(cs).scaleb(-2)


def to_hundredths(value: Decimal) -> int:
    """Ergebnis als ganze Zahl in Hundertsteln (für Vergleichsschlüssel)."""
    if not is_hundredths(value):
        raise ValueError(f"{value} ist nicht auf Hundertstel genau")
    return int(value * CS_PER_SECOND)


def parse_decimal_input(value: object) -> Decimal | None:
    """Eingabe einer Kommazahl ab 0 (Zehntelwertung): Zahl oder Text mit Komma oder Punkt.

    `10.5`, `"10,5"`, `"10.5"`, `10`, `Decimal("10.5")` → `Decimal`; None bei allem anderen
    (Wahrheitswert, negativ, kein Zahltext, nicht endlich). Nachkommastellen bleiben, wie
    eingegeben („9,80“ → 9.80), damit der Aufrufer zu viele Stellen erkennen kann.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not _DECIMAL_TEXT.match(text):
            return None
        return Decimal(text.replace(",", "."))
    if isinstance(value, float):
        value = Decimal(str(value))
    if isinstance(value, int):
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        return None
    return value


def decimal_places(value: Decimal) -> int:
    """Anzahl Nachkommastellen, wie geschrieben (10.50 → 2, 10 → 0)."""
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def to_tenths(value: Decimal) -> Decimal:
    """Auf eine Nachkommastelle gebracht (nur für Werte, die schon auf Zehntel genau sind)."""
    try:
        return value.quantize(TENTH)
    except InvalidOperation:  # pragma: no cover - nur bei absurd großen Werten
        return value


def format_number(value: Decimal | int) -> str:
    """Deutsche Schreibweise: Komma als Dezimalzeichen, echtes Minuszeichen."""
    text = format(Decimal(value), "f")
    return text.replace("-", "−").replace(".", ",")


def format_seconds_value(seconds: Decimal) -> str:
    """Katalogsekunden ohne überflüssige Nullen: 60 → „60“, 2.50 → „2,5“."""
    normalized = seconds.normalize()
    if normalized == normalized.to_integral_value():
        normalized = normalized.quantize(Decimal(1))
    return format_number(normalized)


def format_cs(cs: int) -> str:
    """1284 → „12,84 s“."""
    return f"{format_number(cs_to_seconds(cs))} s"


def plural(count: int | Decimal, singular: str, plural_form: str) -> str:
    return f"{format_number(count)} {singular if count == 1 else plural_form}"
