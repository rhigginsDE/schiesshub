"""Fixtures für das Modul `anzeige`: Anwendung mit echtem Katalog und Aufbau-Hilfen.

Turnier, Starts und Ergebnisse entstehen über die APIs der anderen Module.
"""

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
from tests.conftest import REAL_CATALOG_DIR, running

API = "/api/v1"


def precision_definition(series: int = 2) -> dict[str, Any]:
    """Eigene Präzision: `series` Serien zu 5 Schuss, Einzelschuss."""
    return {
        "variant": {
            "id": "standard",
            "name": "Standard",
            "abschnitte": [
                {"id": "praezision", "name": "Präzision", "serien": series, "schuss_je_serie": 5}
            ],
        },
        "scoring": {
            "modell": "ringe",
            "rangfolge": "absteigend",
            "gleichstand": ["zehner", "innenzehner"],
            "geprueft": False,
        },
    }


def shots(*series: list[int | str]) -> dict[str, Any]:
    return {"sections": {"praezision": {"series": [{"shots": list(s)} for s in series]}}}


@dataclass
class Api:
    client: httpx.AsyncClient
    app: FastAPI
    events: asyncio.Queue[Event]
    _counter: list[int] = field(default_factory=lambda: [0])
    _tournament_names: list[str] = field(default_factory=list)

    def _unique(self, name: str) -> str:
        count = self._tournament_names.count(name)
        self._tournament_names.append(name)
        return name if count == 0 else f"{name} ({count + 1})"

    def drain(self) -> list[Event]:
        received = []
        while not self.events.empty():
            received.append(self.events.get_nowait())
        return received

    async def ok(self, method: str, path: str, status: int = 200, **kwargs: Any) -> Any:
        response = await self.client.request(method, f"{API}{path}", **kwargs)
        assert response.status_code == status, response.text
        return response.json() if response.content else None

    async def fail(self, method: str, path: str, status: int, **kwargs: Any) -> dict[str, Any]:
        response = await self.client.request(method, f"{API}{path}", **kwargs)
        assert response.status_code == status, response.text
        return response.json()

    # --- Turnier und Teilnehmer ---------------------------------------------------

    async def tournament(self, name: str = "Vereinspokal", **settings: Any) -> str:
        # Name und Datum sind je Turnier eindeutig: Wiederholungen bekommen eine Nummer.
        body: dict[str, Any] = {
            "name": self._unique(name),
            "organizer": "SV Muster",
            "date_from": "2027-03-06",
        }
        if settings:
            body["settings"] = settings
        return (await self.ok("POST", "/tournaments", 201, json=body))["id"]

    async def range(self, tid: str, lanes: int = 4, name: str = "Stand 1") -> str:
        body = {"name": name, "lane_count": lanes}
        return (await self.ok("POST", f"/tournaments/{tid}/ranges", 201, json=body))["id"]

    async def klass(self, tid: str, code: str = "offen") -> str:
        body = {"code": code, "name": f"Klasse {code}", "short": code[:3].upper()}
        return (await self.ok("POST", f"/tournaments/{tid}/classes", 201, json=body))["id"]

    async def competition(self, tid: str, range_id: str | None, **fields: Any) -> dict[str, Any]:
        body: dict[str, Any] = {"range_id": range_id, "planning": "queue", **fields}
        if "catalog_code" not in fields:
            body.setdefault("name", "Präzision")
            body.setdefault("definition", precision_definition())
            body.setdefault("capture_mode", "shot")
        return await self.ok("POST", f"/tournaments/{tid}/competitions", 201, json=body)

    async def club(self, name: str) -> str:
        return (await self.ok("POST", "/clubs", 201, json={"name": name}))["id"]

    async def entry(self, tid: str, class_id: str, name: str | None = None, **person: Any) -> str:
        self._counter[0] += 1
        body = {"name": name or f"Person{self._counter[0]} Muster", **person}
        person_id = (await self.ok("POST", "/persons", 201, json=body))["id"]
        entry = await self.ok(
            "POST",
            f"/tournaments/{tid}/entries",
            201,
            json={"person_id": person_id, "class_id": class_id},
        )
        return entry["id"]

    async def start(self, tid: str, eid: str, cid: str) -> str:
        booked = await self.ok(
            "POST", f"/tournaments/{tid}/entries/{eid}/starts", 201, json={"competition_id": cid}
        )
        return booked[0]["id"]

    async def status(self, tid: str, *steps: str) -> None:
        for step in steps:
            await self.ok("POST", f"/tournaments/{tid}/status", json={"status": step})

    # --- Ablauf am Stand und Ergebnisse --------------------------------------------

    async def call(self, tid: str, sid: str) -> None:
        await self.ok("POST", f"/tournaments/{tid}/starts/{sid}/call")

    async def shoot(self, tid: str, sid: str, raw: dict[str, Any], *, final: bool = True) -> None:
        await self.call(tid, sid)
        state = await self.ok(
            "PUT", f"/tournaments/{tid}/starts/{sid}/raw", json={"raw": raw, "base_seq": 0}
        )
        if final:
            await self.ok(
                "POST",
                f"/tournaments/{tid}/starts/{sid}/finalize",
                json={"base_seq": state["seq"]},
            )

    # --- Anzeige ----------------------------------------------------------------

    async def displays(self) -> list[dict[str, Any]]:
        return await self.ok("GET", "/displays")

    async def display(self, name: str = "Stand-Bildschirm", **fields: Any) -> dict[str, Any]:
        return await self.ok("POST", "/displays", 201, json={"name": name, **fields})

    async def feed(self, display_id: str) -> dict[str, Any]:
        return await self.ok("GET", f"/displays/{display_id}/feed")

    async def show(self, *scenes: dict[str, Any], tid: str | None = None, **config: Any) -> str:
        """Neue Anzeige mit genau diesen Szenen; liefert ihre ID."""
        self._counter[0] += 1
        created = await self.display(
            f"Anzeige {self._counter[0]}",
            tournament_id=tid,
            config={"scenes": list(scenes), **config},
        )
        return created["id"]


@pytest.fixture
async def api(
    clean_db: None, settings_for: Callable[[Path], Settings], tmp_path: Path
) -> AsyncIterator[Api]:
    settings = settings_for(REAL_CATALOG_DIR).model_copy(update={"data_dir": tmp_path / "data"})
    app = create_app(settings)
    async with running(app) as client:
        queue = app.state.events.subscribe()
        yield Api(client=client, app=app, events=queue)
        app.state.events.unsubscribe(queue)
    crypto.set_field_cipher(None)


@dataclass
class Setup:
    """Aktives Turnier mit einem Stand, einer Klasse und einer Präzision nach Reihenfolge."""

    tid: str
    range_id: str
    class_id: str
    cid: str


@pytest.fixture
async def setup(api: Api) -> Setup:
    tid = await api.tournament()
    range_id = await api.range(tid)
    class_id = await api.klass(tid)
    cid = (await api.competition(tid, range_id))["id"]
    await api.status(tid, "active")
    api.drain()
    return Setup(tid, range_id, class_id, cid)
