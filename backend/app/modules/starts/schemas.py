"""Ein- und Ausgabeformate des Moduls `starts`. Feldnamen englisch wie im Datenmodell.

Eingaben sind streng: unbekannte Felder sind Fehler, Typen werden nicht umgewandelt (außer
UUIDs und Zeitpunkten, die als Text aus dem JSON kommen).
"""

from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.modules.starts.rules import AbortReason, StartStatus
from app.modules.turnier.schemas import Id, PositiveInt, StrictModel

# Zeitpunkt mit Zeitzone; gespeichert und ausgegeben in UTC.
Instant = Annotated[
    AwareDatetime, Field(strict=False), AfterValidator(lambda value: value.astimezone(UTC))
]


# --- Anmeldung ---------------------------------------------------------------


class EntryCreate(StrictModel):
    person_id: Id
    class_id: Id
    # Ohne Angabe: die nächste freie Nummer ab `settings.first_start_number` des Turniers.
    start_number: PositiveInt | None = None


class EntryUpdate(StrictModel):
    class_id: Id | None = None
    start_number: PositiveInt | None = None


class EntryPersonOut(BaseModel):
    id: UUID
    # Klartext; nur über Endpunkte mit `entry.read`.
    name: str
    # Wie die Person auf Anzeige und Listen erscheint (null bei `hidden`).
    display_name: str | None
    # Vereinsname, unabhängig von `show_club` (für die Anmeldung).
    club: str | None


class StartOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entry_id: UUID
    competition_id: UUID
    attempt: int
    fee_cents: int
    status: StartStatus
    abort_reason: AbortReason | None
    queue_position: int | None
    heat_id: UUID | None
    lane: int | None
    created_at: datetime
    updated_at: datetime


class EntryOut(BaseModel):
    id: UUID
    tournament_id: UUID
    start_number: int
    class_id: UUID
    person: EntryPersonOut
    starts: list[StartOut]
    # Summe der Beträge aller gebuchten Starts (Version 1: nur Anzeige, keine Zahlungsbuchung).
    fee_total_cents: int
    created_at: datetime
    updated_at: datetime


# --- Start -------------------------------------------------------------------


class StartBooking(StrictModel):
    competition_id: Id
    count: Annotated[int, Field(ge=1, le=99)] = 1
    # Nur bei Zeitplan: gleich einen Platz buchen. Ohne `lane` die erste freie Bahn.
    heat_id: Id | None = None
    lane: PositiveInt | None = None


class AbortRequest(StrictModel):
    abort_reason: AbortReason


class CallRequest(StrictModel):
    # Reihenfolge: ohne Angabe die erste freie Bahn. Zeitplan: die Bahn des Durchgangs.
    lane: PositiveInt | None = None


class ReturnRequest(StrictModel):
    # Wohin der Start in der Reihenfolge zurückkommt.
    position: Literal["front", "back"] = "back"


class MoveRequest(StrictModel):
    """Genau eins von beiden: eine Stelle nach oben/unten oder an eine Position (ab 1)."""

    direction: Literal["up", "down"] | None = None
    position: PositiveInt | None = None

    @model_validator(mode="after")
    def _one_of(self) -> Self:
        if (self.direction is None) == (self.position is None):
            raise ValueError("Bitte entweder eine Richtung (up/down) oder eine Position angeben.")
        return self


class SlotRequest(StrictModel):
    heat_id: Id
    # Ohne Angabe die erste freie Bahn des Durchgangs.
    lane: PositiveInt | None = None


# --- Durchgang ---------------------------------------------------------------


class HeatCreate(StrictModel):
    starts_at: Instant
    ends_at: Instant
    # Ohne Angabe: die nächste Nummer auf dem Stand.
    number: PositiveInt | None = None


class HeatUpdate(StrictModel):
    starts_at: Instant | None = None
    ends_at: Instant | None = None
    number: PositiveInt | None = None


class HeatSeries(StrictModel):
    """Durchgänge hintereinander; Dauer je Durchgang aus `heat_minutes` des Wettbewerbs."""

    competition_id: Id
    starts_at: Instant
    count: Annotated[int, Field(ge=1, le=200)]


class HeatOut(BaseModel):
    id: UUID
    range_id: UUID
    number: int
    starts_at: datetime
    ends_at: datetime
    # Belegte Plätze (ohne abgebrochene Starts) und Kapazität (= Bahnen des Stands).
    booked: int
    capacity: int


class NextSlotOut(BaseModel):
    heat: HeatOut
    lane: int


# --- Sichten für die Stationen -----------------------------------------------


class StationStartOut(BaseModel):
    """Ein Start in Startliste, Reihenfolge und Standanzeige. Nie mit vollem Namen."""

    start_id: UUID
    entry_id: UUID
    start_number: int
    # Nach Anzeige-Einstellung der Person: voll, abgekürzt oder null.
    display_name: str | None
    # Nur wenn die Person `show_club` gewählt hat.
    club: str | None
    class_id: UUID
    class_short: str
    competition_id: UUID
    competition_name: str
    range_id: UUID | None
    attempt: int
    status: StartStatus
    abort_reason: AbortReason | None
    queue_position: int | None
    lane: int | None
    heat_id: UUID | None
    heat_number: int | None
    heat_starts_at: datetime | None


class LaneOut(BaseModel):
    lane: int
    # Der aufgerufene Start auf dieser Bahn, null wenn frei.
    start: StationStartOut | None


class QueueOut(BaseModel):
    range_id: UUID
    lane_count: int
    # Wartende Starts der Reihenfolge, nach `queue_position`.
    waiting: list[StationStartOut]
    lanes: list[LaneOut]


class RangeNowOut(BaseModel):
    """„Am Stand“ und „als Nächstes“ für Anzeige und Erfassung."""

    range_id: UUID
    lane_count: int
    lanes: list[LaneOut]
    # Nächster Durchgang mit wartenden Starts (Zeitplan), mit seinen Starts.
    next_heat: HeatOut | None
    next_heat_starts: list[StationStartOut]
    # Die nächsten Wartenden der Reihenfolge (höchstens so viele wie Bahnen).
    next_queue: list[StationStartOut]
