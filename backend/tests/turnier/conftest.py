"""Fixtures für die Tests des Moduls `turnier`."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core import crypto
from app.core.config import Settings
from app.core.events import Event
from app.main import create_app
from tests.conftest import REAL_CATALOG_DIR, running

API = "/api/v1"


@dataclass
class Api:
    """HTTP-Client plus Mitschnitt der Ereignisse, die die Anwendung verteilt."""

    client: httpx.AsyncClient
    events: asyncio.Queue[Event]
    created: int = 0

    def drain(self) -> list[Event]:
        received = []
        while not self.events.empty():
            received.append(self.events.get_nowait())
        return received

    async def create_tournament(self, **fields: Any) -> dict[str, Any]:
        # Gleicher Name und Tag gilt als Doppel: ab dem zweiten Turnier ohne Namen hochzählen.
        self.created += 1
        name = "Vereinspokal" if self.created == 1 else f"Vereinspokal {self.created}"
        body = {"name": name, "date_from": "2027-03-06", **fields}
        response = await self.client.post(f"{API}/tournaments", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    async def create(self, tournament_id: str, kind: str, **fields: Any) -> dict[str, Any]:
        response = await self.client.post(f"{API}/tournaments/{tournament_id}/{kind}", json=fields)
        assert response.status_code == 201, response.text
        return response.json()


@pytest.fixture
async def api(clean_db: None, settings_for: Callable[[Path], Settings]) -> AsyncIterator[Api]:
    app = create_app(settings_for(REAL_CATALOG_DIR))
    async with running(app) as client:
        queue = app.state.events.subscribe()
        yield Api(client=client, events=queue)
        app.state.events.unsubscribe(queue)


@pytest.fixture
async def data_api(
    clean_db: None, settings_for: Callable[[Path], Settings], tmp_path: Path
) -> AsyncIterator[Api]:
    """Wie `api`, aber mit eigenem Datenverzeichnis (Schlüssel für Personen, Mitschrift)."""
    settings = settings_for(REAL_CATALOG_DIR).model_copy(update={"data_dir": tmp_path / "data"})
    app = create_app(settings)
    async with running(app) as client:
        queue = app.state.events.subscribe()
        yield Api(client=client, events=queue)
        app.state.events.unsubscribe(queue)
    crypto.set_field_cipher(None)
