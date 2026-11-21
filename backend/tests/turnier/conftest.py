"""Fixtures für die Tests des Moduls `turnier`."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

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

    def drain(self) -> list[Event]:
        received = []
        while not self.events.empty():
            received.append(self.events.get_nowait())
        return received

    async def create_tournament(self, **fields: Any) -> dict[str, Any]:
        body = {"name": "Vereinspokal", "date_from": "2027-03-06", **fields}
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
