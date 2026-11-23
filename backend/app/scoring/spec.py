"""Form der Wettbewerbsdefinition (`competition.definition`).

Die Definition ist eine Kopie aus dem Katalog: `{"variant": <Variante>, "scoring": <wertung>}` mit
den deutschen Feldnamen der Katalogdateien. Die Modelle sind absichtlich eigenständig und streng:
Kennt die Wertung ein Feld nicht, ist das ein Fehler – so fällt auf, wenn der Katalog etwas
Neues beschreibt, das die Wertung (noch) nicht versteht.
"""

import re
from decimal import Decimal
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app.scoring.numbers import to_decimal

Number = Annotated[Decimal, BeforeValidator(to_decimal)]
NonNegativeNumber = Annotated[Decimal, BeforeValidator(to_decimal), Field(ge=0)]
PositiveNumber = Annotated[Decimal, BeforeValidator(to_decimal), Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
# Ohne `ringwerte` gelten 0–10 und „X“; mit `ringwerte` genau die dort genannten (Bogen 3D: 11).
RingValue = NonNegativeInt | Literal["X"]
Text = Annotated[str, Field(min_length=1)]

_CRITERION_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def _check_criterion_id(value: str) -> str:
    if not _CRITERION_ID.match(value):
        raise ValueError(
            f"Gleichstandskriterium „{value}“: nur Kleinbuchstaben a–z, Ziffern und Unterstrich"
        )
    return value


# Jede ID in diesem Format wird angenommen; was die Wertung nicht rechnet, ist manuell zu
# entscheiden (siehe `ranking.py`).
CriterionId = Annotated[str, AfterValidator(_check_criterion_id)]

Direction = Literal["absteigend", "aufsteigend"]
CaptureMode = Literal["shot", "series"]
CAPTURE_MODES: tuple[CaptureMode, ...] = ("shot", "series")

# Gleichstandskriterien, die die Wertung selbst rechnet (Bedeutung: `ranking.py`). Andere IDs
# sind erlaubt, werden aber nicht gerechnet: Ab der ersten solchen ID ist ein verbleibender
# Gleichstand nach Sportordnung manuell zu entscheiden.
TIE_BREAKERS = (
    "zehner",
    "innenzehner",
    "neuner_abwaerts",
    "parcours_zeit",
    "letzte_serie_rueckwaerts",
    "schuesse_rueckwaerts",
    "ergebnis_zweite_haelfte",
    "mehr_treffer",
    "zehntel_gesamt",
    "elfer",
    "neuner",
    "sechser",
    "fuenfer",
)
# Stechen rechnet die Wertung nie; mit `stechen_bis_platz` gilt es nur für die Plätze bis N.
SHOOTOFF = "stechen"

# Felder unter `scoring`, die nur bestimmte Modelle auswerten (`false` zählt als nicht gesetzt).
MODEL_PARAMETERS = (
    "abzug_je_voller_sekunde_ueber_sollzeit",
    "min_teilergebnis",
    "zeit_rundung",
    "unbeendete_serie",
    "zehntelwertung",
    "hoechstergebnis_gleicher_rang",
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class StanceSpec(_Strict):
    """Ein erlaubter Anschlag an einer Position."""

    haltung: Literal["stehend", "kniend", "liegend", "sitzend"]
    hand: Literal["beidhaendig", "einhaendig", "starke_hand", "schwache_hand"] | None = None
    aufgelegt: bool | None = None
    """Auflageschießen; nur Hinweis."""


class PositionSpec(_Strict):
    """Position einer Serie (Mehrdistanz); nur Hinweis für das Terminal, ohne Einfluss auf die
    Wertung."""

    nr: PositiveInt
    distanz_m: PositiveNumber | None = None
    anschlaege: Annotated[list[StanceSpec], Field(min_length=1)]
    scheibe: PositiveInt | None = None


class SectionSpec(_Strict):
    """Ein Abschnitt (Katalog: `abschnitte[]`)."""

    id: Text
    name: Text
    serien: PositiveInt
    schuss_je_serie: PositiveInt | None = None
    max_schuss_je_serie: PositiveInt | None = None
    ziele_je_serie: PositiveInt | None = None
    zeit_je_serie_s: PositiveNumber | None = None
    zeiten_s: list[PositiveNumber] | None = None
    max_zeit_je_serie_s: PositiveNumber | None = None
    zeit_wird_gemessen: bool | None = None
    zuschlag_je_stehender_scheibe_s: NonNegativeNumber | None = None
    distanzen_m: list[PositiveNumber] | None = None
    zeit_je_schuss_s: PositiveNumber | None = None
    pause_zwischen_schuessen_s: PositiveNumber | None = None
    sollzeit_s: PositiveNumber | None = None
    max_gesamtzeit_s: PositiveNumber | None = None
    positionen: list[PositionSpec] | None = None
    serien_gewertet: PositiveInt | None = None
    trefferaufnahme_nach: list[PositiveInt] | None = None
    ringwerte: Annotated[list[RingValue], Field(min_length=1)] | None = None
    zeit_bei_abbruch_s: PositiveNumber | None = None
    zuschlag_stoerung_vor_erstem_schuss_s: NonNegativeNumber | None = None
    # Plausibilität gemessener Zeiten (siehe `raw.py`): höchstens Faktor × Zeitlimit
    # (`max_zeit_je_serie_s` bzw. `max_gesamtzeit_s`, Standard 3), ohne Limit eine Stunde;
    # `zeit_plausibel_max_s` setzt die Grenze fest.
    zeit_plausibel_faktor: Annotated[Decimal, BeforeValidator(to_decimal), Field(ge=1)] | None = (
        None
    )
    zeit_plausibel_max_s: PositiveNumber | None = None
    # Nur Information für Maske und Ablauf, ohne Einfluss auf die Rechnung:
    wettkampfzeit_s: PositiveNumber | None = None
    """Gesamtzeit für alle Wertungsschüsse des Abschnitts."""
    vorbereitung_probe_s: PositiveNumber | None = None
    """Vorbereitungs- und Probezeit vor dem ersten Wertungsschuss."""
    probeschuesse: NonNegativeInt | Literal["unbegrenzt"] | None = None

    @model_validator(mode="after")
    def _check_per_series_lists(self) -> Self:
        for name in ("zeiten_s", "distanzen_m", "positionen"):
            values = getattr(self, name)
            if values is not None and len(values) != self.serien:
                raise ValueError(
                    f"{name} hat {len(values)} Einträge, erwartet werden {self.serien} "
                    "(einer je Serie)"
                )
        if self.ringwerte and len(set(self.ringwerte)) != len(self.ringwerte):
            raise ValueError("ringwerte enthält einen Wert mehrfach")
        if self.serien_gewertet is not None and self.serien_gewertet > self.serien:
            raise ValueError(
                f"serien_gewertet ist {self.serien_gewertet}, es gibt nur {self.serien} Serien"
            )
        breaks = self.trefferaufnahme_nach or []
        if any(number > self.serien for number in breaks):
            raise ValueError(f"trefferaufnahme_nach: Seriennummern höchstens {self.serien}")
        if any(a >= b for a, b in pairwise(breaks)):
            raise ValueError("trefferaufnahme_nach: Seriennummern aufsteigend und ohne Doppelte")
        if self.positionen and self.distanzen_m:
            for index, position in enumerate(self.positionen):
                distance = self.distanzen_m[index]
                if position.distanz_m is not None and position.distanz_m != distance:
                    raise ValueError(
                        f"positionen[{index}].distanz_m ist {position.distanz_m}, "
                        f"distanzen_m[{index}] aber {distance}"
                    )
        return self


class VariantSpec(_Strict):
    id: Text
    name: Text
    wettkampfzeit_gesamt_s: PositiveNumber | None = None
    """Gemeinsame Zeit über alle Abschnitte (z. B. Dreistellungskampf); nur Information."""
    abschnitte: Annotated[list[SectionSpec], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_unique_sections(self) -> Self:
        ids = [section.id for section in self.abschnitte]
        if duplicates := sorted({i for i in ids if ids.count(i) > 1}):
            raise ValueError(f"Abschnitt-ID mehrfach vergeben: {', '.join(duplicates)}")
        return self


class ScoringSpec(_Strict):
    """Die Wertung (Katalog: `wertung`). `modell` ist Text, damit ein unbekanntes Modell eine
    eigene, verständliche Meldung bekommt."""

    modell: Text
    rangfolge: Direction
    geprueft: bool | None = None
    gleichstand: list[CriterionId] | None = None
    abzug_je_voller_sekunde_ueber_sollzeit: NonNegativeNumber | None = None
    min_teilergebnis: Number | None = None
    zeit_rundung: Literal["summe_abrunden"] | None = None
    unbeendete_serie: Literal["ringe_bis_dahin_zeit_letzter_schuss"] | None = None
    zehntelwertung: bool | None = None
    """Ringe je Schuss 0 oder 1,0–10,9 (eine Nachkommastelle); nur Modell `ringe`."""
    stechen_bis_platz: PositiveInt | None = None
    """Gleichstand im Ergebnis auf den Plätzen 1 bis N entscheidet ein Stechen (nicht die
    Wertung); die übrigen Plätze trennt `gleichstand` ohne `stechen`."""
    hoechstergebnis_gleicher_rang: bool | None = None
    """Wer das erzielbare Höchstergebnis erreicht, wird bei Ergebnisgleichheit nicht
    unterschieden (DSB-SpO 0.12.1 Satz 1): gleicher Platz ohne Gleichstandskette und ohne
    Stechen. Nur Modell `ringe`."""


class DefinitionSpec(_Strict):
    variant: VariantSpec
    scoring: ScoringSpec
