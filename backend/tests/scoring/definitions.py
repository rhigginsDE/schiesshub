"""Feste Wettbewerbsdefinitionen für die Verhaltenstests.

Bewusst unabhängig vom Katalog: Ändert sich eine Katalogdatei, bleiben diese Tests stabil. Die
Werte entsprechen dem BDS-Ablauf zum Zeitpunkt der Tests; nur `test_catalog.py` prüft die echten
Dateien. Jede Funktion liefert eine frische Kopie, die ein Test verändern darf.
"""

from typing import Any

RING_TIES = ["zehner", "innenzehner", "neuner_abwaerts"]


def _definition(variant_id: str, sections: list[dict], **scoring: Any) -> dict:
    return {
        "variant": {"id": variant_id, "name": variant_id, "abschnitte": sections},
        "scoring": scoring,
    }


def praezision() -> dict:
    """KW 25 m Präzision: 2×10 Schuss in je 5 Min."""
    section = {
        "id": "praezision",
        "name": "Präzision",
        "serien": 2,
        "schuss_je_serie": 10,
        "zeit_je_serie_s": 300,
    }
    return _definition(
        "standard",
        [section],
        modell="ringe",
        rangfolge="absteigend",
        gleichstand=RING_TIES,
        geprueft=True,
    )


def intervall(serien: int = 6) -> dict:
    """LW 50 m Intervall: 5er-Serien, je Schuss 8 s Sicht, 12 s Pause."""
    section = {
        "id": "intervall",
        "name": "Intervall",
        "serien": serien,
        "schuss_je_serie": 5,
        "zeit_je_schuss_s": 8,
        "pause_zwischen_schuessen_s": 12,
    }
    return _definition(
        "dm", [section], modell="ringe", rangfolge="absteigend", gleichstand=RING_TIES
    )


def kombi() -> dict:
    """KW 25 m Kombi: Präzision 2×10, Intervall 2×5, Zeitserie 5 in 20 s und 5 in 10 s."""
    sections = [
        {
            "id": "praezision",
            "name": "Präzision",
            "serien": 2,
            "schuss_je_serie": 10,
            "zeit_je_serie_s": 300,
        },
        {
            "id": "intervall",
            "name": "Intervall",
            "serien": 2,
            "schuss_je_serie": 5,
            "zeit_je_schuss_s": 3,
            "pause_zwischen_schuessen_s": 7,
        },
        {
            "id": "zeitserie",
            "name": "Zeitserie",
            "serien": 2,
            "schuss_je_serie": 5,
            "zeiten_s": [20, 10],
        },
    ]
    return _definition(
        "standard", sections, modell="ringe", rangfolge="absteigend", gleichstand=RING_TIES
    )


def speed(serien: int = 4, *, rounding: bool = True) -> dict:
    """KW 25 m Speed: 5 Scheiben, 5 Schuss, max. 60 s je Serie; ohne ringwerte/unbeendete_serie."""
    section = {
        "id": "speed",
        "name": "Speed",
        "serien": serien,
        "schuss_je_serie": 5,
        "ziele_je_serie": 5,
        "max_zeit_je_serie_s": 60,
        "zeit_wird_gemessen": True,
    }
    scoring: dict[str, Any] = {"modell": "ringe_minus_zeit", "rangfolge": "absteigend"}
    if rounding:
        scoring["zeit_rundung"] = "summe_abrunden"
    return _definition("bm-lm", [section], **scoring)


def fallscheibe(serien: int = 4, max_schuss: int = 16) -> dict:
    """KW 25 m Fallscheibe GK: 5 Fallscheiben, max. 60 s, 10 s je stehender Scheibe;
    ohne zeit_bei_abbruch_s/zuschlag_stoerung_vor_erstem_schuss_s."""
    section = {
        "id": "fallscheibe",
        "name": "Fallscheibe",
        "serien": serien,
        "ziele_je_serie": 5,
        "max_schuss_je_serie": max_schuss,
        "max_zeit_je_serie_s": 60,
        "zeit_wird_gemessen": True,
        "zuschlag_je_stehender_scheibe_s": 10,
    }
    return _definition("bm-lm", [section], modell="zeit_plus_zuschlaege", rangfolge="aufsteigend")


def _mehrdistanz(
    serien: int,
    fertigkeit_s: int,
    fertigkeit_m: list[int],
    sollzeit_s: int,
    gleichstand: list[str],
) -> dict:
    sections = [
        {
            "id": "fertigkeit",
            "name": "Fertigkeit",
            "serien": serien,
            "schuss_je_serie": 5,
            "zeit_je_serie_s": fertigkeit_s,
            "distanzen_m": fertigkeit_m,
        },
        {
            "id": "parcours",
            "name": "Parcours",
            "serien": serien,
            "schuss_je_serie": 5,
            "distanzen_m": list(reversed(fertigkeit_m)),
            "zeit_wird_gemessen": True,
            "sollzeit_s": sollzeit_s,
            "max_gesamtzeit_s": 2 * sollzeit_s,
        },
    ]
    return _definition(
        "variante-1",
        sections,
        modell="ringe_mit_zeitabzug",
        rangfolge="absteigend",
        abzug_je_voller_sekunde_ueber_sollzeit=1,
        min_teilergebnis=0,
        gleichstand=gleichstand,
    )


def mehrdistanz_kw() -> dict:
    """KW Mehrdistanz, Parcours-Variante 1: 4+4 Serien, Sollzeit 80 s, Abbruch 160 s."""
    return _mehrdistanz(4, 10, [5, 10, 15, 20], 80, RING_TIES)


def mehrdistanz_flinte() -> dict:
    """Flinte Mehrdistanz, Variante 1: 3+3 Serien, Sollzeit 70 s; Gleichstand Zehner, Zeit."""
    return _mehrdistanz(3, 15, [15, 20, 25], 70, ["zehner", "parcours_zeit"])


def mehrdistanz_lw() -> dict:
    """LW Mehrdistanz, Variante 1: 3+3 Serien, Sollzeit 70 s; Gleichstand nur Parcourszeit."""
    return _mehrdistanz(3, 15, [15, 20, 25], 70, ["parcours_zeit"])
