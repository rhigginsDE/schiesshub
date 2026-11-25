"""Ein- und Ausgabeformate des Moduls `starts`. Feldnamen englisch wie im Datenmodell.

Eingaben sind streng: unbekannte Felder sind Fehler, Typen werden nicht umgewandelt (außer
UUIDs und Zeitpunkten, die als Text aus dem JSON kommen).
"""

from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

# 409-Antwort: gemeinsamer Baustein, hier weiter erreichbar.
from app.core.errors import ConflictOut as ConflictOut
from app.core.errors import FieldError
from app.modules.starts.rules import AbortReason, StartStatus
from app.modules.turnier.schemas import Id, PositiveInt, StrictModel

# Zeitpunkt mit Zeitzone; gespeichert und ausgegeben in UTC.
Instant = Annotated[
    AwareDatetime, Field(strict=False), AfterValidator(lambda value: value.astimezone(UTC))
]
# Bemerkung zum Abbruch; dieselben Grenzen wie der Grund im Modul `ergebnisse`.
AbortNote = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


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
    # Steht gerade auf `lane` und belegt sie (aufgerufen oder erfasst, noch nicht freigegeben).
    on_lane: bool
    # Zeitpunkt des Aufrufs auf den Schützenstand („seit hh:mm“); leer, solange der Start wartet.
    called_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StartRightNoticeOut(BaseModel):
    """Warnung oder Hinweis zum Startrecht laut Meisterschaftstabelle des Verbands.

    Nie ein Grund zur Ablehnung: Der Start bleibt möglich. Der Text ist fertig formuliert.
    """

    # kein_startrecht, nicht_ausgeschrieben (severity warning); startet_bei,
    # startmoeglichkeit_0711 (severity hint).
    code: Literal[
        "startet_bei", "startmoeglichkeit_0711", "kein_startrecht", "nicht_ausgeschrieben"
    ]
    severity: Literal["warning", "hint"]
    message_de: str
    # Fundstelle: Tabelle, Stand und Eintrag.
    source: str


class EntryStartOut(StartOut):
    """Ein Start in der Ausgabe für die Anmeldung, mit Startrecht laut Verbandstabelle."""

    # Leer, wenn die Klasse startberechtigt ist oder es nichts zu sagen gibt (eigener
    # Wettbewerb, eigene Klasse, Verband ohne Startrecht-Tabelle).
    start_rights: list[StartRightNoticeOut] = []


class EntryOut(BaseModel):
    id: UUID
    tournament_id: UUID
    start_number: int
    class_id: UUID
    person: EntryPersonOut
    starts: list[EntryStartOut]
    # Summe der Beträge aller gebuchten Starts (Version 1: nur Anzeige, keine Zahlungsbuchung).
    fee_total_cents: int
    created_at: datetime
    updated_at: datetime


# --- Start -------------------------------------------------------------------


class StartBooking(StrictModel):
    competition_id: Id
    count: Annotated[int, Field(ge=1, le=99)] = 1
    # Nur bei Zeitplan: gleich einen Platz buchen. Ohne `lane` der erste freie Schützenstand.
    heat_id: Id | None = None
    lane: PositiveInt | None = None


class StartRightCheckOut(BaseModel):
    """Vorab-Auskunft zum Startrecht einer Klasse in einem Wettbewerb, vor dem Buchen."""

    competition_id: UUID
    competition_name: str
    # Kennziffer aus dem Katalog; null bei eigenem Wettbewerb.
    competition_code: str | None
    # startberechtigt | startet_bei | startmoeglichkeit_0711 | kein_startrecht |
    # nicht_ausgeschrieben | keine_angabe (kein Eintrag, keine Tabelle, Klasse ohne Nummer).
    status: Literal[
        "startberechtigt",
        "startet_bei",
        "startmoeglichkeit_0711",
        "kein_startrecht",
        "nicht_ausgeschrieben",
        "keine_angabe",
    ]
    start_rights: list[StartRightNoticeOut]


class AbortRequest(StrictModel):
    abort_reason: AbortReason
    # Bemerkung zum Abbruch, wie `reason` bei `POST …/result/abort` (1–500 Zeichen).
    note: AbortNote | None = None


class CallRequest(StrictModel):
    # Reihenfolge: ohne Angabe der erste freie Schützenstand. Zeitplan: der des Durchgangs.
    lane: PositiveInt | None = None
    # Reihenfolge: auch auf einen Schützenstand, den ein bald beginnender Durchgang braucht
    # (sonst 409 mit `code: heat_imminent`). Ohne `lane` wird zuerst einer genommen, den kein
    # Durchgang braucht.
    confirm_heat_conflict: bool = False


class CallConflictOut(BaseModel):
    """HTTP 409 beim Aufrufen. `code` nur bei `heat_imminent` (dann ohne `errors`)."""

    detail: str
    errors: list[FieldError] | None = None
    code: Literal["heat_imminent"] | None = None


class CallNextRequest(StrictModel):
    # Nur diesen Schützenstand füllen („Nächsten auf Schützenstand N“); sonst alle freien.
    lane: PositiveInt | None = None
    # Auch Schützenstände füllen, die ein bald beginnender Durchgang braucht. Ohne Bestätigung
    # bleiben sie frei (Antwort: `held_lanes`); ist sonst keiner frei, kommt 409 `heat_imminent`.
    confirm_heat_conflict: bool = False


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
    # Ohne Angabe der erste freie Schützenstand des Durchgangs.
    lane: PositiveInt | None = None


# --- Durchgang ---------------------------------------------------------------


class HeatCreate(StrictModel):
    starts_at: Instant
    ends_at: Instant
    # Ohne Angabe: die nächste Nummer auf dem Schießstand.
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
    # Belegte Plätze (ohne abgebrochene Starts) und Kapazität (= Zahl der Schützenstände).
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
    # Nur mit `names=full` (Personal am Schießstand, Berechtigung nötig): voller Name und Verein,
    # unabhängig von der Anzeige-Einstellung. Sonst immer null.
    full_name: str | None = None
    full_club: str | None = None
    class_id: UUID
    class_short: str
    competition_id: UUID
    competition_name: str
    # Kennziffer der Disziplin aus dem Katalog („1001“); null bei eigenem Wettbewerb.
    competition_code: str | None = None
    range_id: UUID | None
    attempt: int
    status: StartStatus
    abort_reason: AbortReason | None
    # Bemerkung zum Abbruch (`note` bzw. `reason` beim Abbrechen), nur mit `names=full` und nur
    # bei abgebrochenen Starts; sonst immer null. Kann Namen oder Gründe enthalten, deshalb nie
    # in öffentlichen Sichten.
    abort_note: str | None = None
    queue_position: int | None
    lane: int | None
    # Steht gerade auf `lane` und belegt sie (aufgerufen oder erfasst, noch nicht freigegeben).
    on_lane: bool = False
    # Zeitpunkt des Aufrufs auf den Schützenstand; leer, solange der Start wartet.
    called_at: datetime | None
    heat_id: UUID | None
    heat_number: int | None
    heat_starts_at: datetime | None


class LaneProgressOut(BaseModel):
    """Erfassungsfortschritt eines Starts auf dem Schützenstand (aus dem aktuellen Ergebnis)."""

    # Abschnitt, in dem gerade geschossen wird: der erste unvollständige, sonst der letzte.
    section_id: str | None
    # Vollständig erfasste Serien dieses Abschnitts und seine Serienzahl.
    series_done: int
    series_total: int
    # Alle Rohwerte vollständig (bereit zum Abschließen).
    complete: bool
    # Welcher Abschnitt das ist (ab 1) und wie viele der Ablauf hat („Abschnitt 2 von 2“);
    # 0, solange es keine Abschnitte gibt.
    section_number: int = 0
    section_count: int = 0
    # Über alle Abschnitte: vollständig erfasste Serien und Serien insgesamt („5 von 8 Serien“).
    series_done_overall: int = 0
    series_total_overall: int = 0


class LaneOut(BaseModel):
    lane: int
    # Der Start auf diesem Schützenstand (aufgerufen oder erfasst, noch nicht freigegeben); null,
    # wenn frei.
    start: StationStartOut | None
    # Erfassungsfortschritt des Starts; null ohne Start oder solange nichts erfasst ist.
    progress: LaneProgressOut | None = None


class HeatReservationOut(BaseModel):
    """Nächster Durchgang des Schießstands mit wartenden Starts und den Schützenständen, die er
    braucht.

    Solange `active` ist, hält der Schießstand `lanes` für ihn frei: Aufrufe aus der Reihenfolge
    auf diese Schützenstände brauchen `confirm_heat_conflict: true`.
    """

    heat_id: UUID
    number: int
    starts_at: datetime
    ends_at: datetime
    # Gebuchte Schützenstände der wartenden Starts dieses Durchgangs.
    lanes: list[int]
    # Einstellung `heat_reserve_minutes` des Turniers; 0 = aus.
    reserve_minutes: int
    # Ab hier hält der Schießstand die Schützenstände frei (`starts_at` − `reserve_minutes`);
    # null bei 0.
    reserved_from: datetime | None
    # Hält die Schützenstände gerade frei.
    active: bool


class QueueOut(BaseModel):
    range_id: UUID
    lane_count: int
    # Wartende Starts der Reihenfolge, nach `queue_position`.
    waiting: list[StationStartOut]
    lanes: list[LaneOut]
    # Nächster Durchgang des Schießstands (Zeitplan), damit die Oberfläche vor dem Aufruf warnen
    # kann.
    upcoming_heat: HeatReservationOut | None = None


class SkippedStartOut(BaseModel):
    """Ein Start, der bei „Nächste aufrufen“ übersprungen wurde."""

    start_id: UUID
    entry_id: UUID
    start_number: int
    competition_id: UUID
    queue_position: int | None
    # on_lane: Die Person steht gerade auf einem Schützenstand (hier oder an einem anderen
    # Schießstand) oder hat in diesem Aufruf einen bekommen.
    reason: Literal["on_lane"]


class CallNextOut(BaseModel):
    # Die aufgerufenen Starts, in der Reihenfolge der Schützenstände.
    called: list[StartOut]
    # Übersprungene Starts; sie behalten ihren Platz in der Reihenfolge.
    skipped: list[SkippedStartOut]
    # Freie Schützenstände, die für den bald beginnenden Durchgang frei bleiben (ohne Bestätigung).
    held_lanes: list[int]
    # Der Durchgang, für den Schützenstände freigehalten werden (wie in der Reihenfolge-Ansicht).
    upcoming_heat: HeatReservationOut | None
    # Hinweis für die Oberfläche (übersprungen, freigehalten); null, wenn es nichts zu sagen gibt.
    message: str | None


class RangeNowOut(BaseModel):
    """„Am Schießstand“ und „als Nächstes“ für Anzeige und Erfassung."""

    range_id: UUID
    lane_count: int
    lanes: list[LaneOut]
    # Nächster Durchgang mit wartenden Starts (Zeitplan), mit seinen Starts.
    next_heat: HeatOut | None
    next_heat_starts: list[StationStartOut]
    # Die nächsten Wartenden der Reihenfolge (höchstens so viele wie Schützenstände).
    next_queue: list[StationStartOut]
    # Wie in `QueueOut`.
    upcoming_heat: HeatReservationOut | None = None
