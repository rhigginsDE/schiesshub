"""Wartungszustand während einer Wiederherstellung.

Solange er gilt, weist der Server schreibende Anfragen an die API (alles außer GET, HEAD,
OPTIONS) mit HTTP 503 ab:

    {"detail": "Die Sicherung wird gerade wiederhergestellt. …", "code": "maintenance"}

Während des eigentlichen Tauschs der Datenbank (`exclusive`, wenige Sekunden) gilt das auch für
lesende Anfragen; nur der Ereignis-Strom (`/events`) bleibt offen. Beginn und Ende meldet das
Ereignis `backup.maintenance` (`{"active": …, "message_de": …, "since": …}`) an alle Geräte.

Eingebaut wird die Sperre als äußerste ASGI-Schicht (`install`). Vor ihr liegt keine
CORS-Schicht; die 503-Antwort trägt deshalb selbst die CORS-Kopfzeilen für erlaubte Herkünfte.
Die Sperre zählt außerdem die laufenden schreibenden Anfragen, damit die Wiederherstellung
abwarten kann, bis begonnene Eingaben fertig sind (`drained`).
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import API_PREFIX
from app.core.events import EventHub

EVENT_MAINTENANCE = "backup.maintenance"
# Fortschritt einer Wiederherstellung (`guided`): nur Zustand, Schritt und Anteil.
EVENT_RESTORE = "backup.restore"
CODE = "maintenance"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Bleibt auch während des Tauschs erreichbar: braucht keine Datenbank.
EXCLUSIVE_OPEN_PATHS = frozenset({f"{API_PREFIX}/events"})
RETRY_AFTER_S = 10

MESSAGE = (
    "Die Sicherung wird gerade wiederhergestellt. Eingaben sind für einige Minuten gesperrt; "
    "bitte danach erneut versuchen."
)
MESSAGE_EXCLUSIVE = (
    "Die Datenbank wird gerade getauscht. Der Server ist in wenigen Sekunden wieder erreichbar."
)


@dataclass(slots=True)
class MaintenanceState:
    events: EventHub
    cors_origins: frozenset[str] = frozenset()
    active: bool = False
    exclusive: bool = False
    since: datetime | None = None
    in_flight: int = 0
    in_flight_reads: int = 0
    _idle: asyncio.Event = field(default_factory=asyncio.Event)
    _idle_reads: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        self._idle.set()
        self._idle_reads.set()

    def snapshot(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "exclusive": self.exclusive,
            "message_de": (MESSAGE_EXCLUSIVE if self.exclusive else MESSAGE)
            if self.active
            else None,
            "since": self.since.isoformat() if self.since else None,
        }

    def _publish(self) -> None:
        self.events.publish(EVENT_MAINTENANCE, self.snapshot())

    def begin(self) -> None:
        if not self.active:
            self.active = True
            self.since = datetime.now(UTC)
            self._publish()

    def set_exclusive(self, exclusive: bool) -> None:
        if self.exclusive != exclusive:
            self.exclusive = exclusive
            self._publish()

    def end(self) -> None:
        if self.active:
            self.active = False
            self.exclusive = False
            self.since = None
            self._publish()

    async def drained(self, timeout_s: float, *, reads: bool = False) -> bool:
        """Wartet, bis keine schreibende (mit `reads`: keine) Anfrage mehr läuft.

        False bei Zeitüberschreitung. Der Ereignis-Strom zählt nie mit.
        """
        try:
            await asyncio.wait_for((self._idle_reads if reads else self._idle).wait(), timeout_s)
        except TimeoutError:
            return False
        return True

    def _enter(self, write: bool) -> None:
        if write:
            self.in_flight += 1
            self._idle.clear()
        else:
            self.in_flight_reads += 1
            self._idle_reads.clear()

    def _leave(self, write: bool) -> None:
        if write:
            self.in_flight = max(self.in_flight - 1, 0)
            if self.in_flight == 0:
                self._idle.set()
        else:
            self.in_flight_reads = max(self.in_flight_reads - 1, 0)
            if self.in_flight_reads == 0:
                self._idle_reads.set()

    def blocks(self, method: str, path: str) -> bool:
        if not self.active or not path.startswith(API_PREFIX):
            return False
        if self.exclusive:
            return path not in EXCLUSIVE_OPEN_PATHS
        return method not in SAFE_METHODS


class MaintenanceGate:
    """ASGI-Schicht: weist während der Wartung ab und zählt laufende schreibende Anfragen."""

    def __init__(self, app: ASGIApp, state: MaintenanceState) -> None:
        self.app = app
        self.state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope["method"]
        path = scope["path"]
        if self.state.blocks(method, path):
            await self._reject(scope, send)
            return
        if path in EXCLUSIVE_OPEN_PATHS or not path.startswith(API_PREFIX):
            await self.app(scope, receive, send)
            return
        write = method not in SAFE_METHODS
        self.state._enter(write)
        try:
            await self.app(scope, receive, send)
        finally:
            self.state._leave(write)

    async def _reject(self, scope: Scope, send: Send) -> None:
        message = MESSAGE_EXCLUSIVE if self.state.exclusive else MESSAGE
        body = json.dumps({"detail": message, "code": CODE}, ensure_ascii=False).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"retry-after", str(RETRY_AFTER_S).encode()),
        ]
        origin = dict(scope.get("headers") or []).get(b"origin")
        if origin is not None and origin.decode("latin-1") in self.state.cors_origins:
            headers += [
                (b"access-control-allow-origin", origin),
                (b"access-control-allow-credentials", b"true"),
                (b"vary", b"Origin"),
            ]
        await send({"type": "http.response.start", "status": 503, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def install(app: FastAPI, state: MaintenanceState) -> None:
    """Hängt die Sperre als äußerste Schicht vor die Anwendung.

    Die Anwendung baut ihre Schichten beim ersten ASGI-Aufruf (unter Uvicorn: beim Start, also
    vor den Modul-Starts). Ist das schon geschehen, wird der fertige Stapel umhüllt, sonst die
    Schicht regulär eingetragen.
    """
    if getattr(app.state, "maintenance_gate_installed", False):
        return
    if app.middleware_stack is None:
        app.add_middleware(MaintenanceGate, state=state)
    else:
        app.middleware_stack = MaintenanceGate(app.middleware_stack, state)
    app.state.maintenance_gate_installed = True
