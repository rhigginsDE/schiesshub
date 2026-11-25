"""Pydantic-Modelle für die YAML-Dateien des Katalogs (Format: catalog/README.md).

Die Modelle sind bewusst streng: unbekannte Felder sind Fehler, Typen werden nicht umgewandelt
(eine Kennziffer muss Text sein). Feldnamen entsprechen den deutschen Schlüsseln der Dateien.
"""

import itertools
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80)]
Text = Annotated[str, Field(min_length=1)]
Code = Annotated[str, Field(pattern=r"^\S+$", max_length=40)]
# Datumsangaben stehen als Text in den Dateien ("2026-06-30").
IsoDate = Annotated[date, Field(strict=False)]
Number = int | float
PositiveNumber = Annotated[int, Field(gt=0)] | Annotated[float, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]

WeaponType = Literal["kurzwaffe", "langwaffe", "flinte", "armbrust", "bogen", "blasrohr", "licht"]
GroupKind = Literal[
    "praezision",
    "speed",
    "kombi",
    "fallscheibe",
    "fallscheibe-gk",
    "fallscheibe-kk",
    "mehrdistanz",
    "zeitserie",
    "fertigkeit",
    "symbolscheibe",
    "intervall",
    "auflage",
    "dreistellung",
    "laufende-scheibe",
    "vogelbaum",
    "wurfscheibe",
    "feldbogen",
    "bogen-3d",
]
ScoringModel = Literal["ringe", "ringe_minus_zeit", "ringe_mit_zeitabzug", "zeit_plus_zuschlaege"]
Stance = Literal["stehend", "kniend", "liegend", "sitzend"]
# "einhaendig": eine Hand, welche ist freigestellt.
Hand = Literal["beidhaendig", "einhaendig", "starke_hand", "schwache_hand"]
Gender = Literal["alle", "weiblich", "maennlich", "divers"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    return sorted({value for value in values if value in seen or seen.add(value)})


# --- katalog.yaml -----------------------------------------------------------


class VerbandInfo(StrictModel):
    kuerzel: Text
    name: Text


class RegelwerkTeil(StrictModel):
    stand: IsoDate
    datei: Text | None = None


class Regelwerk(StrictModel):
    name: Text
    stand: IsoDate
    teile: dict[str, RegelwerkTeil] | None = None
    abgeglichen_am: IsoDate | None = None


class KatalogDatei(StrictModel):
    schema_: Literal[1] = Field(alias="schema")
    id: Slug
    verband: VerbandInfo
    regelwerk: Regelwerk
    status: Literal["entwurf", "geprueft"]
    hinweise: list[Text] = []
    nicht_enthalten: list[Text] = []
    glossar: dict[str, Text] = {}
    offizielle_quellen: list[Text] = []


# --- klassen.yaml -----------------------------------------------------------


class KlassenQuelle(StrictModel):
    regelwerk: Text
    stand: IsoDate
    abschnitte: list[Text] = []


class Stichtag(StrictModel):
    sportjahr: Text | None = None
    bezug: Text | None = None
    hinweis: Text | None = None
    unsicher: bool | None = None


class Klasse(StrictModel):
    id: Slug
    name: Text
    kurz: Text
    geschlecht: Gender
    # Offizielle Klassennummer (DSB: "10" = Herren I), nur innerhalb eines Satzes eindeutig.
    nummer: Code | None = None
    # Klassensatz (Schlüssel aus `klassensaetze`), z. B. "sportschiessen" oder "auflage".
    satz: Slug | None = None
    # Klassen, in die gemeldet werden darf, obwohl das Alter eine andere ergibt (Höhermeldung).
    hoeher_in: list[Slug] = []
    alter_hilfe: Text | None = None
    mindeststarter_dm: PositiveInt | None = None
    zusammenlegen_in: list[Slug] = []
    zusammenlegen_nach_alter: bool = False
    hinweis: Text | None = None


class KlassenDatei(StrictModel):
    schema_: Literal[1] = Field(alias="schema")
    verband: Slug
    quelle: KlassenQuelle | None = None
    geprueft: bool = False
    stichtag: Stichtag | None = None
    geschlecht_hinweis: Text | None = None
    # Klassensätze mit Kurzbeschreibung und Fundstelle (DSB: Kugel, Auflage, Bogen …).
    klassensaetze: dict[Slug, Text] = {}
    klassen: list[Klasse]
    regeln: list[Text] = []
    unsicher: list[Text] = []


# --- gruppen/<gruppe>.yaml --------------------------------------------------


class Gruppe(StrictModel):
    id: Slug
    name: Text
    waffenart: WeaponType
    distanz_m: PositiveInt | None = None
    art: GroupKind


class Wertung(StrictModel):
    modell: ScoringModel
    rangfolge: Literal["absteigend", "aufsteigend"]
    geprueft: bool
    gleichstand: list[Text] | None = None
    abzug_je_voller_sekunde_ueber_sollzeit: Number | None = None
    min_teilergebnis: Number | None = None
    zeit_rundung: Literal["summe_abrunden"] | None = None
    # Speed: Wird eine Serie nicht beendet, zählen die bis dahin erzielten Ringe und die
    # Zeit des letzten Schusses (K 6.10, L 9.09).
    unbeendete_serie: Literal["ringe_bis_dahin_zeit_letzter_schuss"] | None = None
    # Zehntelwertung: Ringwerte mit einer Nachkommastelle (0 und 1,0 bis 10,9).
    zehntelwertung: bool | None = None
    # Ringgleichheit auf den Plätzen 1 bis N wird durch Stechen entschieden (Kriterium "stechen").
    stechen_bis_platz: PositiveInt | None = None
    # DSB SpO 0.12.1: Wer ohne Finale das erzielbare Höchstergebnis erreicht, wird nicht
    # unterschieden (gleicher Rang ohne Gleichstandskette). Nur bei Modell "ringe".
    hoechstergebnis_gleicher_rang: bool | None = None
    # DSB SpO 9.4.3: Gleichstand beim Höchstergebnis entscheidet ein Stechen (Vorrang vor der
    # Kette). Nur bei Modell "ringe", nicht zusammen mit hoechstergebnis_gleicher_rang.
    stechen_bei_hoechstergebnis: bool | None = None
    # Woraus "letzte_serie_rueckwaerts" die verglichenen Serien bildet: "zehn_schuss" = Blöcke zu
    # 10 Schuss (SpO 0.12.1 Nr. 1), "serie" = Serien wie im Ablauf (z. B. 25er bei Flinte, 3.9.1.2).
    # Ohne Angabe: "serie", wenn alle Abschnitte nur Treffer zählen, sonst "zehn_schuss".
    gleichstand_serie: Literal["zehn_schuss", "serie"] | None = None
    # Die Kette `gleichstand` gilt nur für Gleichstände, die auf Platz 1 bis N beginnen
    # (z. B. SpO 9.4.1: Plätze 1–6); ab Platz N+1 gilt `gleichstand_danach` (leer: gleicher Platz).
    gleichstand_bis_platz: PositiveInt | None = None
    gleichstand_danach: list[Text] | None = None

    @model_validator(mode="after")
    def _check_max_score_rule(self) -> Self:
        if self.hoechstergebnis_gleicher_rang and self.modell != "ringe":
            raise ValueError("hoechstergebnis_gleicher_rang gibt es nur bei modell 'ringe'")
        if self.stechen_bei_hoechstergebnis and self.modell != "ringe":
            raise ValueError("stechen_bei_hoechstergebnis gibt es nur bei modell 'ringe'")
        if self.stechen_bei_hoechstergebnis and self.hoechstergebnis_gleicher_rang:
            raise ValueError(
                "stechen_bei_hoechstergebnis und hoechstergebnis_gleicher_rang schließen sich aus"
            )
        if (self.gleichstand_bis_platz is None) != (self.gleichstand_danach is None):
            raise ValueError("gleichstand_bis_platz und gleichstand_danach nur zusammen angeben")
        return self


class Anschlag(StrictModel):
    haltung: Stance
    # Bei Langwaffe und Flinte nicht angegeben.
    hand: Hand | None = None
    # Auflageschießen: Waffe liegt auf einer Auflage.
    aufgelegt: bool | None = None


class Position(StrictModel):
    # Positionsnummer laut Sporthandbuch.
    nr: PositiveInt
    distanz_m: PositiveNumber | None = None
    # Eine oder mehrere erlaubte Alternativen.
    anschlaege: Annotated[list[Anschlag], Field(min_length=1)]
    # n-te Scheibe von links.
    scheibe: PositiveInt | None = None


class Abschnitt(StrictModel):
    id: Slug
    name: Text
    serien: PositiveInt
    schuss_je_serie: PositiveInt | None = None
    max_schuss_je_serie: PositiveInt | None = None
    ziele_je_serie: PositiveInt | None = None
    zeit_je_serie_s: PositiveNumber | None = None
    zeiten_s: list[PositiveNumber] | None = None
    max_zeit_je_serie_s: PositiveNumber | None = None
    zeit_wird_gemessen: bool | None = None
    zuschlag_je_stehender_scheibe_s: Number | None = None
    distanzen_m: list[PositiveNumber] | None = None
    zeit_je_schuss_s: PositiveNumber | None = None
    pause_zwischen_schuessen_s: PositiveNumber | None = None
    sollzeit_s: PositiveNumber | None = None
    max_gesamtzeit_s: PositiveNumber | None = None
    # Anschlag je Serie, z. B. bei Mehrdistanz.
    positionen: list[Position] | None = None
    # Mögliche Ringwerte je Treffer, absteigend (Speed: 10, 7, 0).
    ringwerte: list[NonNegativeInt] | None = None
    # Fallscheibe: Serienzeit bei Zeitlimit oder Abbruch durch den Schützen.
    zeit_bei_abbruch_s: PositiveNumber | None = None
    # Fallscheibe: Zuschlag bei Waffenstörung vor dem ersten Wertungsschuss.
    zuschlag_stoerung_vor_erstem_schuss_s: PositiveNumber | None = None
    # Nur die ersten N Serien zählen (Turnier-Einstellung; im Katalog normalerweise nicht gesetzt).
    serien_gewertet: PositiveInt | None = None
    # Trefferaufnahme nach diesen Serien (1-basiert, aufsteigend), rein informativ.
    trefferaufnahme_nach: list[PositiveInt] | None = None
    # Gesamtzeit für alle Wertungsschüsse des Abschnitts (DSB nennt meist keine Zeit je Serie).
    wettkampfzeit_s: PositiveNumber | None = None
    # Vorbereitungs- und Probezeit vor dem ersten Wertungsschuss.
    vorbereitung_probe_s: PositiveNumber | None = None
    probeschuesse: NonNegativeInt | Literal["unbegrenzt"] | None = None
    # Eingabeschutz, keine Sportregel: Eine gemessene Zeit über Faktor × Zeitlimit
    # (max_zeit_je_serie_s bzw. max_gesamtzeit_s; ohne Angabe 3, ohne Limit eine Stunde) gilt als
    # Tippfehler. zeit_plausibel_max_s setzt die Grenze fest und hat Vorrang.
    zeit_plausibel_faktor: Annotated[int, Field(ge=1)] | Annotated[float, Field(ge=1)] | None = None
    zeit_plausibel_max_s: PositiveNumber | None = None

    @model_validator(mode="after")
    def _check_per_series_lists(self) -> Self:
        for name in ("zeiten_s", "distanzen_m", "positionen"):
            values = getattr(self, name)
            if values is not None and len(values) != self.serien:
                raise ValueError(
                    f"{name} hat {len(values)} Einträge, erwartet werden {self.serien} "
                    "(einer je Serie)"
                )
        if self.positionen is not None and self.distanzen_m is not None:
            for index, (position, distanz) in enumerate(
                zip(self.positionen, self.distanzen_m, strict=True)
            ):
                if position.distanz_m is not None and position.distanz_m != distanz:
                    raise ValueError(
                        f"positionen[{index}].distanz_m ist {position.distanz_m}, "
                        f"distanzen_m[{index}] ist {distanz}"
                    )
        if self.ringwerte is not None:
            if not self.ringwerte:
                raise ValueError("ringwerte darf nicht leer sein")
            if any(a <= b for a, b in zip(self.ringwerte, self.ringwerte[1:], strict=False)):
                raise ValueError(
                    "ringwerte müssen absteigend sortiert sein und dürfen sich nicht wiederholen"
                )
        if self.serien_gewertet is not None and self.serien_gewertet > self.serien:
            raise ValueError(
                f"serien_gewertet ist {self.serien_gewertet}, es gibt nur {self.serien} Serien"
            )
        if self.trefferaufnahme_nach is not None:
            werte = self.trefferaufnahme_nach
            if any(a >= b for a, b in itertools.pairwise(werte)):
                raise ValueError("trefferaufnahme_nach muss aufsteigend sein, ohne Wiederholung")
            if werte and werte[-1] > self.serien:
                raise ValueError(
                    f"trefferaufnahme_nach nennt Serie {werte[-1]}, "
                    f"es gibt nur {self.serien} Serien"
                )
        return self


class Variante(StrictModel):
    id: Slug
    name: Text
    # Gemeinsame Zeit für alle Abschnitte (z. B. Dreistellungskampf mit Wechselzeiten).
    wettkampfzeit_gesamt_s: PositiveNumber | None = None
    abschnitte: Annotated[list[Abschnitt], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_unique_sections(self) -> Self:
        if duplicates := _duplicates([abschnitt.id for abschnitt in self.abschnitte]):
            raise ValueError(f"Abschnitt-ID mehrfach vergeben: {', '.join(duplicates)}")
        return self


class Finale(StrictModel):
    """Finale bzw. Endkampf, nur zur Information (eigene Worte, mit Fundstelle)."""

    teilnehmer: PositiveInt
    hinweis: Text | None = None
    abschnitt: Text | None = None


class Ablauf(StrictModel):
    beschreibung: Text
    finale: Finale | None = None
    varianten: Annotated[list[Variante], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_unique_variants(self) -> Self:
        if duplicates := _duplicates([variante.id for variante in self.varianten]):
            raise ValueError(f"Varianten-ID mehrfach vergeben: {', '.join(duplicates)}")
        return self


class Disziplin(StrictModel):
    kennziffer: Code
    name: Text
    waffe: Text
    munition: Text
    visierung: Text
    anschlag: Text
    scheibe: Text
    ablauf: Slug
    hinweis: Text | None = None
    optional: bool = False
    pruefen: list[Text] = []
    fruehere_kennziffer: Code | None = None


class GruppenDatei(StrictModel):
    schema_: Literal[1] = Field(alias="schema")
    verband: Slug
    gruppe: Gruppe
    wertung: Wertung
    ablaeufe: dict[Slug, Ablauf]
    disziplinen: list[Disziplin]


# --- startrecht.yaml --------------------------------------------------------

KlassenNummer = Code


class MixTeam(StrictModel):
    name: Text
    klassen: Annotated[list[KlassenNummer], Field(min_length=1)]


class Startfelder(StrictModel):
    """Startrecht der Klassen eines Satzes. Alle Klassen sind Klassennummern (`Klasse.nummer`)."""

    einzel: list[KlassenNummer] = []
    mannschaft: list[KlassenNummer] = []
    # Klasse -> Klasse, in der sie mitschießt (DSB-Tabelle: "b 10").
    startet_bei: dict[KlassenNummer, KlassenNummer] = {}
    mannschaft_startet_bei: dict[KlassenNummer, KlassenNummer] = {}
    olympisch: list[KlassenNummer] = []
    # Darf per Höhermeldung (DSB: SpO 0.7.1.1) in einer ausgeschriebenen Klasse starten.
    startmoeglichkeit_0711: list[KlassenNummer] = []
    kein_startrecht: list[KlassenNummer] = []
    endkampf: list[KlassenNummer] = []
    mix_team: list[MixTeam] = []
    neu_bei_dm: list[KlassenNummer] = []
    hinweis: Text | None = None
    # In der Quelle nicht eindeutig lesbar.
    offen: Text | None = None


class StartrechtEintrag(Startfelder):
    """Startrecht in einem Wettbewerb laut Meisterschaftstabelle des Verbands."""

    # Klassensatz; bei mehreren gilt für eine Nummer der erste Satz, der sie kennt
    # (DSB Blasrohr: eigene Schülerklassen, sonst die Klassen des Sportschießens).
    satz: Slug | Annotated[list[Slug], Field(min_length=1)]
    wettbewerb: Text
    # Kennziffer im Katalog, falls sie vom Schlüssel abweicht (z. B. Schlüssel "para-1.10").
    kennziffer: Code | None = None
    meisterschaft: Text | None = None
    deutsche_schuelermeisterschaft: Startfelder | None = None


class StartrechtDatei(StrictModel):
    schema_: Literal[1] = Field(alias="schema")
    verband: Slug
    stand_tabelle: Text | None = None
    hinweise: list[Text] = []
    startrecht: dict[Code, StartrechtEintrag]
