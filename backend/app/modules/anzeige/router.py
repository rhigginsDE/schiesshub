"""HTTP-Schnittstelle des Moduls `anzeige`.

Verwaltung braucht `display.control`, das Lesen von Feed und eigener Anzeige `display.read`.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.db import SessionDep
from app.core.events import EventHubDep
from app.core.security import Actor, require
from app.modules.anzeige import service
from app.modules.anzeige.feed import BackupInfo, build_feed
from app.modules.anzeige.models import Display
from app.modules.anzeige.schemas import (
    DeviceAssign,
    DisplayConfig,
    DisplayCreate,
    DisplayOut,
    DisplayUpdate,
    FeedOut,
    FeedPreviewRequest,
    SceneOrder,
)

PERMISSION_READ = "display.read"
PERMISSION_CONTROL = "display.control"

Reader = Annotated[Actor, Depends(require(PERMISSION_READ))]
Controller = Annotated[Actor, Depends(require(PERMISSION_CONTROL))]

router = APIRouter(prefix="/displays", tags=["anzeige"])

NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Nicht gefunden"}}
CONFLICT = {status.HTTP_409_CONFLICT: {"description": "Im aktuellen Zustand nicht möglich"}}
WRITE = {**NOT_FOUND, **CONFLICT}
FEED = {
    **NOT_FOUND,
    status.HTTP_304_NOT_MODIFIED: {"description": "Unverändert (If-None-Match passt zum ETag)"},
}
DISPLAY = "/{display_id}"


def _out(display: Display) -> DisplayOut:
    return DisplayOut.model_validate(display)


def _backup_info(request: Request) -> BackupInfo:
    backup = getattr(request.app.state, "backup", None)
    if backup is None:
        return BackupInfo()
    warning = backup.status().warning
    return BackupInfo(
        warning_code=warning.code if warning is not None else None,
        warning_message=warning.message_de if warning is not None else None,
        warn_on_display=backup.config.warn_on_display,
    )


def _matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    for candidate in if_none_match.split(","):
        candidate = candidate.strip()
        if candidate == "*":
            return True
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == etag:
            return True
    return False


async def _feed_response(
    request: Request, response: Response, session: SessionDep, display: Display
) -> FeedOut | Response:
    feed = await build_feed(
        session, display, _backup_info(request), request.app.state.events.known_names()
    )
    etag = f'"{feed.version}"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if _matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    response.headers.update(headers)
    return feed


FEED_DESCRIPTION = (
    "Alles, was der Bildschirm zum Zeichnen braucht: Kopf, die aufgelösten Szenen in "
    "Reihenfolge (eine Szene kann mehrere Seiten ergeben, `part`/`parts`), übersprungene Szenen "
    "mit Grund, Laufzeile und Warnungen. Ist nichts zu zeigen, kommt eine Ruhe-Szene (`idle`). "
    "`version` steht auch im ETag; mit `If-None-Match` antwortet der Server 304, solange sich "
    "der Inhalt nicht ändert. Neu laden bei den Ereignissen aus `reload_on` (genaue Namen, "
    "direkt für `EventSource.addEventListener`) und spätestens nach `poll_seconds`. Uhrzeiten "
    "zusätzlich in Ortszeit des Turniers (`*_local`, Zone in `header.timezone`)."
)


# --- Eigene Anzeige (Gerät) -----------------------------------------------------


@router.get(
    "/mine",
    summary="Anzeige dieses Geräts",
    description="Die Anzeige, der das aufrufende Gerät zugewiesen ist.",
    responses=NOT_FOUND,
)
async def get_mine(session: SessionDep, actor: Reader) -> DisplayOut:
    return _out(await service.display_of_device(session, actor.device_id))


@router.get(
    "/mine/feed",
    summary="Feed der Anzeige dieses Geräts",
    description=FEED_DESCRIPTION,
    responses=FEED,
)
async def get_mine_feed(
    request: Request, response: Response, session: SessionDep, actor: Reader
) -> FeedOut:
    display = await service.display_of_device(session, actor.device_id)
    return await _feed_response(request, response, session, display)  # type: ignore[return-value]


# --- Verwaltung ----------------------------------------------------------------


@router.get("", summary="Alle Anzeigen")
async def list_displays(session: SessionDep, _: Controller) -> list[DisplayOut]:
    return [_out(display) for display in await service.list_displays(session)]


@router.post(
    "",
    summary="Anzeige anlegen",
    description="Ohne `config` mit den Standardszenen (Live-Wertung und Startliste).",
    status_code=status.HTTP_201_CREATED,
    responses=WRITE,
)
async def create_display(
    data: DisplayCreate, session: SessionDep, events: EventHubDep, actor: Controller
) -> DisplayOut:
    return _out(await service.create_display(session, events, actor, data))


@router.post(
    "/defaults",
    summary="Standard-Anzeige anlegen",
    description="Legt die „Hauptanzeige“ an, solange es keine Anzeige gibt (sonst 409).",
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
)
async def create_defaults(
    session: SessionDep, events: EventHubDep, actor: Controller
) -> DisplayOut:
    return _out(await service.create_defaults(session, events, actor))


@router.get(DISPLAY, summary="Anzeige", responses=NOT_FOUND)
async def get_display(display_id: UUID, session: SessionDep, _: Controller) -> DisplayOut:
    return _out(await service.get_display(session, display_id))


@router.patch(
    DISPLAY,
    summary="Anzeige ändern (Name, Turnier, Reihenfolge, Inhalt)",
    description=(
        "`tournament_id: null` heißt: automatisch das aktive Turnier. Mit `config` werden "
        "Szenen und Einstellungen im selben Schritt ersetzt (wie `PUT …/config`); die Szenen "
        "werden gegen das neue Turnier geprüft, Fehler nennen `config.scenes[…]`."
    ),
    responses=WRITE,
)
async def update_display(
    display_id: UUID,
    data: DisplayUpdate,
    session: SessionDep,
    events: EventHubDep,
    actor: Controller,
) -> DisplayOut:
    return _out(await service.update_display(session, events, actor, display_id, data))


@router.delete(DISPLAY, summary="Anzeige löschen", status_code=204, responses=NOT_FOUND)
async def delete_display(
    display_id: UUID, session: SessionDep, events: EventHubDep, actor: Controller
) -> Response:
    await service.delete_display(session, events, actor, display_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    f"{DISPLAY}/config",
    summary="Inhalt der Anzeige setzen",
    description="Ersetzt Szenen und Einstellungen vollständig.",
    responses=WRITE,
)
async def put_config(
    display_id: UUID,
    config: DisplayConfig,
    session: SessionDep,
    events: EventHubDep,
    actor: Controller,
) -> DisplayOut:
    return _out(await service.put_config(session, events, actor, display_id, config))


@router.post(
    f"{DISPLAY}/scenes/reorder",
    summary="Szenen neu ordnen",
    description="`ids`: alle Szenen-IDs der Anzeige in der neuen Reihenfolge.",
    responses=WRITE,
)
async def reorder_scenes(
    display_id: UUID,
    data: SceneOrder,
    session: SessionDep,
    events: EventHubDep,
    actor: Controller,
) -> DisplayOut:
    return _out(await service.reorder_scenes(session, events, actor, display_id, data.ids))


@router.put(
    f"{DISPLAY}/device",
    summary="Gerät zuweisen",
    description="Das Gerät zeigt danach diese Anzeige (`GET /displays/mine`).",
    responses=WRITE,
)
async def assign_device(
    display_id: UUID,
    data: DeviceAssign,
    session: SessionDep,
    events: EventHubDep,
    actor: Controller,
) -> DisplayOut:
    return _out(await service.assign_device(session, events, actor, display_id, data.device_id))


@router.delete(f"{DISPLAY}/device", summary="Gerät lösen", responses=NOT_FOUND)
async def release_device(
    display_id: UUID, session: SessionDep, events: EventHubDep, actor: Controller
) -> DisplayOut:
    return _out(await service.release_device(session, events, actor, display_id))


@router.get(
    f"{DISPLAY}/feed", summary="Feed einer Anzeige", description=FEED_DESCRIPTION, responses=FEED
)
async def get_feed(
    display_id: UUID, request: Request, response: Response, session: SessionDep, _: Reader
) -> FeedOut:
    display = await service.get_display(session, display_id)
    return await _feed_response(request, response, session, display)  # type: ignore[return-value]


@router.post(
    f"{DISPLAY}/preview-feed",
    summary="Feed-Vorschau für eine ungespeicherte Konfiguration",
    description=(
        "Baut den Feed der Anzeige mit `config` (und wahlweise `tournament_id`) statt der "
        "gespeicherten Werte, ohne etwas zu speichern. Die Szenen werden wie beim Speichern "
        "geprüft (422 mit `config.scenes[…]`). Kein ETag."
    ),
    responses=WRITE,
)
async def preview_feed(
    display_id: UUID,
    data: FeedPreviewRequest,
    request: Request,
    session: SessionDep,
    _: Controller,
) -> FeedOut:
    display = await service.get_display(session, display_id)
    tournament_id = (
        data.tournament_id if "tournament_id" in data.model_fields_set else display.tournament_id
    )
    await service.check_config(session, tournament_id, data.config)
    return await build_feed(
        session,
        display,
        _backup_info(request),
        request.app.state.events.known_names(),
        config=data.config,
        tournament_id=tournament_id,
    )
