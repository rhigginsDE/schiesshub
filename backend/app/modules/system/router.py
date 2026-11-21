"""HTTP-Schnittstelle des Moduls `system`: Health und Live-Ereignisse."""

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import StreamingResponse

from app import __version__
from app.core.db import SessionDep
from app.core.events import Event, EventHubDep
from app.modules.system import service
from app.modules.system.schemas import HealthOut

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    summary="Zustand des Servers",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthOut}},
)
async def health(session: SessionDep, response: Response) -> HealthOut:
    result = await service.get_health(session)
    if result.db != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get(
    "/events",
    summary="Live-Ereignisse (Server-Sent Events)",
    description=(
        "Dauerhafte Verbindung im Format `text/event-stream`. Ereignisse: `verbunden` (einmal "
        "nach dem Verbindungsaufbau), `heartbeat` (bei Ruhe, standardmäßig alle 15 s) und "
        "fachliche Ereignisse wie `katalog.importiert`. Clients laden bei einem fachlichen "
        "Ereignis die betroffenen Daten neu."
    ),
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def events(request: Request, hub: EventHubDep) -> StreamingResponse:
    heartbeat = request.app.state.settings.sse_heartbeat_seconds
    stream = hub.stream(heartbeat, initial=Event("verbunden", {"version": __version__}))
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
