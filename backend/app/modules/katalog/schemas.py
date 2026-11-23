"""Antwortformate der Katalog-API. Feldnamen deutsch wie in den Katalogdateien."""

from datetime import date, datetime

from pydantic import BaseModel

from app.modules.katalog.fileformat import Finale, StartrechtEintrag, Variante, Wertung


class RegelwerkOut(BaseModel):
    name: str
    stand: date


class VerbandOut(BaseModel):
    id: str
    kuerzel: str
    name: str
    regelwerk: RegelwerkOut
    status: str
    anzahl_gruppen: int
    anzahl_disziplinen: int


class GruppeOut(BaseModel):
    verband: str
    id: str
    name: str
    waffenart: str
    distanz_m: int | None
    art: str
    # Anzahl der Disziplinen in der Gruppe.
    anzahl: int
    wertung_modell: str
    geprueft: bool


class DisziplinOut(BaseModel):
    verband: str
    kennziffer: str
    name: str
    gruppe_id: str
    gruppe_name: str
    waffe: str
    munition: str
    visierung: str
    anschlag: str
    scheibe: str
    optional: bool
    hinweis: str | None


class AblaufOut(BaseModel):
    schluessel: str
    beschreibung: str
    finale: Finale | None = None
    varianten: list[Variante]


class DisziplinDetailOut(DisziplinOut):
    pruefen: list[str]
    fruehere_kennziffer: str | None
    ablauf: AblaufOut
    wertung: Wertung


class KlasseOut(BaseModel):
    verband: str
    id: str
    name: str
    kurz: str
    geschlecht: str
    alter_hilfe: str | None
    mindeststarter_dm: int | None
    zusammenlegen_in: list[str]
    zusammenlegen_nach_alter: bool
    hinweis: str | None
    # Offizielle Klassennummer und Klassensatz (DSB), sonst leer.
    nummer: str | None
    satz: str | None
    hoeher_in: list[str]


class StartrechtOut(BaseModel):
    """Startrecht je Wettbewerb laut Meisterschaftstabelle (Inhalt der startrecht.yaml)."""

    verband: str
    stand_tabelle: str | None
    hinweise: list[str]
    # Schlüssel = Kennziffer bzw. "<satz>-<kennziffer>"; Klassen als Klassennummern im Satz.
    startrecht: dict[str, StartrechtEintrag]


class KatalogFehlerOut(BaseModel):
    verband: str | None
    datei: str | None
    pfad: str | None
    meldung: str


class KatalogStatusOut(BaseModel):
    verbaende: int
    gruppen: int
    disziplinen: int
    klassen: int
    # Zeitpunkt, zu dem zuletzt ein Verband erfolgreich übernommen wurde.
    importiert_am: datetime | None
    # Fehler des letzten Importversuchs; betroffene Verbände zeigen ihren alten Stand.
    fehler: list[KatalogFehlerOut]
