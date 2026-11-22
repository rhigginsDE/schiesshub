"""Gekoppelte Geräte mit Standardrolle „Anzeige“ zeigen ihre Anzeige (echter Prüfer)."""

from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.core import crypto
from app.core.config import Settings
from app.core.security import reset_permission_checker
from app.main import create_app
from app.modules.auth.settings import AuthSettings
from tests.auth.conftest import client_for, role_id, setup_admin
from tests.conftest import REAL_CATALOG_DIR

API = "/api/v1"


@pytest.fixture
async def app(
    clean_db: None, settings_for: Callable[[Path], Settings], tmp_path: Path
) -> AsyncIterator[FastAPI]:
    settings = settings_for(REAL_CATALOG_DIR).model_copy(update={"data_dir": tmp_path / "data"})
    application = create_app(settings)
    application.state.auth_settings = AuthSettings(enforced=True)
    application.state.test_clients = []
    async with application.router.lifespan_context(application):
        try:
            yield application
        finally:
            for client in application.state.test_clients:
                await client.aclose()
    reset_permission_checker()
    crypto.set_field_cipher(None)


async def pair_display_device(
    app: FastAPI, admin: httpx.AsyncClient
) -> tuple[httpx.AsyncClient, str]:
    display_role = await role_id(admin, "Anzeige")
    code = (
        await admin.post(
            f"{API}/devices/pairing-codes",
            json={"name": "Fernseher", "default_role_id": display_role},
        )
    ).json()["code"]
    device = client_for(app)
    paired = await device.post(f"{API}/auth/pair", json={"code": code, "device_name": "Fernseher"})
    assert paired.status_code == 201, paired.text
    return device, paired.json()["device"]["id"]


async def test_device_shows_its_display(app: FastAPI) -> None:
    admin = client_for(app)
    await setup_admin(admin)
    tv, tv_id = await pair_display_device(app, admin)

    unassigned = await tv.get(f"{API}/displays/mine")
    assert unassigned.status_code == 404
    assert unassigned.json()["detail"].startswith("Diesem Gerät ist keine Anzeige zugewiesen.")

    (main,) = (await admin.get(f"{API}/displays")).json()
    assigned = await admin.put(f"{API}/displays/{main['id']}/device", json={"device_id": tv_id})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["device_id"] == tv_id

    mine = await tv.get(f"{API}/displays/mine")
    assert mine.status_code == 200
    assert mine.json()["id"] == main["id"]
    feed = await tv.get(f"{API}/displays/mine/feed")
    assert feed.status_code == 200
    assert feed.json()["display_id"] == main["id"]
    assert feed.headers["etag"] == f'"{feed.json()["version"]}"'
    by_id = await tv.get(f"{API}/displays/{main['id']}/feed")
    assert by_id.json()["version"] == feed.json()["version"]

    # Die Anzeige darf lesen, aber nichts einstellen.
    forbidden = await tv.get(f"{API}/displays")
    assert forbidden.status_code == 403
    assert "display.control" in forbidden.json()["detail"]
    forbidden = await tv.put(f"{API}/displays/{main['id']}/config", json={"scenes": []})
    assert forbidden.status_code == 403

    # Ein Gerät zeigt höchstens eine Anzeige.
    other = (await admin.post(f"{API}/displays", json={"name": "Flur"})).json()
    taken = await admin.put(f"{API}/displays/{other['id']}/device", json={"device_id": tv_id})
    assert taken.status_code == 409
    assert taken.json()["detail"] == (
        "Das Gerät „Fernseher“ zeigt schon die Anzeige „Hauptanzeige“. Bitte es dort zuerst lösen."
    )

    released = await admin.delete(f"{API}/displays/{main['id']}/device")
    assert released.json()["device_id"] is None
    assert (await tv.get(f"{API}/displays/mine")).status_code == 404
    moved = await admin.put(f"{API}/displays/{other['id']}/device", json={"device_id": tv_id})
    assert moved.status_code == 200
    assert (await tv.get(f"{API}/displays/mine")).json()["name"] == "Flur"

    # Wird das Gerät gelöscht, verliert die Anzeige die Zuordnung (ON DELETE SET NULL).
    deleted = await admin.delete(f"{API}/devices/{tv_id}")
    assert deleted.status_code == 204, deleted.text
    assert (await admin.get(f"{API}/displays/{other['id']}")).json()["device_id"] is None


async def test_blocked_device_cannot_be_assigned(app: FastAPI) -> None:
    admin = client_for(app)
    await setup_admin(admin)
    _, tv_id = await pair_display_device(app, admin)
    blocked = await admin.patch(f"{API}/devices/{tv_id}", json={"blocked": True})
    assert blocked.status_code == 200, blocked.text
    (main,) = (await admin.get(f"{API}/displays")).json()
    response = await admin.put(f"{API}/displays/{main['id']}/device", json={"device_id": tv_id})
    assert response.status_code == 409
    assert response.json()["detail"] == "Das Gerät ist gesperrt und kann keine Anzeige zeigen."
