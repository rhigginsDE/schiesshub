"""Einfacher Verteiler für Server-Sent Events, der seine Abonnenten im Speicher hält.

Ereignisse sind nur Hinweise („lade die betroffenen Daten neu“). Geht eines verloren, weil ein
Client zu langsam liest, ist das unkritisch. Der Verteiler gilt je Prozess; das Backend läuft
deshalb mit einem einzelnen Worker.

Bekannte Ereignisnamen: Browser können nur auf genaue Namen hören (`EventSource` kennt keine
Muster wie `start.*`). Deshalb führt der Verteiler eine Liste der Namen, die vorkommen können:
Module melden ihre Namen beim Laden mit `register_event_names` an, und jedes `publish` merkt sich
seinen Namen zusätzlich. `known_names()` liefert die Liste, `GET /events/names` zeigt sie,
`match_names` löst Muster (`*` am Ende) gegen sie auf.
"""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Request

HEARTBEAT_EVENT = "heartbeat"
CONNECTED_EVENT = "verbunden"

# Von Modulen angemeldete Namen, über alle Verteiler eines Prozesses (Anmeldung beim Laden).
_registered_names: set[str] = set()


def register_event_names(*names: str) -> None:
    """Meldet Ereignisnamen an, die ein Modul veröffentlichen kann (genaue Namen, keine Muster)."""
    for name in names:
        if not name or name.endswith("*"):
            raise ValueError(f"Ungültiger Ereignisname: {name!r}")
        _registered_names.add(name)


def registered_event_names() -> frozenset[str]:
    return frozenset(_registered_names)


def match_names(patterns: Iterable[str], names: Iterable[str]) -> list[str]:
    """Löst Muster gegen bekannte Namen auf, sortiert und ohne doppelte.

    `start.*` passt auf alle Namen, die mit `start.` beginnen; ein Muster ohne `*` ist ein
    genauer Name und bleibt immer stehen, auch wenn er (noch) nicht bekannt ist.
    """
    known = set(names)
    result: set[str] = set()
    for pattern in patterns:
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            result |= {name for name in known if name.startswith(prefix)}
        else:
            result.add(pattern)
    return sorted(result)


@dataclass(frozen=True, slots=True)
class Event:
    name: str
    data: dict[str, Any] = field(default_factory=dict)

    def encode(self) -> str:
        """Darstellung im SSE-Textformat."""
        payload = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"))
        return f"event: {self.name}\ndata: {payload}\n\n"


class EventHub:
    def __init__(self, queue_size: int = 100) -> None:
        self._queue_size = queue_size
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._published: set[str] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(queue)

    def known_names(self) -> list[str]:
        """Angemeldete und schon veröffentlichte Ereignisnamen, sortiert."""
        return sorted(_registered_names | self._published)

    def publish(self, name: str, data: dict[str, Any] | None = None) -> None:
        """Verteilt ein Ereignis an alle Abonnenten, ohne zu blockieren."""
        self._published.add(name)
        event = Event(name, data or {})
        for queue in self._subscribers:
            if queue.full():
                # Langsamer Client: das älteste Ereignis verwerfen.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    async def stream(
        self, heartbeat_seconds: float, initial: Event | None = None
    ) -> AsyncIterator[str]:
        """Liefert Ereignisse im SSE-Format; nach `heartbeat_seconds` Ruhe einen Heartbeat."""
        queue = self.subscribe()
        try:
            if initial is not None:
                yield initial.encode()
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
                except TimeoutError:
                    event = Event(HEARTBEAT_EVENT, {"zeit": datetime.now(UTC).isoformat()})
                yield event.encode()
        finally:
            self.unsubscribe(queue)


def get_event_hub(request: Request) -> EventHub:
    return request.app.state.events


EventHubDep = Annotated[EventHub, Depends(get_event_hub)]
