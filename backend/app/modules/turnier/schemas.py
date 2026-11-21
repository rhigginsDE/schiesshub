"""Ein- und Ausgabeformate des Moduls `turnier`. Feldnamen englisch wie im Datenmodell.

Eingaben sind streng: unbekannte Felder sind Fehler, Typen werden nicht umgewandelt. Die Felder
in `definition` stammen aus dem Katalog und behalten dessen deutsche Schreibweise.
"""

from datetime import date, datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.katalog.fileformat import Variante, Wertung

# UUIDs und Datumsangaben kommen als Text aus dem JSON und dürfen umgewandelt werden.
Id = Annotated[UUID, Field(strict=False)]
IsoDate = Annotated[date, Field(strict=False)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Short = Annotated[str, Field(min_length=1, max_length=40)]
ClassCode = Annotated[str, Field(pattern=r"^\S+$", min_length=1, max_length=80)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
Sort = Annotated[int, Field(ge=0)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]

TournamentStatus = Literal["draft", "active", "closed"]
Template = Literal["open", "club_championship", "custom"]
CaptureMode = Literal["shot", "series"]
MultiStartRule = Literal["best", "first", "all"]
Planning = Literal["queue", "schedule"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def check_multi_start(multi_start: bool | None, max_starts: int | None) -> None:
    if multi_start is False and max_starts is not None and max_starts != 1:
        raise ValueError(
            "Ohne Mehrfachstart ist genau ein Start möglich; die Höchstzahl der Starts muss 1 sein."
        )


# --- Turnier-Einstellungen ---------------------------------------------------


class TournamentSettings(StrictModel):
    """Einstellungen je Turnier. Die `default_*`-Werte gelten für neu angelegte Wettbewerbe."""

    # Einspruchsfrist in Minuten; null = keine Frist.
    protest_minutes: NonNegativeInt | None = None
    currency: Currency = "EUR"
    default_fee_first_cents: NonNegativeInt = 0
    default_fee_repeat_cents: NonNegativeInt = 0
    default_multi_start: bool = False
    default_max_starts: PositiveInt = 1
    default_multi_start_rule: MultiStartRule = "best"
    # Wechselzeit (Scheibenwechsel, Trefferaufnahme) je Durchgang bei Zeitplan.
    default_changeover_minutes: NonNegativeInt = 5
    default_capture_mode: CaptureMode = "series"
    # Voreinstellungen für die Anzeige; Inhalt bestimmt das Modul `anzeige`.
    display: dict[str, Any] = {}

    @model_validator(mode="after")
    def _check_defaults(self) -> Self:
        check_multi_start(self.default_multi_start, self.default_max_starts)
        return self


class TournamentSettingsUpdate(StrictModel):
    """Teiländerung der Einstellungen: Nur mitgeschickte Schlüssel werden übernommen."""

    protest_minutes: NonNegativeInt | None = None
    currency: Currency | None = None
    default_fee_first_cents: NonNegativeInt | None = None
    default_fee_repeat_cents: NonNegativeInt | None = None
    default_multi_start: bool | None = None
    default_max_starts: PositiveInt | None = None
    default_multi_start_rule: MultiStartRule | None = None
    default_changeover_minutes: NonNegativeInt | None = None
    default_capture_mode: CaptureMode | None = None
    display: dict[str, Any] | None = None


# --- Turnier -----------------------------------------------------------------


class TournamentCreate(StrictModel):
    name: Name
    organizer: Name | None = None
    date_from: IsoDate
    # Ohne Angabe: eintägig.
    date_to: IsoDate | None = None
    # Die Vorlage setzt die Standardwerte in `settings`; mitgeschickte Einstellungen gehen vor.
    template: Template = "custom"
    settings: TournamentSettingsUpdate | None = None


class TournamentUpdate(StrictModel):
    name: Name | None = None
    organizer: Name | None = None
    date_from: IsoDate | None = None
    date_to: IsoDate | None = None
    settings: TournamentSettingsUpdate | None = None


class StatusChange(StrictModel):
    status: TournamentStatus


class TournamentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    organizer: str | None
    date_from: date
    date_to: date
    status: TournamentStatus
    template: Template
    settings: TournamentSettings
    created_at: datetime
    updated_at: datetime


# --- Stand -------------------------------------------------------------------


class RangeCreate(StrictModel):
    name: Name
    lane_count: PositiveInt
    # Ohne Angabe: ans Ende.
    sort: Sort | None = None


class RangeUpdate(StrictModel):
    name: Name | None = None
    lane_count: PositiveInt | None = None
    sort: Sort | None = None


class RangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    name: str
    lane_count: int
    sort: int


class Order(StrictModel):
    """Neue Reihenfolge: alle IDs der Liste, jede genau einmal."""

    ids: list[Id]


# --- Klasse ------------------------------------------------------------------


class ClassCreate(StrictModel):
    code: ClassCode
    name: Name
    short: Short
    sort: Sort | None = None
    merge_into_id: Id | None = None


class ClassUpdate(StrictModel):
    code: ClassCode | None = None
    name: Name | None = None
    short: Short | None = None
    sort: Sort | None = None
    # null hebt die Zusammenlegung auf.
    merge_into_id: Id | None = None


class ClassImport(StrictModel):
    federation: Annotated[str, Field(min_length=1, max_length=80)]


class ClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    code: str
    name: str
    short: str
    sort: int
    merge_into_id: UUID | None


# --- Wettbewerb --------------------------------------------------------------


class DefinitionSource(StrictModel):
    """Woher die Definition kopiert wurde."""

    federation: Annotated[str, Field(min_length=1)]
    code: Annotated[str, Field(min_length=1)]
    group: Annotated[str, Field(min_length=1)]
    # Stand des Regelwerks laut Katalog zum Zeitpunkt der Kopie.
    catalog_stand: IsoDate


class CompetitionDefinition(StrictModel):
    """Kopie von Ablauf-Variante und Wertung; geprüft mit denselben Modellen wie der Katalog."""

    # Fehlt bei eigenen Wettbewerben ohne Katalog.
    source: DefinitionSource | None = None
    variant: Variante
    scoring: Wertung
    ablauf_beschreibung: Annotated[str, Field(min_length=1)] | None = None


class CompetitionSettings(StrictModel):
    """Felder, die beim Anlegen und Ändern gleich sind. Ohne Angabe gilt der Turnier-Standard."""

    name: Name | None = None
    range_id: Id | None = None
    sort: Sort | None = None
    capture_mode: CaptureMode | None = None
    multi_start: bool | None = None
    max_starts: PositiveInt | None = None
    multi_start_rule: MultiStartRule | None = None
    fee_first_cents: NonNegativeInt | None = None
    fee_repeat_cents: NonNegativeInt | None = None
    # Leer: alle Klassen des Turniers sind zugelassen.
    class_ids: list[Id] | None = None
    combined_ranking: bool | None = None
    planning: Planning | None = None
    # Dauer eines Durchgangs einschließlich Wechselzeit.
    heat_minutes: PositiveInt | None = None
    changeover_minutes: NonNegativeInt | None = None

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        check_multi_start(self.multi_start, self.max_starts)
        if self.class_ids is not None and len(set(self.class_ids)) != len(self.class_ids):
            raise ValueError("Eine Klasse ist mehrfach angegeben.")
        return self


class CompetitionCreate(CompetitionSettings):
    """Aus dem Katalog (`catalog_federation` + `catalog_code`) oder eigen (`definition`)."""

    catalog_federation: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    catalog_code: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    # Ablauf-Variante aus dem Katalog; ohne Angabe die erste.
    variant_id: Annotated[str, Field(min_length=1)] | None = None
    definition: CompetitionDefinition | None = None

    @model_validator(mode="after")
    def _check_origin(self) -> Self:
        from_catalog = self.catalog_federation is not None or self.catalog_code is not None
        if from_catalog:
            if self.catalog_federation is None or self.catalog_code is None:
                raise ValueError(
                    "Für einen Wettbewerb aus dem Katalog werden Verband und Kennziffer benötigt."
                )
            if self.definition is not None:
                raise ValueError(
                    "Entweder aus dem Katalog anlegen oder eine eigene Definition mitgeben, "
                    "nicht beides."
                )
            return self
        if self.definition is None:
            raise ValueError(
                "Bitte Verband und Kennziffer aus dem Katalog angeben oder eine eigene "
                "Definition mitgeben."
            )
        if self.variant_id is not None:
            raise ValueError(
                "Eine Variante lässt sich nur bei Wettbewerben aus dem Katalog wählen."
            )
        if self.definition.source is not None:
            raise ValueError("Ein eigener Wettbewerb hat keine Katalog-Herkunft (source).")
        if self.name is None:
            raise ValueError("Ein eigener Wettbewerb braucht einen Namen.")
        return self


class CompetitionUpdate(CompetitionSettings):
    # Ersetzt die Definition. `source` darf fehlen (bleibt dann erhalten), aber nicht abweichen.
    definition: CompetitionDefinition | None = None


class DefinitionReset(StrictModel):
    # Ohne Angabe die Variante der aktuellen Definition.
    variant_id: Annotated[str, Field(min_length=1)] | None = None


class CompetitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    range_id: UUID | None
    sort: int
    catalog_federation: str | None
    catalog_code: str | None
    name: str
    definition: CompetitionDefinition
    capture_mode: CaptureMode
    multi_start: bool
    max_starts: int
    multi_start_rule: MultiStartRule
    fee_first_cents: int
    fee_repeat_cents: int
    class_ids: list[UUID]
    combined_ranking: bool
    planning: Planning
    heat_minutes: int | None
    changeover_minutes: int


# --- Übersicht ---------------------------------------------------------------


class TournamentOverview(TournamentOut):
    ranges: list[RangeOut]
    classes: list[ClassOut]
    competitions: list[CompetitionOut]
