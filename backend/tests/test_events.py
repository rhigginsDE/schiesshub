"""Server-Sent Events: Verteiler, Datenstrom und das Ereignis nach dem Import."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

from app.core.config import Settings
from app.core.events import Event, EventHub
from app.main import create_app
from tests.conftest import REAL_CATALOG_DIR, running


def parse(chunk: str) -> tuple[str, dict]:
    """Zerlegt einen SSE-Block in Ereignisname und Daten."""
    assert chunk.endswith("\n\n")
    event_line, data_line = chunk.strip().split("\n")
    assert event_line.startswith("event: ")
    assert data_line.startswith("data: ")
    return event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: "))


def test_event_encoding() -> None:
    encoded = Event("katalog.importiert", {"verbaende": 1, "name": "Schützen"}).encode()

    assert encoded == 'event: katalog.importiert\ndata: {"verbaende":1,"name":"Schützen"}\n\n'


async def test_publish_reaches_every_subscriber() -> None:
    hub = EventHub()
    first, second = hub.subscribe(), hub.subscribe()

    hub.publish("test", {"n": 1})

    assert first.get_nowait() == Event("test", {"n": 1})
    assert second.get_nowait() == Event("test", {"n": 1})
    hub.unsubscribe(first)
    hub.unsubscribe(second)
    assert hub.subscriber_count == 0


async def test_slow_subscriber_loses_oldest_event() -> None:
    hub = EventHub(queue_size=2)
    queue = hub.subscribe()

    for n in range(3):
        hub.publish("test", {"n": n})

    assert [queue.get_nowait().data["n"] for _ in range(2)] == [1, 2]


async def test_stream_sends_initial_event_events_and_heartbeat() -> None:
    hub = EventHub()
    stream = hub.stream(heartbeat_seconds=0.05, initial=Event("verbunden", {"version": "x"}))

    assert parse(await anext(stream)) == ("verbunden", {"version": "x"})
    assert hub.subscriber_count == 1

    hub.publish("katalog.importiert", {"disziplinen": 3})
    assert parse(await anext(stream)) == ("katalog.importiert", {"disziplinen": 3})

    # Ohne Ereignis kommt nach der Wartezeit ein Heartbeat.
    name, data = parse(await asyncio.wait_for(anext(stream), timeout=2))
    assert name == "heartbeat"
    assert "zeit" in data

    await stream.aclose()
    assert hub.subscriber_count == 0


async def test_import_at_startup_publishes_event(
    clean_db: None, settings_for: Callable[[Path], Settings], real_catalog_counts: dict[str, int]
) -> None:
    app = create_app(settings_for(REAL_CATALOG_DIR))
    queue = app.state.events.subscribe()

    async with running(app):
        event = queue.get_nowait()

    assert event.name == "katalog.importiert"
    assert event.data["fehler"] == []
    assert event.data["disziplinen"] == real_catalog_counts["disziplinen"]
    assert event.data["importiert_am"] is not None
