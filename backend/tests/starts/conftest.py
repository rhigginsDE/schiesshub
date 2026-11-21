"""Fixtures für die Tests des Moduls `starts`: Anwendung, Ereignis-Mitschnitt, Aufbau-Hilfen."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core import crypto
from app.core.config import Settings
from app.core.events import Event
from app.main import create_app
from tests.conftest import running

API = "/api/v1"

# Eigener Ablauf ohne feste Zeiten: Die Planung ist dann die Reihenfolge.
OWN_DEFINITION: dict[str, Any] = {
    "variant": {
        "id": "fallscheibe",
        "name": "Fallscheibe",
        "abschnitte": [{"id": "lauf", "name": "Lauf", "serien": 3, "schuss_je_serie": 5}],
    },
    "scoring": {"modell": "ringe", "rangfolge": "absteigend", "geprueft": False},
}


@dataclass
class Api:
    """HTTP-Client, Anwendung und Mitschnitt der Ereignisse; dazu Hilfen zum Aufbauen."""

    client: httpx.AsyncClient
    app: FastAPI
    events: asyncio.Queue[Event]
    _counter: list[int] = field(default_factory=lambda: [0])

    def drain(self) -> list[Event]:
        received = []
        while not self.events.empty():
            received.append(self.events.get_nowait())
        return received

    async def ok(self, method: str, path: str, status: int = 200, **kwargs: Any) -> Any:
        response = await self.client.request(method, f"{API}{path}", **kwargs)
        assert response.status_code == status, response.text
        return response.json() if response.content else None

    async def fail(self, method: str, path: str, status: int, **kwargs: Any) -> str:
        response = await self.client.request(method, f"{API}{path}", **kwargs)
        assert response.status_code == status, response.text
        return response.json()["detail"]

    # --- Aufbau ---------------------------------------------------------------

    async def tournament(self, **settings: Any) -> str:
        body: dict[str, Any] = {"name": "Vereinspokal", "date_from": "2027-03-06"}
        if settings:
            body["settings"] = settings
        return (await self.ok("POST", "/tournaments", 201, json=body))["id"]

    async def range(self, tid: str, lanes: int = 4, name: str = "Stand 1") -> str:
        body = {"name": name, "lane_count": lanes}
        return (await self.ok("POST", f"/tournaments/{tid}/ranges", 201, json=body))["id"]

    async def klass(self, tid: str, code: str = "offen", name: str = "Offene Klasse") -> str:
        body = {"code": code, "name": name, "short": code[:3].upper()}
        return (await self.ok("POST", f"/tournaments/{tid}/classes", 201, json=body))["id"]

    async def competition(
        self, tid: str, range_id: str | None, name: str = "Fallscheibe", **fields: Any
    ) -> dict[str, Any]:
        body = {"name": name, "definition": OWN_DEFINITION, "range_id": range_id, **fields}
        return await self.ok("POST", f"/tournaments/{tid}/competitions", 201, json=body)

    async def club(self, name: str) -> str:
        return (await self.ok("POST", "/clubs", 201, json={"name": name}))["id"]

    async def person(self, name: str | None = None, **fields: Any) -> str:
        self._counter[0] += 1
        body = {"name": name or f"Person{self._counter[0]} Muster", **fields}
        return (await self.ok("POST", "/persons", 201, json=body))["id"]

    async def entry(self, tid: str, class_id: str, person_id: str | None = None, **fields: Any):
        body = {"person_id": person_id or await self.person(), "class_id": class_id, **fields}
        return await self.ok("POST", f"/tournaments/{tid}/entries", 201, json=body)

    async def book(self, tid: str, eid: str, cid: str, **fields: Any) -> list[dict[str, Any]]:
        body = {"competition_id": cid, **fields}
        return await self.ok("POST", f"/tournaments/{tid}/entries/{eid}/starts", 201, json=body)

    async def set_status(self, tid: str, *steps: str) -> None:
        for step in steps:
            await self.ok("POST", f"/tournaments/{tid}/status", json={"status": step})


@pytest.fixture
async def api(
    clean_db: None, settings_for: Callable[[Path], Settings], minimal_catalog: Path, tmp_path: Path
) -> AsyncIterator[Api]:
    settings = settings_for(minimal_catalog).model_copy(update={"data_dir": tmp_path / "data"})
    app = create_app(settings)
    async with running(app) as client:
        queue = app.state.events.subscribe()
        yield Api(client=client, app=app, events=queue)
        app.state.events.unsubscribe(queue)
    crypto.set_field_cipher(None)


@dataclass
class Setup:
    """Turnier mit einem Stand, einer Klasse und einem Wettbewerb nach Reihenfolge."""

    tid: str
    range_id: str
    class_id: str
    competition_id: str


@pytest.fixture
async def queue_setup(api: Api) -> Setup:
    tid = await api.tournament()
    range_id = await api.range(tid, lanes=2)
    class_id = await api.klass(tid)
    competition = await api.competition(tid, range_id, planning="queue")
    api.drain()
    return Setup(tid, range_id, class_id, competition["id"])
