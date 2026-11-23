"""Fixtures für das Modul `ergebnisse`: Anwendung mit echtem Katalog, Aufbau-Hilfen.

Die Sicherung läuft mit einem eigenen Datenverzeichnis; die Mitschrift liegt unter
`<data_dir>/backups/journal`.
"""

import asyncio
import uuid
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
FALLSCHEIBE = "4401"


def precision_definition(series: int = 2, counted: int | None = None) -> dict[str, Any]:
    """Präzision: `series` Serien zu 5 Schuss, Gleichstand nach Zehnern und Innenzehnern."""
    section: dict[str, Any] = {
        "id": "praezision",
        "name": "Präzision",
        "serien": series,
        "schuss_je_serie": 5,
    }
    if counted is not None:
        section["serien_gewertet"] = counted
    return {
        "variant": {"id": "standard", "name": "Standard", "abschnitte": [section]},
        "scoring": {
            "modell": "ringe",
            "rangfolge": "absteigend",
            "gleichstand": ["zehner", "innenzehner"],
            "geprueft": False,
        },
    }


def shots(*series: list[int | str]) -> dict[str, Any]:
    return {"sections": {"praezision": {"series": [{"shots": list(s)} for s in series]}}}


def falls(*series: dict[str, Any]) -> dict[str, Any]:
    return {"sections": {"fallscheibe": {"series": list(series)}}}


@dataclass
class Api:
    client: httpx.AsyncClient
    app: FastAPI
    events: asyncio.Queue[Event]
    data_dir: Path
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

    # --- Aufbau ---------------------------------------------------------------

    async def tournament(self, **settings: Any) -> str:
        # Name und Datum sind je Turnier eindeutig: Wiederholungen bekommen eine Nummer.
        body: dict[str, Any] = {"name": self._unique("Vereinspokal"), "date_from": "2027-03-06"}
        if settings:
            body["settings"] = settings
        return (await self.ok("POST", "/tournaments", 201, json=body))["id"]

    async def range(self, tid: str, lanes: int = 8) -> str:
        body = {"name": "Stand 1", "lane_count": lanes}
        return (await self.ok("POST", f"/tournaments/{tid}/ranges", 201, json=body))["id"]

    async def klass(self, tid: str, code: str = "offen", **fields: Any) -> str:
        body = {"code": code, "name": f"Klasse {code}", "short": code[:3].upper(), **fields}
        return (await self.ok("POST", f"/tournaments/{tid}/classes", 201, json=body))["id"]

    async def competition(self, tid: str, range_id: str, **fields: Any) -> dict[str, Any]:
        body = {"name": "Wettbewerb", "range_id": range_id, "planning": "queue", **fields}
        return await self.ok("POST", f"/tournaments/{tid}/competitions", 201, json=body)

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

    async def starts(self, tid: str, eid: str, cid: str, count: int = 1) -> list[str]:
        body = {"competition_id": cid, "count": count} if count > 1 else {"competition_id": cid}
        booked = await self.ok("POST", f"/tournaments/{tid}/entries/{eid}/starts", 201, json=body)
        return [start["id"] for start in booked]

    async def call(self, tid: str, sid: str) -> None:
        await self.ok("POST", f"/tournaments/{tid}/starts/{sid}/call")

    async def status(self, tid: str, *steps: str) -> None:
        for step in steps:
            await self.ok("POST", f"/tournaments/{tid}/status", json={"status": step})

    # --- Ergebnisse -------------------------------------------------------------

    def start_path(self, tid: str, sid: str) -> str:
        return f"/tournaments/{tid}/starts/{sid}"

    async def put_raw(
        self, tid: str, sid: str, raw: dict[str, Any], base_seq: int, **kwargs: Any
    ) -> dict[str, Any]:
        return await self.ok(
            "PUT",
            f"{self.start_path(tid, sid)}/raw",
            json={"raw": raw, "base_seq": base_seq},
            **kwargs,
        )

    async def finalize(self, tid: str, sid: str, base_seq: int) -> dict[str, Any]:
        return await self.ok(
            "POST", f"{self.start_path(tid, sid)}/finalize", json={"base_seq": base_seq}
        )

    async def shoot(
        self, tid: str, sid: str, raw: dict[str, Any], *, final: bool = True
    ) -> dict[str, Any]:
        """Aufrufen, erfassen und (standardmäßig) abschließen."""
        await self.call(tid, sid)
        state = await self.put_raw(tid, sid, raw, 0)
        if final:
            state = await self.finalize(tid, sid, state["seq"])
        return state

    async def ranking(self, tid: str, cid: str, **params: Any) -> dict[str, Any]:
        return await self.ok("GET", f"/tournaments/{tid}/competitions/{cid}/ranking", params=params)


@pytest.fixture
async def api(
    clean_db: None, settings_for: Callable[[Path], Settings], tmp_path: Path
) -> AsyncIterator[Api]:
    data_dir = tmp_path / "data"
    settings = settings_for(REAL_CATALOG_DIR).model_copy(update={"data_dir": data_dir})
    app = create_app(settings)
    async with running(app) as client:
        queue = app.state.events.subscribe()
        yield Api(client=client, app=app, events=queue, data_dir=data_dir)
        app.state.events.unsubscribe(queue)
    crypto.set_field_cipher(None)


@dataclass
class Setup:
    tid: str
    range_id: str
    class_id: str
    cid: str


async def make_setup(api: Api, **competition: Any) -> Setup:
    tid = await api.tournament()
    range_id = await api.range(tid)
    class_id = await api.klass(tid)
    created = await api.competition(tid, range_id, **competition)
    await api.status(tid, "active")
    api.drain()
    return Setup(tid, range_id, class_id, created["id"])


@pytest.fixture
async def fallscheibe(api: Api) -> Setup:
    """Turnier mit Flinte 15 m Fallscheibe (4401) aus dem echten Katalog."""
    return await make_setup(
        api, catalog_federation="bds", catalog_code=FALLSCHEIBE, capture_mode="series"
    )


@pytest.fixture
async def precision(api: Api) -> Setup:
    """Turnier mit eigener Präzision (2 × 5 Schuss), Einzelschuss."""
    return await make_setup(api, definition=precision_definition(), capture_mode="shot")


def new_id() -> str:
    return str(uuid.uuid4())
