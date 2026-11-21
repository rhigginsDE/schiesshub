"""Reine Funktionen rund um Namen: Bereinigen, Vergleichsform für die Suche, Abkürzung."""

import unicodedata
from typing import Literal

DisplayMode = Literal["full", "short", "hidden"]

# Namenszusätze, die zum Nachnamen gehören („Anna von der Leyen“ → „A. von der Leyen“).
NAME_PARTICLES = frozenset(
    {
        "von",
        "vom",
        "zu",
        "zum",
        "zur",
        "van",
        "der",
        "den",
        "de",
        "del",
        "della",
        "di",
        "da",
        "du",
        "la",
        "le",
        "ten",
        "ter",
        "op",
    }
)

# Nach dem Entfernen der Akzente: ae/oe/ue gelten als a/o/u, damit „koehler“, „kohler“ und
# „Köhler“ dieselbe Vergleichsform haben.
_DIGRAPHS = (("ae", "a"), ("oe", "o"), ("ue", "u"))


def clean_text(value: str) -> str:
    """Unicode normalisieren (NFC), Leerraum am Rand entfernen und innen zusammenfassen."""
    return " ".join(unicodedata.normalize("NFC", value).split())


def fold(value: str) -> str:
    """Vergleichsform: ohne Groß-/Kleinschreibung, Akzente und Umlaut-Schreibweise.

    Wird auf gespeicherte Werte und Suchbegriffe gleichermaßen angewandt.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    folded = without_marks.casefold()
    for digraph, replacement in _DIGRAPHS:
        folded = folded.replace(digraph, replacement)
    return " ".join(folded.split())


def _initial(given_name: str) -> str:
    """„Hans-Peter“ → „H.-P.“, „J.“ → „J.“."""
    parts = [part.rstrip(".") for part in given_name.split("-")]
    return "-".join(f"{part[0]}." for part in parts if part)


def abbreviate_name(name: str) -> str:
    """Kurzform für Anzeige und Listen: Vornamen als Initialen, Nachname vollständig.

    - „Markus Brandt“ → „M. Brandt“
    - „Hans Peter Müller“ → „H. P. Müller“, „Hans-Peter Müller“ → „H.-P. Müller“
    - „Anna Müller-Lüdenscheidt“ → „A. Müller-Lüdenscheidt“ (Doppelname bleibt)
    - „Ludwig van Beethoven“ → „L. van Beethoven“ (Namenszusätze gehören zum Nachnamen)
    - Ein einzelner Name bleibt, wie er ist.
    """
    words = clean_text(name).split(" ")
    if len(words) < 2:
        return " ".join(words)
    surname_start = len(words) - 1
    while surname_start > 0 and words[surname_start - 1].casefold() in NAME_PARTICLES:
        surname_start -= 1
    initials = [initial for word in words[:surname_start] if (initial := _initial(word))]
    if not initials:
        return " ".join(words)
    return " ".join([*initials, *words[surname_start:]])


def display_name(name: str, mode: DisplayMode) -> str | None:
    """Name, wie er auf Anzeige und Listen erscheint."""
    match mode:
        case "full":
            return clean_text(name)
        case "short":
            return abbreviate_name(name)
        case "hidden":
            return None
