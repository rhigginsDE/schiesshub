"""Fixtures für das Modul `auth`.

Jeder Test startet eine eigene Anwendung mit eigenen Auth-Einstellungen. Nach dem Test wird der
offene Prüfer wiederhergestellt, damit Tests anderer Module unberührt bleiben.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.security import Actor, require, reset_permission_checker
from app.main import create_app
from app.modules.auth.identity import CSRF_HEADER
from app.modules.auth.settings import AuthSettings

API = "/api/v1"
ADMIN_NAME = "Anna Admin"
ADMIN_PIN = "1234"

AppFactory = Callable[..., AbstractAsyncContextManager[FastAPI]]
PROBE_PERMISSIONS = ("tournament.read", "tournament.edit", "result.read", "result.correct")


def add_probe_routes(app: FastAPI) -> None:
    """Endpunkte, wie sie fremde Module anlegen: geschützt mit `require(...)`."""

    def actor_json(actor: Actor) -> dict[str, Any]:
        return {
            "user_id": str(actor.user_id) if actor.user_id else None,
            "device_id": str(actor.device_id) if actor.device_id else None,
            "user_name": actor.user_name,
            "permissions": sorted(actor.permissions),
        }

    def endpoint(permission: str) -> Callable[..., Any]:
        async def probe(actor: Annotated[Actor, Depends(require(permission))]) -> dict[str, Any]:
            return actor_json(actor)

        return probe

    for permission in PROBE_PERMISSIONS:
        app.add_api_route(
            f"{API}/probe/{permission}", endpoint(permission), methods=["GET", "POST"]
        )


@pytest.fixture
def make_app(
    clean_db: None, settings_for: Callable[[Path], Settings], minimal_catalog: Path
) -> AsyncIterator[AppFactory]:
    @asynccontextmanager
    async def start(**auth: Any) -> AsyncIterator[FastAPI]:
        app = create_app(settings_for(minimal_catalog))
        app.state.auth_settings = AuthSettings(**auth)
        app.state.test_clients = []
        add_probe_routes(app)
        async with app.router.lifespan_context(app):
            try:
                yield app
            finally:
                for client in app.state.test_clients:
                    await client.aclose()

    yield start
    reset_permission_checker()


def client_for(app: FastAPI, *, https: bool = False, csrf: bool = True) -> httpx.AsyncClient:
    """Ein Browser: eigener Cookie-Speicher, schickt standardmäßig den CSRF-Header.

    Wird beim Beenden der Anwendung geschlossen."""
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=f"{'https' if https else 'http'}://schiesshub.test",
        headers={CSRF_HEADER: "1"} if csrf else {},
    )
    app.state.test_clients.append(client)
    return client


async def setup_admin(client: httpx.AsyncClient) -> httpx.Response:
    response = await client.post(
        f"{API}/auth/setup",
        json={"name": ADMIN_NAME, "pin": ADMIN_PIN, "device_name": "Kasse 1"},
    )
    assert response.status_code == 201, response.text
    return response


async def role_id(client: httpx.AsyncClient, name: str) -> str:
    roles = (await client.get(f"{API}/roles")).json()
    return next(role["id"] for role in roles if role["name"] == name)


async def pair_new_device(
    app: FastAPI, admin: httpx.AsyncClient, **code_fields: Any
) -> httpx.AsyncClient:
    code = (await admin.post(f"{API}/devices/pairing-codes", json=code_fields)).json()["code"]
    device = client_for(app)
    response = await device.post(f"{API}/auth/pair", json={"code": code, "device_name": "Tablet"})
    assert response.status_code == 201, response.text
    return device


async def create_user(admin: httpx.AsyncClient, name: str, pin: str, role: str) -> dict[str, Any]:
    response = await admin.post(
        f"{API}/users", json={"name": name, "pin": pin, "role_id": await role_id(admin, role)}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def login(client: httpx.AsyncClient, user_id: str, pin: str) -> httpx.Response:
    return await client.post(f"{API}/auth/login", json={"user_id": user_id, "pin": pin})


async def sql(engine: AsyncEngine, statement: str, **params: Any) -> list[Any]:
    async with engine.begin() as connection:
        result = await connection.execute(text(statement), params)
        return list(result) if result.returns_rows else []


async def set_time(engine: AsyncEngine, table: str, column: str, value: datetime) -> None:
    await sql(engine, f'UPDATE "{table}" SET {column} = :value', value=value)
