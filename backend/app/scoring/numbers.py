"""Zahlen ohne Rundungsfehler und ihre deutsche Schreibweise.

Zeiten sind ganze Hundertstelsekunden (`*_cs`), alles andere `Decimal`. Gleitkommazahlen aus
dem Katalog (YAML) werden über ihre Textform umgewandelt, damit aus 0.1 nicht
0.1000000000000000055 wird.
"""

from decimal import Decimal

CS_PER_SECOND = 100


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
