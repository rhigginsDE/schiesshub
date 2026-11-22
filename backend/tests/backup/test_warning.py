"""Warnung der Sicherung für alle gekoppelten Geräte (`GET /backup/warning`) und ihr Ereignis."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core.config import Settings
from app.core.security import reset_permission_checker
from app.main import create_app
from app.modules.auth.settings import AuthSettings
from app.modules.system.router import router as system_router
from tests.auth.conftest import (
    client_for,
    create_user,
    login,
    pair_new_device,
    role_id,
    setup_admin,
)
from tests.backup.conftest import PASSPHRASE, BackupApp, BackupEnv

API = "/api/v1"
WARNING_KEYS = {"warning", "warn_all_stations", "warn_on_display"}


async def test_warning_open_mode(backup: BackupApp) -> None:
    response = await backup.client.get(f"{API}/backup/warning")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == WARNING_KEYS
    assert body["warn_all_stations"] is True
    assert body["warn_on_display"] is False
    # Ohne Stick und ohne Passwort: dieselbe Warnung wie im Status, gleiche Form.
    status = (await backup.client.get(f"{API}/backup/status")).json()
    assert body["warning"] == status["warning"]
    assert body["warning"]["code"] == "usb_missing"
    assert set(body["warning"]) == {"code", "message_de", "since"}


async def test_warning_follows_settings_and_clears(backup: BackupApp) -> None:
    settings = (await backup.client.get(f"{API}/backup/settings")).json()
    await backup.client.put(
        f"{API}/backup/settings",
        json={**settings, "warn_all_stations": False, "warn_on_display": True},
    )
    await backup.client.put(f"{API}/backup/passphrase", json={"passphrase": PASSPHRASE})
    backup.env.plug_in()
    await backup.client.post(f"{API}/backup/usb/recheck")
    body = (await backup.client.get(f"{API}/backup/warning")).json()
    assert body == {"warning": None, "warn_all_stations": False, "warn_on_display": True}


async def test_warning_hides_paths_and_details(backup: BackupApp) -> None:
    """Die öffentliche Meldung nennt keine Pfade, Dateinamen oder Größen – der Status schon."""
    await backup.client.put(f"{API}/backup/passphrase", json={"passphrase": PASSPHRASE})
    backup.env.plug_in()
    await backup.client.post(f"{API}/backup/usb/recheck")
    service = backup.service
    service.usb.writable = False
    service.usb.error = f"Stick nicht lesbar: [Errno 5] Input/output error: '{backup.env.usb_dir}'"
    service._refresh_status()
    status = (await backup.client.get(f"{API}/backup/status")).json()
    body = (await backup.client.get(f"{API}/backup/warning")).json()
    assert status["warning"]["code"] == body["warning"]["code"] == "usb_not_writable"
    assert str(backup.env.usb_dir) in status["warning"]["message_de"]
    assert str(backup.env.usb_dir) not in body["warning"]["message_de"]
    assert body["warning"]["message_de"] == "Der Sicherungs-Stick ist nicht beschreibbar."
    assert body["warning"]["since"] == status["warning"]["since"]


async def test_status_event_carries_only_public_warning(backup: BackupApp) -> None:
    events = backup.app.state.events.subscribe()
    await backup.client.put(f"{API}/backup/passphrase", json={"passphrase": PASSPHRASE})
    backup.env.plug_in()
    await backup.client.post(f"{API}/backup/usb/recheck")
    runs = (await backup.client.post(f"{API}/backup/run")).json()
    received = []
    while not events.empty():
        received.append(events.get_nowait())
    status_events = [event for event in received if event.name == "backup.status"]
    assert status_events
    for event in status_events:
        assert set(event.data) == WARNING_KEYS
    done = [event for event in received if event.name == "backup.completed"]
    assert len(done) == 2
    for event in done:
        assert set(event.data["run"]) == {"id", "kind", "target", "ok"}
    # Kein Dateiname, keine Prüfsumme, keine Größe in den Ereignissen.
    text = " ".join(event.encode() for event in received)
    for run in runs:
        assert run["file_name"].removesuffix(".dump").removesuffix(".shb") not in text
        assert run["sha256"] not in text


async def test_settings_change_announces_status(backup: BackupApp) -> None:
    events = backup.app.state.events.subscribe()
    settings = (await backup.client.get(f"{API}/backup/settings")).json()
    await backup.client.put(f"{API}/backup/settings", json={**settings, "warn_on_display": True})
    received = []
    while not events.empty():
        received.append(events.get_nowait())
    status_events = [event for event in received if event.name == "backup.status"]
    assert status_events[-1].data["warn_on_display"] is True


# --- Mit Berechtigungsprüfung ---------------------------------------------------------


@asynccontextmanager
async def _enforced(settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(settings)
    app.state.auth_settings = AuthSettings(enforced=True)
    app.state.test_clients = []
    try:
        async with app.router.lifespan_context(app):
            try:
                yield app
            finally:
                for client in app.state.test_clients:
                    await client.aclose()
    finally:
        reset_permission_checker()


@pytest.fixture
async def enforced_app(
    clean_db: None, idle_scheduler: None, backup_settings: Settings
) -> AsyncIterator[FastAPI]:
    async with _enforced(backup_settings) as app:
        yield app


async def test_warning_for_every_paired_device(
    enforced_app: FastAPI, backup_env: BackupEnv
) -> None:
    app = enforced_app
    admin = client_for(app)
    await setup_admin(admin)
    display_role = await role_id(admin, "Anzeige")
    tv = await pair_new_device(app, admin, name="Halle 2", default_role_id=display_role)
    tablet = await pair_new_device(app, admin, name="Stand")
    cashier = await create_user(admin, "Kai Kasse", "4711", "Kasse")
    assert (await login(tablet, cashier["id"], "4711")).status_code == 200
    unlogged = await pair_new_device(app, admin, name="Ohne Rolle")
    stranger = client_for(app)

    expected = (await admin.get(f"{API}/backup/warning")).json()
    assert expected["warning"]["code"] == "usb_missing"
    for device in (tv, tablet, unlogged):
        response = await device.get(f"{API}/backup/warning")
        assert response.status_code == 200, response.text
        assert response.json() == expected
    # Den vollen Status sehen nur Rollen mit „Sicherung ansehen“.
    assert (await tv.get(f"{API}/backup/status")).status_code == 403
    assert (await tablet.get(f"{API}/backup/status")).status_code == 403
    # Nicht gekoppelt: abgewiesen wie überall.
    refused = await stranger.get(f"{API}/backup/warning")
    assert refused.status_code == 401
    # Schreiben ohne CSRF-Kopf bleibt verboten, auch über die gelockerte Prüfung.
    assert (await tv.post(f"{API}/backup/warning")).status_code in (403, 405)


async def test_sse_is_not_filtered_by_permissions(
    enforced_app: FastAPI, backup_env: BackupEnv
) -> None:
    """`GET /events` hängt an keiner Berechtigung: Jeder Abonnent bekommt `backup.status`.

    (httpx' ASGITransport kann einen endlosen Strom nicht stückweise lesen; geprüft werden
    deshalb die Route selbst und der Verteiler, über den der Strom läuft.)
    """
    route = next(
        route
        for route in system_router.routes
        if isinstance(route, APIRoute) and route.path == "/events"
    )
    names = {getattr(dep.call, "__name__", "") for dep in route.dependant.dependencies}
    assert names == {"get_event_hub"}

    admin = client_for(enforced_app)
    await setup_admin(admin)
    await admin.put(f"{API}/backup/passphrase", json={"passphrase": PASSPHRASE})
    subscriber = enforced_app.state.events.subscribe()
    backup_env.plug_in()
    await admin.post(f"{API}/backup/usb/recheck")
    received = []
    while not subscriber.empty():
        received.append(subscriber.get_nowait())
    data = next(event.data for event in received if event.name == "backup.status")
    assert set(data) == WARNING_KEYS
    assert data["warning"] is None
