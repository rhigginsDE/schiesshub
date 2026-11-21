"""Pydantic-Modelle für die YAML-Dateien des Katalogs (Format: catalog/README.md).

Die Modelle sind bewusst streng: unbekannte Felder sind Fehler, Typen werden nicht umgewandelt
(eine Kennziffer muss Text sein). Feldnamen entsprechen den deutschen Schlüsseln der Dateien.
"""

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

WeaponType = Literal["kurzwaffe", "langwaffe", "flinte"]
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
]
ScoringModel = Literal["ringe", "ringe_minus_zeit", "ringe_mit_zeitabzug", "zeit_plus_zuschlaege"]
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

    @model_validator(mode="after")
    def _check_per_series_lists(self) -> Self:
        for name in ("zeiten_s", "distanzen_m"):
            values = getattr(self, name)
            if values is not None and len(values) != self.serien:
                raise ValueError(
                    f"{name} hat {len(values)} Einträge, erwartet werden {self.serien} "
                    "(einer je Serie)"
                )
        return self


class Variante(StrictModel):
    id: Slug
    name: Text
    abschnitte: Annotated[list[Abschnitt], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_unique_sections(self) -> Self:
        if duplicates := _duplicates([abschnitt.id for abschnitt in self.abschnitte]):
            raise ValueError(f"Abschnitt-ID mehrfach vergeben: {', '.join(duplicates)}")
        return self


class Ablauf(StrictModel):
    beschreibung: Text
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
