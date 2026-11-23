"""Formelle Begriffe je Verband (Entscheidung vom 23.11.2026).

Ein Wettbewerb nutzt in formellen Ausgaben (Ausschreibung, Aushang, Listen, Anzeige) die Wörter
seines Verbands: „Schützenstand“, „Ergebnisliste“, „Ringgleichheit“ usw. Die Wörter stehen in den
YAML-Dateien neben diesem Modul, nicht im Code:

- `standard.yaml` enthält jeden Schlüssel. Er gilt ohne Verband (eigene Disziplin), für
  unbekannte Verbände und für jedes Wort, das ein Verbandssatz nicht nennt.
- `<verband>.yaml` (Dateiname = `catalog_federation`, klein geschrieben) nennt nur belegte
  Wörter, mit Fundstelle als Kommentar.

Die Dateien werden einmal beim Import gelesen und geprüft; ein Fehler (fehlender oder unbekannter
Schlüssel, leeres Wort) verhindert den Start.
"""

from functools import cache
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DIRECTORY = Path(__file__).parent
STANDARD = "standard"

Wort = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class Begriffe(BaseModel):
    """Ein vollständiger Begriffssatz. Feldname = Schlüssel, Wert = Wort für Menschen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ergebnisliste: Wort = Field(description="Liste mit Ergebnissen und Platzierungen")
    ergebnislisten: Wort = Field(description="Mehrzahl von `ergebnisliste`")
    startliste: Wort = Field(description="Liste der Starts eines Turniers")
    startnummer: Wort = Field(description="Nummer des Schützen im Turnier")
    startzeit: Wort = Field(description="Zeitpunkt, zu dem ein Schütze antreten soll")
    schiessstand: Wort = Field(description="Die Anlage, z. B. „Schießstand 25 m“")
    schiessstaende: Wort = Field(description="Mehrzahl von `schiessstand`")
    schuetzenstand: Wort = Field(description="Platz eines Schützen am Schießstand (nummeriert)")
    schuetzenstaende: Wort = Field(description="Mehrzahl von `schuetzenstand`")
    durchgang: Wort = Field(description="Abgeschlossener Schießblock mit Uhrzeit")
    durchgaenge: Wort = Field(description="Mehrzahl von `durchgang`")
    durchgangszeit: Wort = Field(description="Gemessene Zeit eines Parcours-Durchgangs")
    serie: Wort = Field(description="Feste Zahl von Schüssen im Ablauf („6 Serien à 10 Schuss“)")
    serien: Wort = Field(description="Mehrzahl von `serie`")
    wertungsserie: Wort = Field(description="Serie, die in die Wertung eingeht")
    wertungsserien: Wort = Field(description="Mehrzahl von `wertungsserie`")
    wertungsschuesse: Wort = Field(description="Schüsse, die in die Wertung eingehen")
    trefferaufnahme: Wort = Field(description="Erfassen und Auswerten der Treffer")
    ergebnisgleichheit: Wort = Field(
        description="Gleiches Ergebnis, allgemein (ohne Bezug auf ein Wertungsmodell)"
    )
    ringgleichheit: Wort = Field(description="Gleiches Ergebnis bei Ringwertung")
    treffergleichheit: Wort = Field(description="Gleiches Ergebnis bei Trefferwertung")
    abbruch: Wort = Field(description="Der Schütze bricht seinen Start ab (Bedienung: aufgegeben)")
    abbruch_kurz: Wort = Field(description="Kurzform von `abbruch` in Listen")
    nicht_angetreten: Wort = Field(description="Start trotz Aufruf nicht angetreten")
    disqualifiziert: Wort = Field(description="Aus der Disziplin ausgeschlossen")
    disqualifikation: Wort = Field(description="Ausschluss aus der Disziplin (Hauptwort)")
    einspruch: Wort = Field(description="Einwand gegen eine Entscheidung oder ein Ergebnis")
    protest: Wort = Field(description="Schriftlicher Einwand an das Wettbewerbsgericht")
    protestgebuehr: Wort = Field(description="Gebühr für einen Protest")
    gebuehr_einspruch: Wort = Field(
        description="Gebühr für einen Einspruch gegen das Ergebnis, wie sie die Ausschreibung "
        "nennt (BDS „Protestgebühr“, DSB „Einspruchsgebühr“)"
    )
    standaufsicht: Wort = Field(description="Verantwortliche Aufsichtsperson am Schießstand")
    schiessleiter: Wort = Field(description="Leitet den Schießbetrieb auf dem Schießstand")
    wettkampfleitung: Wort = Field(description="Leitung des Wettkampfs (nicht „Wettkampfleiter“)")
    startgeld: Wort = Field(description="Teilnahmegebühr je Start")
    klasse: Wort = Field(description="Einteilung nach Alter und Geschlecht")
    klassen: Wort = Field(description="Mehrzahl von `klasse`")
    kennziffer: Wort = Field(description="Nummer einer Disziplin im Regelwerk des Verbands")


KEYS: frozenset[str] = frozenset(Begriffe.model_fields)


class BegriffeFehler(ValueError):
    """Eine Begriffsdatei ist nicht gültig."""


def _read(path: Path) -> dict[str, str]:
    """Liest den Abschnitt `begriffe` einer Datei; prüft nur Form und Schlüssel."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or set(data) - {"begriffe"}:
        raise BegriffeFehler(f"{path.name}: erwartet nur den Abschnitt „begriffe“.")
    words = data.get("begriffe") or {}
    if not isinstance(words, dict):
        raise BegriffeFehler(f"{path.name}: „begriffe“ muss eine Zuordnung Schlüssel → Wort sein.")
    if unknown := sorted(set(words) - KEYS):
        raise BegriffeFehler(f"{path.name}: unbekannte Schlüssel {', '.join(unknown)}.")
    for key, value in words.items():
        if not isinstance(value, str) or not value.strip():
            raise BegriffeFehler(f"{path.name}: „{key}“ braucht ein Wort.")
    return words


def load(directory: Path = DIRECTORY) -> tuple[Begriffe, dict[str, Begriffe]]:
    """Liest alle Begriffsdateien eines Verzeichnisses: Standardsatz und je Verband den
    vollständigen Satz (Verbandswörter über dem Standard)."""
    standard_path = directory / f"{STANDARD}.yaml"
    standard_words = _read(standard_path)
    if missing := sorted(KEYS - set(standard_words)):
        raise BegriffeFehler(f"{standard_path.name}: es fehlen {', '.join(missing)}.")
    standard = Begriffe.model_validate(standard_words)
    federations: dict[str, Begriffe] = {}
    for path in sorted(directory.glob("*.yaml")):
        if path.stem == STANDARD:
            continue
        if path.stem != path.stem.lower():
            raise BegriffeFehler(f"{path.name}: Dateiname bitte klein (wie `catalog_federation`).")
        federations[path.stem] = Begriffe.model_validate({**standard_words, **_read(path)})
    return standard, federations


@cache
def _loaded() -> tuple[Begriffe, dict[str, Begriffe]]:
    return load()


def standard() -> Begriffe:
    return _loaded()[0]


def verbaende() -> dict[str, Begriffe]:
    """Vollständiger Satz je Verband, der eine eigene Datei hat."""
    return dict(_loaded()[1])


def begriffe_fuer(verband: str | None) -> Begriffe:
    """Begriffssatz eines Verbands (`catalog_federation`); ohne Verband oder für einen Verband
    ohne eigene Datei der Standardsatz."""
    if verband:
        found = _loaded()[1].get(verband.strip().lower())
        if found is not None:
            return found
    return standard()


# Einmal beim Start lesen: Fehler in den Dateien sollen sofort auffallen, nicht erst bei der
# ersten Ausschreibung.
_loaded()
