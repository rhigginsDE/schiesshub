"""HTTP-Schnittstelle des Moduls `system`: Health, formelle Begriffe und Live-Ereignisse."""

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse

from app import __version__
from app.core import begriffe
from app.core.db import SessionDep
from app.core.events import Event, EventHubDep
from app.core.security import require_paired
from app.modules.system import service
from app.modules.system.schemas import HealthOut, TermsOut

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
    "/terms",
    summary="Formelle Begriffe je Verband",
    description=(
        "Wörter für formelle Ausgaben (Ausschreibung, Aushang, Start- und Ergebnisliste, "
        "Anzeige), z. B. `schuetzenstand` = „Schützenstand“, `ergebnisliste` = „Ergebnisliste“, "
        "`kennziffer` = „Kennziffer“ (BDS) bzw. „Kennzahl“ (DSB). `default` gilt ohne Verband "
        "(eigene Disziplin) und für Verbände ohne eigenen Satz; `federations` enthält je Verband "
        "(Schlüssel = `catalog_federation` in Kleinbuchstaben) den vollständigen Satz, Lücken "
        "schon mit `default` gefüllt. Die Bedienung der Stationen darf Alltagswörter behalten "
        "(„Gleichstand“, „aufgegeben“). Lesbar für jedes gekoppelte Gerät; die Wörter ändern "
        "sich nur mit einer neuen Version des Servers."
    ),
    dependencies=[Depends(require_paired())],
)
async def terms() -> TermsOut:
    return TermsOut(default=begriffe.standard(), federations=begriffe.verbaende())


@router.get(
    "/events/names",
    summary="Bekannte Ereignisnamen",
    description=(
        "Alle fachlichen Ereignisnamen, die der Server senden kann (von den Modulen angemeldet "
        "oder schon einmal gesendet), sortiert. `EventSource` hört nur auf genaue Namen; damit "
        "lassen sich Muster wie `start.*` auflösen."
    ),
)
async def event_names(hub: EventHubDep) -> list[str]:
    return hub.known_names()


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
