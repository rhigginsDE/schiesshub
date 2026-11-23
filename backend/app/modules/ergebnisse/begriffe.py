"""Formelle Begriffe der Ergebnislisten – die eine Stelle für Rangliste, Anzeige und Export.

Was formell gedruckt oder angezeigt wird (Ergebnisliste, Aushang, Anzeige), muss dem
Sporthandbuch entsprechen (Entscheidungen vom 23.11.2026). Die Wörter stehen deshalb nur hier;
Rangliste (`ranking.py`), Anzeige (`anzeige.feed`) und Export (`export.formatting`,
`export.tables`) holen sie von hier. Formelle Begriffe werden später je Verband gepflegt; dann
wird nur dieses Modul auf den Begriffssatz des Verbands umgestellt.

Fundstellen (BDS-Sporthandbuch, Fassung 30.06.2026):

- „Ergebnisliste“ (nicht „Siegerliste“): K 1.14, L 1.12.
- „Abbruch (AB)“: K 1.07 / L 1.05 (Abbruch im Probeschießen), K 1.14 / L 1.12 (nach „Feuer“).
- „Ringgleichheit“: A 9.03; „Treffergleichheit“ (Mehrdistanz Flinte und Büchse, entschieden
  über die Durchgangszeit): L 11.04, L 12.04. Für Fallscheibe und Speed nennt das Sporthandbuch
  kein Wort; dort steht neutral „gleiches Ergebnis“.
- „Schützenstand“ (nicht „Bahn“), „Schießstand“ (die Anlage, nicht „Stand“).
"""

from collections.abc import Sequence

RESULT_LIST = "Ergebnisliste"
"""Titel der Liste mit Ergebnissen und Plätzen (PDF, CSV, Dateiname, Anzeige)."""
RESULT_LIST_FILE = "Ergebnisliste"
"""Teil des Dateinamens („Vereinspokal_Ergebnisliste_2027-03-06.pdf“)."""

FIRING_POINT = "Schützenstand"
"""Der Platz des Schützen (bisher „Bahn“)."""
SHOOTING_RANGE = "Schießstand"
"""Die Anlage (bisher „Stand“), z. B. „Schießstand 25 m“."""
NO_SHOOTING_RANGE = "Ohne Schießstand"

ABORT_LABELS: dict[str, str] = {
    "dns": "nicht angetreten",
    "dnf": "Abbruch (AB)",
    "dsq": "disqualifiziert",
}
ABORT_FALLBACK = "abgebrochen"

RING_TIE = "Ringgleichheit"
HIT_TIE = "Treffergleichheit"
NEUTRAL_TIE = "gleiches Ergebnis"

NOT_COMPARABLE = "Ergebnis nicht vergleichbar"


def abort_label(reason: str | None) -> str | None:
    """„dnf“ → „Abbruch (AB)“; unbekannte Schlüssel als „abgebrochen“; ohne Grund None."""
    if reason is None:
        return None
    return ABORT_LABELS.get(reason, ABORT_FALLBACK)


def tie_word(model: str | None, criteria: Sequence[str] = ()) -> str:
    """Wort für gleiche Ergebnisse je Wertungsmodell (Fundstellen oben).

    Mehrdistanz mit der Durchgangszeit als Kriterium (Flinte, Büchse) → „Treffergleichheit“;
    sonst bei Ringwertung „Ringgleichheit“; bei Zeitwertung (Fallscheibe) und Ringe minus Zeit
    (Speed) nennt das Sporthandbuch kein Wort → „gleiches Ergebnis“."""
    if model == "ringe_mit_zeitabzug" and "parcours_zeit" in criteria:
        return HIT_TIE
    if model in ("ringe", "ringe_mit_zeitabzug"):
        return RING_TIE
    return NEUTRAL_TIE


def tie_note(reason: str | None, criterion: str | None, place: int | None, word: str) -> str | None:
    """Hinweis zu einem offenen geteilten Platz für Listen und Anzeige."""
    match reason:
        case "shootoff":
            return f"{word} auf Platz {place}: Stechen"
        case "manual":
            return (
                f"{word}: nach Sportordnung manuell entscheiden (nächstes Kriterium: {criterion})"
            )
        case "missing_data":
            detail = f" für „{criterion}“" if criterion else ""
            return (
                f"{word} nicht auflösbar: Angaben{detail} fehlen (z. B. Seriensumme statt "
                "Einzelschüssen); nach Sportordnung manuell entscheiden"
            )
    return None


def tie_unresolved_text(word: str) -> str:
    """Kurzform in Listen, wenn ein geteilter Platz nicht entschieden ist."""
    return f"{word} nicht auflösbar"


def abort_note(reason: str | None, labels: Sequence[str] = ()) -> str | None:
    """Warum ein Abbruch mit erfassten Werten keinen Platz bekommt."""
    listed = _join(labels)
    match reason:
        case "no_rule":
            return f"{NOT_COMPARABLE}: Regel für nicht geschossene Serien fehlt"
        case "incomplete_series":
            return f"{NOT_COMPARABLE}: {listed or 'Serie'} unvollständig erfasst"
        case "missing_section_time":
            return f"{NOT_COMPARABLE}: Gesamtzeit {listed} fehlt".replace("  ", " ")
        case "invalid":
            return f"{NOT_COMPARABLE}: Rohwerte lassen sich nicht werten"
    return None


def _join(labels: Sequence[str]) -> str:
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])} und {labels[-1]}"
