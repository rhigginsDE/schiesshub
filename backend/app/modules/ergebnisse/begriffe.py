"""Formelle Wörter der Ergebnislisten – die eine Stelle für Rangliste, Anzeige und Export.

Was formell gedruckt oder angezeigt wird (Ergebnisliste, Aushang, Anzeige), nutzt die Wörter des
Verbands, aus dessen Katalog der Wettbewerb stammt (Entscheidung vom 23.11.2026). Die Wörter
selbst stehen im Begriffssatz je Verband (`app.core.begriffe`, YAML-Dateien mit Fundstellen);
hier wird nur ausgewählt und zusammengesetzt:

- `terms_for(competition.catalog_federation)`: Satz eines Wettbewerbs (eigene Disziplin oder
  Verband ohne eigene Datei: Standardsatz).
- `document_terms(...)`: Satz für Teile über mehrere Wettbewerbe (Dokumenttitel, Dateiname):
  der gemeinsame Verband, sonst (gemischt oder nur eigene Disziplinen) der Standardsatz.
- `abort_label`: „Abbruch (AB)“ (BDS: `abbruch` mit `abbruch_kurz`), beim DSB nur das Wort ohne
  Kurzform, dazu „nicht angetreten“, „disqualifiziert“.
- `tie_word`: Wort für gleiche Ergebnisse je Wertungsmodell (unten).

Fundstellen der BDS-Wörter: `app/core/begriffe/bds.yaml` (Ergebnisliste K 1.14 / L 1.12,
„Abbruch (AB)“ K 1.07 / L 1.05, Ringgleichheit A 9.03, Treffergleichheit L 11.04 / L 12.04);
DSB: `dsb.yaml` (Ergebnisgleichheit 0.12, Treffergleichheit 3.45.6 Flinte).
"""

from collections.abc import Iterable, Sequence

from app.core.begriffe import Begriffe, begriffe_fuer
from app.scoring.criteria import criterion_text
from app.scoring.ranking import MAX_SCORE_NOTE

ABORT_FALLBACK = "abgebrochen"
"""Unbekannter Abbruchgrund (sollte nicht vorkommen)."""

NEUTRAL_TIE = "gleiches Ergebnis"
"""Kein Wort im Regelwerk (Fallscheibe, Speed): neutral."""

NOT_COMPARABLE = "Ergebnis nicht vergleichbar"

RING_MODELS = frozenset({"ringe", "ringe_mit_zeitabzug"})

RESULT_LIST_FILE = "Ergebnisliste"
"""Teil des Dateinamens („Vereinspokal_Ergebnisliste_2027-03-06.pdf“); bleibt ASCII-fest."""


def terms_for(federation: str | None) -> Begriffe:
    """Begriffssatz eines Wettbewerbs nach `catalog_federation`."""
    return begriffe_fuer(federation)


def document_terms(federations: Iterable[str | None]) -> Begriffe:
    """Ein gemeinsamer Verband aller Katalog-Wettbewerbe → sein Satz; sonst der Standardsatz."""
    found = {item.strip().lower() for item in federations if item and item.strip()}
    return begriffe_fuer(found.pop() if len(found) == 1 else None)


def abort_word(terms: Begriffe | None = None) -> str:
    """„Abbruch (AB)“; ohne eigene Kurzform (DSB) nur das Wort."""
    terms = terms or begriffe_fuer(None)
    if terms.abbruch_kurz.strip().lower() == terms.abbruch.strip().lower():
        return terms.abbruch
    return f"{terms.abbruch} ({terms.abbruch_kurz})"


def abort_label(reason: str | None, terms: Begriffe | None = None) -> str | None:
    """„dnf“ → „Abbruch (AB)“; unbekannte Schlüssel als „abgebrochen“; ohne Grund None."""
    if reason is None:
        return None
    terms = terms or begriffe_fuer(None)
    match reason:
        case "dnf":
            return abort_word(terms)
        case "dns":
            return terms.nicht_angetreten
        case "dsq":
            return terms.disqualifiziert
    return ABORT_FALLBACK


def tie_word(
    model: str | None,
    criteria: Sequence[str] = (),
    terms: Begriffe | None = None,
    *,
    hits_only: bool = False,
) -> str:
    """Wort für gleiche Ergebnisse je Wertungsmodell.

    - Trefferwertung: Mehrdistanz mit der Durchgangszeit als Kriterium (BDS L 11.04 / L 12.04)
      oder Werte, die nur Treffer zählen (Wurfscheibe, DSB 3.45.6) → `treffergleichheit`;
    - sonst bei Ringwertung → `ergebnisgleichheit` (BDS und Standard „Ringgleichheit“, DSB
      „Ergebnisgleichheit“);
    - Zeitwertung (Fallscheibe) und Ringe minus Zeit (Speed): Das Sporthandbuch nennt kein Wort
      → „gleiches Ergebnis“."""
    terms = terms or begriffe_fuer(None)
    if model in RING_MODELS and (
        hits_only or (model == "ringe_mit_zeitabzug" and "parcours_zeit" in criteria)
    ):
        return terms.treffergleichheit
    if model in RING_MODELS:
        return terms.ergebnisgleichheit
    return NEUTRAL_TIE


def tie_note(reason: str | None, criterion: str | None, place: int | None, word: str) -> str | None:
    """Hinweis zu einem geteilten Platz für Listen und Anzeige; Kriterien im Klartext."""
    match reason:
        case "max_score":
            return MAX_SCORE_NOTE
        case "shootoff":
            return f"{word} auf Platz {place}: Stechen"
        case "manual":
            return (
                f"{word}: nach Sportordnung manuell entscheiden "
                f"(nächstes Kriterium: {criterion_text(criterion)})"
            )
        case "missing_data":
            detail = f" für „{criterion_text(criterion)}“" if criterion else ""
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


def federation_of(competition: object) -> str | None:
    """`catalog_federation` eines Wettbewerbs, klein geschrieben; None bei eigener Disziplin."""
    value = getattr(competition, "catalog_federation", None) or ""
    return value.strip().lower() or None
