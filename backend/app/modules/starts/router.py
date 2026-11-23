"""HTTP-Schnittstelle des Moduls `starts`: Anmeldung, Starts, Ablauf am Schießstand,
Sichten."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import AwareDatetime

from app.core.db import SessionDep
from app.core.events import EventHubDep
from app.core.security import Actor, require
from app.modules.starts import queue, schedule, service, views
from app.modules.starts.schemas import (
    AbortRequest,
    CallConflictOut,
    CallNextOut,
    CallNextRequest,
    CallRequest,
    ConflictOut,
    EntryCreate,
    EntryOut,
    EntryUpdate,
    HeatCreate,
    HeatOut,
    HeatSeries,
    HeatUpdate,
    MoveRequest,
    NextSlotOut,
    QueueOut,
    RangeNowOut,
    ReturnRequest,
    SlotRequest,
    StartBooking,
    StartOut,
    StationStartOut,
)
from app.modules.teilnehmer.router import IndexDep

PERMISSION_ENTRY_READ = "entry.read"
PERMISSION_ENTRY_EDIT = "entry.edit"
PERMISSION_START_READ = "start.read"
PERMISSION_START_EDIT = "start.edit"
PERMISSION_START_CALL = "start.call"
PERMISSION_START_ABORT = "start.abort"

EntryReader = Annotated[Actor, Depends(require(PERMISSION_ENTRY_READ))]
EntryEditor = Annotated[Actor, Depends(require(PERMISSION_ENTRY_EDIT))]
StartReader = Annotated[Actor, Depends(require(PERMISSION_START_READ))]
StartEditor = Annotated[Actor, Depends(require(PERMISSION_START_EDIT))]
Caller = Annotated[Actor, Depends(require(PERMISSION_START_CALL))]
Aborter = Annotated[Actor, Depends(require(PERMISSION_START_ABORT))]

# Volle Namen in den Sichten der Station Stand (`names=full`): nur für das Personal am Schießstand.
FULL_NAME_PERMISSIONS = (PERMISSION_START_CALL, "result.capture", PERMISSION_ENTRY_READ)
FULL_NAMES_DENIED = (
    "Volle Namen sieht nur das Personal am Schießstand (Berechtigung „start.call“, "
    "„result.capture“ oder „entry.read“). Ohne sie steht jede Person so da, wie sie es gewählt hat "
    "(names=public)."
)
Names = Annotated[
    Literal["public", "full"],
    Query(
        description=(
            "`public` (Standard): nur nach Anzeige-Einstellung. `full`: zusätzlich `full_name`, "
            "`full_club` und bei abgebrochenen Starts die Bemerkung zum Abbruch (`abort_note`) "
            "(Berechtigung start.call, result.capture oder entry.read)."
        )
    ),
]


async def _full_names(request: Request, names: str) -> bool:
    """True bei `names=full` mit Berechtigung; ohne Berechtigung 403 mit Erklärung."""
    if names != "full":
        return False
    for permission in FULL_NAME_PERMISSIONS:
        try:
            await require(permission)(request)
        except HTTPException:
            continue
        return True
    raise HTTPException(status.HTTP_403_FORBIDDEN, FULL_NAMES_DENIED)


# 409 mit Feldbezug (`errors`) beantwortet der gemeinsame Handler aus `app.core.errors`.
router = APIRouter(prefix="/tournaments/{tournament_id}", tags=["starts"])

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Nicht gefunden"}}
CONFLICT = {
    status.HTTP_409_CONFLICT: {
        "description": (
            "Im aktuellen Zustand nicht möglich. Betrifft es ein Eingabefeld (z. B. Startnummer "
            "schon vergeben), nennt `errors` das Feld."
        ),
        "model": ConflictOut,
    }
}
WRITE = {**NOT_FOUND, **CONFLICT}
CALL_CONFLICT = {
    status.HTTP_409_CONFLICT: {
        "description": (
            "Im aktuellen Zustand nicht möglich (`detail`, bei Feldbezug `errors`). Mit "
            "`code: heat_imminent`: Der Aufruf aus der Reihenfolge würde einen Schützenstand "
            "belegen, den ein bald beginnender Durchgang braucht (Uhrzeit und Schützenstände im "
            "Text); nach Rückfrage mit `confirm_heat_conflict: true` wiederholen."
        ),
        "model": CallConflictOut,
    }
}
CALL_WRITE = {**NOT_FOUND, **CALL_CONFLICT}

ENTRIES = "/entries"
ENTRY = "/entries/{entry_id}"
START = "/starts/{start_id}"
RANGE = "/ranges/{range_id}"
HEATS = "/ranges/{range_id}/heats"
HEAT = "/ranges/{range_id}/heats/{heat_id}"


def _start(item: object) -> StartOut:
    return StartOut.model_validate(item)


# --- Anmeldung ---------------------------------------------------------------


@router.get(
    ENTRIES,
    summary="Anmeldungen",
    description=(
        "Nach Startnummer sortiert. Mit `q`: Treffer der Startnummer (genau) zuerst, dann "
        "Treffer in Name, Mitgliedsnummer oder Verein."
    ),
    responses=NOT_FOUND,
)
async def list_entries(
    tournament_id: UUID,
    session: SessionDep,
    index: IndexDep,
    _: EntryReader,
    q: Annotated[str | None, Query(max_length=200)] = None,
    class_id: UUID | None = None,
) -> list[EntryOut]:
    return await service.list_entries(session, index, tournament_id, q, class_id)


@router.post(
    ENTRIES,
    summary="Person anmelden",
    description=(
        "Ohne `start_number` vergibt der Server die nächste freie Nummer ab "
        "`settings.first_start_number` des Turniers."
    ),
    status_code=status.HTTP_201_CREATED,
    responses=WRITE,
)
async def create_entry(
    tournament_id: UUID,
    data: EntryCreate,
    session: SessionDep,
    events: EventHubDep,
    actor: EntryEditor,
) -> EntryOut:
    return await service.create_entry(session, events, actor, tournament_id, data)


@router.get(ENTRY, summary="Anmeldung mit Starts und Summe", responses=NOT_FOUND)
async def get_entry(
    tournament_id: UUID, entry_id: UUID, session: SessionDep, _: EntryReader
) -> EntryOut:
    return await service.get_entry_out(session, tournament_id, entry_id)


@router.patch(ENTRY, summary="Anmeldung ändern (Klasse, Startnummer)", responses=WRITE)
async def update_entry(
    tournament_id: UUID,
    entry_id: UUID,
    data: EntryUpdate,
    session: SessionDep,
    events: EventHubDep,
    actor: EntryEditor,
) -> EntryOut:
    return await service.update_entry(session, events, actor, tournament_id, entry_id, data)


@router.delete(
    ENTRY,
    summary="Anmeldung löschen",
    description=(
        "Nur solange kein Start geschossen wurde, gerade aufgerufen ist oder Einträge im "
        "Ergebnisprotokoll hat (auch ein Abbruch „nicht angetreten“)."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    responses=WRITE,
)
async def delete_entry(
    tournament_id: UUID,
    entry_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    actor: EntryEditor,
) -> Response:
    await service.delete_entry(session, events, actor, tournament_id, entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Starts ------------------------------------------------------------------


@router.post(
    f"{ENTRY}/starts",
    summary="Starts buchen",
    description=(
        "Bucht `count` Starts im Wettbewerb. Der Betrag (`fee_first_cents` für den ersten Start "
        "der Person im Wettbewerb, sonst `fee_repeat_cents`) wird am Start festgeschrieben. Bei "
        "Zeitplan optional gleich mit `heat_id` (und `lane`)."
    ),
    status_code=status.HTTP_201_CREATED,
    responses=WRITE,
)
async def book_starts(
    tournament_id: UUID,
    entry_id: UUID,
    data: StartBooking,
    session: SessionDep,
    events: EventHubDep,
    actor: StartEditor,
) -> list[StartOut]:
    starts = await service.book_starts(session, events, actor, tournament_id, entry_id, data)
    return [_start(start) for start in starts]


@router.delete(
    START,
    summary="Start stornieren (nur angemeldet)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=WRITE,
)
async def cancel_start(
    tournament_id: UUID,
    start_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    actor: StartEditor,
) -> Response:
    await service.cancel_start(session, events, actor, tournament_id, start_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    f"{START}/abort",
    summary="Start abbrechen (dns, dnf, dsq)",
    description=(
        "Wechselt den Status zu „abgebrochen“ (Berechtigung `start.abort`). Ist das Modul "
        "`ergebnisse` aktiv, steht der Abbruch wie bei `POST …/starts/{start_id}/result/abort` "
        "auch im Ergebnisprotokoll (Ereignis `aborted`). Die optionale Bemerkung `note` "
        "(bis 500 Zeichen) steht dort als Grund (`reason`) und im System-Protokoll."
    ),
    responses=WRITE,
)
async def abort_start(
    tournament_id: UUID,
    start_id: UUID,
    data: AbortRequest,
    session: SessionDep,
    events: EventHubDep,
    actor: Aborter,
) -> StartOut:
    return _start(
        await service.abort_start(
            session, events, actor, tournament_id, start_id, data.abort_reason, data.note
        )
    )


# --- Reihenfolge -------------------------------------------------------------


@router.get(
    f"{RANGE}/queue",
    summary="Reihenfolge eines Schießstands",
    description=(
        "Wartende Starts in ihrer Reihenfolge und alle Schützenstände. Belegt ist ein "
        "Schützenstand, solange ein Start darauf steht (aufgerufen oder erfasst, noch nicht "
        "freigegeben), mit Status und Erfassungsfortschritt (`progress`)."
    ),
    responses=NOT_FOUND,
)
async def get_queue(
    tournament_id: UUID,
    range_id: UUID,
    request: Request,
    session: SessionDep,
    _: StartReader,
    names: Names = "public",
) -> QueueOut:
    full = await _full_names(request, names)
    return await views.queue_view(session, tournament_id, range_id, full_names=full)


@router.post(
    f"{START}/move",
    summary="Start in der Reihenfolge verschieben",
    responses=WRITE,
)
async def move_start(
    tournament_id: UUID,
    start_id: UUID,
    data: MoveRequest,
    session: SessionDep,
    events: EventHubDep,
    actor: Caller,
) -> QueueOut:
    range_id = await queue.move(session, events, tournament_id, start_id, data, actor)
    return await views.queue_view(session, tournament_id, range_id)


@router.post(
    f"{START}/call",
    summary="Start aufrufen",
    description=(
        "Reihenfolge: auf `lane` oder den ersten freien Schützenstand. Zeitplan: auf den "
        "Schützenstand des Durchgangs. Ein Schützenstand trägt nur einen Start (aufgerufen oder "
        "erfasst, bis er frei wird), eine Person steht nur auf einem Schützenstand. Aus der "
        "Reihenfolge nicht ohne `confirm_heat_conflict` auf einen Schützenstand, den ein "
        "Durchgang innerhalb von `settings.heat_reserve_minutes` braucht (409 "
        "`heat_imminent`); ohne `lane` wird dann zuerst einer genommen, den keiner braucht."
    ),
    responses=CALL_WRITE,
)
async def call_start(
    tournament_id: UUID,
    start_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    actor: Caller,
    data: CallRequest | None = None,
) -> StartOut:
    data = data or CallRequest()
    return _start(
        await queue.call(
            session,
            events,
            actor,
            tournament_id,
            start_id,
            data.lane,
            confirm_heat_conflict=data.confirm_heat_conflict,
        )
    )


@router.post(
    f"{START}/return",
    summary="Aufgerufenen Start zurückstellen",
    description=(
        "Der Schützenstand wird frei. Bei der Reihenfolge kommt der Start vorn (`front`) oder "
        "hinten (`back`) wieder in die Warteschlange; im Zeitplan behält er seinen Platz."
    ),
    responses=WRITE,
)
async def return_start(
    tournament_id: UUID,
    start_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    actor: Caller,
    data: ReturnRequest | None = None,
) -> StartOut:
    position = (data or ReturnRequest()).position
    return _start(
        await queue.return_start(session, events, actor, tournament_id, start_id, position)
    )


@router.post(
    f"{START}/release-lane",
    summary="Schützenstand freigeben",
    description=(
        "Nimmt einen erfassten Start von seinem Schützenstand, ohne den Status zu ändern (z. B. "
        "Schütze fertig, Ergebnis noch nicht abgeschlossen). Mit dem Abschließen oder Abbrechen "
        "wird der Schützenstand ohnehin frei. Ein nur aufgerufener Start wird zurückgestellt, "
        "nicht freigegeben."
    ),
    responses=WRITE,
)
async def release_lane(
    tournament_id: UUID,
    start_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    actor: Caller,
) -> StartOut:
    return _start(await queue.release_lane(session, events, actor, tournament_id, start_id))


@router.post(
    f"{RANGE}/call-next",
    summary="Nächste aufrufen",
    description=(
        "Füllt alle freien Schützenstände des Schießstands (mit `lane` nur diesen: „Nächsten "
        "auf Schützenstand N“) der Reihe nach aus der Reihenfolge. Belegt bleibt ein "
        "Schützenstand auch mit einem erfassten Start, bis er abgeschlossen, abgebrochen oder "
        "der Schützenstand freigegeben ist. Wer gerade auf einem Schützenstand steht (auch an "
        "einem anderen Schießstand), wird übersprungen (`skipped`) und behält seinen Platz. "
        "Schützenstände, die ein Durchgang innerhalb von "
        "`settings.heat_reserve_minutes` braucht, bleiben ohne `confirm_heat_conflict` frei "
        "(`held_lanes`); wäre nur auf ihnen jemand drangekommen, kommt 409 `heat_imminent`."
    ),
    responses=CALL_WRITE,
)
async def call_next(
    tournament_id: UUID,
    range_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    actor: Caller,
    data: CallNextRequest | None = None,
) -> CallNextOut:
    data = data or CallNextRequest()
    result = await queue.call_next(
        session,
        events,
        actor,
        tournament_id,
        range_id,
        data.lane,
        confirm_heat_conflict=data.confirm_heat_conflict,
    )
    return CallNextOut(
        called=[_start(start) for start in result.called],
        skipped=result.skipped,
        held_lanes=result.held_lanes,
        upcoming_heat=result.upcoming_heat,
        message=result.message,
    )


# --- Zeitplan ----------------------------------------------------------------


@router.get(HEATS, summary="Durchgänge eines Schießstands", responses=NOT_FOUND)
async def list_heats(
    tournament_id: UUID, range_id: UUID, session: SessionDep, _: StartReader
) -> list[HeatOut]:
    return await schedule.list_heats(session, tournament_id, range_id)


@router.post(
    HEATS, summary="Durchgang anlegen", status_code=status.HTTP_201_CREATED, responses=WRITE
)
async def create_heat(
    tournament_id: UUID,
    range_id: UUID,
    data: HeatCreate,
    session: SessionDep,
    events: EventHubDep,
    actor: StartEditor,
) -> HeatOut:
    return await schedule.create_heat(session, events, tournament_id, range_id, data, actor)


@router.post(
    f"{HEATS}/series",
    summary="Durchgänge als Serie anlegen",
    description=(
        "`count` Durchgänge ab `starts_at`, lückenlos hintereinander, je `heat_minutes` des "
        "Wettbewerbs lang (die Wechselzeit ist darin enthalten)."
    ),
    status_code=status.HTTP_201_CREATED,
    responses=WRITE,
)
async def create_series(
    tournament_id: UUID,
    range_id: UUID,
    data: HeatSeries,
    session: SessionDep,
    events: EventHubDep,
    actor: StartEditor,
) -> list[HeatOut]:
    return await schedule.create_series(session, events, tournament_id, range_id, data, actor)


@router.patch(HEAT, summary="Durchgang ändern", responses=WRITE)
async def update_heat(
    tournament_id: UUID,
    range_id: UUID,
    heat_id: UUID,
    data: HeatUpdate,
    session: SessionDep,
    events: EventHubDep,
    actor: StartEditor,
) -> HeatOut:
    return await schedule.update_heat(
        session, events, tournament_id, range_id, heat_id, data, actor
    )


@router.delete(
    HEAT,
    summary="Durchgang löschen (nur ohne Starts)",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=WRITE,
)
async def delete_heat(
    tournament_id: UUID,
    range_id: UUID,
    heat_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    actor: StartEditor,
) -> Response:
    await schedule.delete_heat(session, events, actor, tournament_id, range_id, heat_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    f"{HEAT}/call",
    summary="Durchgang aufrufen",
    description=(
        "Ruft alle wartenden Starts des Durchgangs auf ihre Schützenstände – alle oder keinen."
    ),
    responses=WRITE,
)
async def call_heat(
    tournament_id: UUID,
    range_id: UUID,
    heat_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    actor: Caller,
) -> list[StartOut]:
    starts = await schedule.call_heat(session, events, actor, tournament_id, range_id, heat_id)
    return [_start(start) for start in starts]


@router.put(
    f"{START}/slot",
    summary="Start einem Durchgang und einem Schützenstand zuweisen",
    responses=WRITE,
)
async def assign_slot(
    tournament_id: UUID,
    start_id: UUID,
    data: SlotRequest,
    session: SessionDep,
    events: EventHubDep,
    actor: StartEditor,
) -> StartOut:
    return _start(
        await schedule.assign_slot(
            session, events, tournament_id, start_id, data.heat_id, data.lane, actor
        )
    )


@router.delete(f"{START}/slot", summary="Start aus dem Durchgang nehmen", responses=WRITE)
async def clear_slot(
    tournament_id: UUID,
    start_id: UUID,
    session: SessionDep,
    events: EventHubDep,
    actor: StartEditor,
) -> StartOut:
    return _start(await schedule.clear_slot(session, events, tournament_id, start_id, actor))


@router.get(
    "/competitions/{competition_id}/next-slot",
    summary="Nächster freier Platz (Vorschlag)",
    description=(
        "Frühester Durchgang ab `after` (Standard: jetzt) mit freiem Schützenstand auf dem "
        "Schießstand des Wettbewerbs. Mit `entry_id` ohne Überschneidung mit den übrigen "
        "Durchgängen der Person. "
        "`null`, wenn es keinen freien Platz gibt."
    ),
    responses=WRITE,
)
async def next_slot(
    tournament_id: UUID,
    competition_id: UUID,
    session: SessionDep,
    _: StartReader,
    entry_id: UUID | None = None,
    after: AwareDatetime | None = None,
) -> NextSlotOut | None:
    found = await schedule.next_slot(
        session, tournament_id, competition_id, entry_id, after or datetime.now(UTC)
    )
    if found is None:
        return None
    heat, lane = found
    return NextSlotOut(heat=heat, lane=lane)


# --- Sichten -----------------------------------------------------------------


@router.get(
    "/startlist",
    summary="Startliste",
    description=(
        "Alle Starts, wahlweise eines Wettbewerbs oder Schießstands. Namen nur nach der "
        "Anzeige-Einstellung der Person, der Verein nur mit `show_club`."
    ),
    responses=NOT_FOUND,
)
async def get_startlist(
    tournament_id: UUID,
    request: Request,
    session: SessionDep,
    _: StartReader,
    competition_id: UUID | None = None,
    range_id: UUID | None = None,
    names: Names = "public",
) -> list[StationStartOut]:
    full = await _full_names(request, names)
    return await views.startlist(session, tournament_id, competition_id, range_id, full_names=full)


@router.get(
    f"{RANGE}/now",
    summary="Am Schießstand und als Nächstes",
    description=(
        "Belegte Schützenstände (aufgerufen oder erfasst, mit Status und Erfassungsfortschritt "
        "`progress`), der nächste Durchgang mit seinen Starts und die nächsten Wartenden der "
        "Reihenfolge. Namen nur nach der Anzeige-Einstellung der Person."
    ),
    responses=NOT_FOUND,
)
async def get_range_now(
    tournament_id: UUID,
    range_id: UUID,
    request: Request,
    session: SessionDep,
    _: StartReader,
    names: Names = "public",
) -> RangeNowOut:
    full = await _full_names(request, names)
    return await views.range_now(session, tournament_id, range_id, full_names=full)
