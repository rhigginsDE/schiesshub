"""Fixtures für das Modul `export`: Anwendung mit echtem Katalog und Aufbau-Hilfen.

Die Namen in den Tests sind erfunden.
"""

import csv
import io
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import HTTPException, Request

from app.core import crypto
from app.core.config import Settings
from app.core.security import Actor, reset_permission_checker, set_permission_checker
from app.main import create_app
from tests.conftest import REAL_CATALOG_DIR, running

API = "/api/v1"


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


def read_csv(content: bytes) -> list[list[str]]:
    assert content.startswith(b"\xef\xbb\xbf"), "UTF-8-BOM fehlt"
    text = content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=";"))


def as_dicts(rows: list[list[str]]) -> list[dict[str, str]]:
    header, *body = rows
    return [dict(zip(header, row, strict=True)) for row in body]


@dataclass
class Api:
    client: httpx.AsyncClient
    _clubs: dict[str, str] = field(default_factory=dict)
    _counter: list[int] = field(default_factory=lambda: [0])

    async def ok(self, method: str, path: str, status: int = 200, **kwargs: Any) -> Any:
        response = await self.client.request(method, f"{API}{path}", **kwargs)
        assert response.status_code == status, response.text
        return response.json() if response.content else None

    async def get(self, path: str, status: int = 200, **params: Any) -> httpx.Response:
        response = await self.client.get(f"{API}{path}", params=params)
        assert response.status_code == status, response.text
        return response

    async def tournament(self, name: str = "Vereinspokal 2027", **settings: Any) -> str:
        body: dict[str, Any] = {
            "name": name,
            "organizer": "SV Musterstadt",
            "date_from": "2027-03-06",
        }
        if settings:
            body["settings"] = settings
        return (await self.ok("POST", "/tournaments", 201, json=body))["id"]

    async def range(self, tid: str, name: str = "Stand 1", lanes: int = 8) -> str:
        body = {"name": name, "lane_count": lanes}
        return (await self.ok("POST", f"/tournaments/{tid}/ranges", 201, json=body))["id"]

    async def klass(self, tid: str, code: str = "offen", **fields: Any) -> str:
        body = {"code": code, "name": f"Klasse {code}", "short": code[:3].upper(), **fields}
        return (await self.ok("POST", f"/tournaments/{tid}/classes", 201, json=body))["id"]

    async def competition(self, tid: str, range_id: str, **fields: Any) -> str:
        body = {"name": "Wettbewerb", "range_id": range_id, "planning": "queue", **fields}
        return (await self.ok("POST", f"/tournaments/{tid}/competitions", 201, json=body))["id"]

    async def club(self, name: str) -> str:
        if name not in self._clubs:
            club = await self.ok("POST", "/clubs", 201, json={"name": name})
            self._clubs[name] = club["id"]
        return self._clubs[name]

    async def entry(
        self,
        tid: str,
        class_id: str,
        name: str | None = None,
        club: str | None = None,
        **person: Any,
    ) -> str:
        self._counter[0] += 1
        body = {"name": name or f"Person{self._counter[0]} Muster", **person}
        if club is not None:
            body["club_id"] = await self.club(club)
        person_id = (await self.ok("POST", "/persons", 201, json=body))["id"]
        entry = await self.ok(
            "POST",
            f"/tournaments/{tid}/entries",
            201,
            json={"person_id": person_id, "class_id": class_id},
        )
        return entry["id"]

    async def starts(self, tid: str, eid: str, cid: str, count: int = 1, **extra: Any) -> list[str]:
        body = {"competition_id": cid, **extra}
        if count > 1:
            body["count"] = count
        booked = await self.ok("POST", f"/tournaments/{tid}/entries/{eid}/starts", 201, json=body)
        return [start["id"] for start in booked]

    async def activate(self, tid: str) -> None:
        await self.ok("POST", f"/tournaments/{tid}/status", json={"status": "active"})

    async def shoot(self, tid: str, sid: str, raw: dict[str, Any], *, final: bool = True) -> None:
        path = f"/tournaments/{tid}/starts/{sid}"
        await self.ok("POST", f"{path}/call")
        state = await self.ok("PUT", f"{path}/raw", json={"raw": raw, "base_seq": 0})
        if final:
            await self.ok("POST", f"{path}/finalize", json={"base_seq": state["seq"]})

    async def abort(self, tid: str, sid: str, reason: str) -> None:
        await self.ok(
            "POST", f"/tournaments/{tid}/starts/{sid}/abort", json={"abort_reason": reason}
        )


@pytest.fixture
async def api(
    clean_db: None, settings_for: Callable[[Path], Settings], tmp_path: Path
) -> AsyncIterator[Api]:
    settings = settings_for(REAL_CATALOG_DIR).model_copy(update={"data_dir": tmp_path / "data"})
    async with running(create_app(settings)) as client:
        yield Api(client=client)
    crypto.set_field_cipher(None)


@pytest.fixture
def grant() -> Iterator[Callable[..., None]]:
    """Ersetzt den Berechtigungsprüfer: nur die genannten Berechtigungen sind erlaubt."""

    def install(*allowed: str) -> None:
        async def checker(request: Request, permission: str) -> Actor:
            if permission not in allowed:
                raise HTTPException(403, f"Dafür fehlt die Berechtigung „{permission}“.")
            return Actor(permissions=frozenset(allowed))

        set_permission_checker(checker)

    yield install
    reset_permission_checker()


@dataclass
class Setup:
    tid: str
    range_id: str
    class_id: str
    cid: str


async def make_setup(
    api: Api, *, tournament: dict[str, Any] | None = None, **competition: Any
) -> Setup:
    tid = await api.tournament(**(tournament or {}))
    range_id = await api.range(tid)
    class_id = await api.klass(tid)
    if "catalog_code" not in competition:
        competition.setdefault("definition", precision_definition())
        competition.setdefault("capture_mode", "shot")
    cid = await api.competition(tid, range_id, **competition)
    await api.activate(tid)
    return Setup(tid, range_id, class_id, cid)
