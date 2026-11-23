"""Rechte an der Sicherung mit Berechtigungsprüfung: auslösen, einrichten, wiederherstellen.

Und was mit dem Zugang der auslösenden Person geschieht, wenn Konto oder Gerät in der Sicherung
fehlen.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.security import reset_permission_checker
from app.main import create_app
from app.modules.auth.settings import AuthSettings
from tests.auth.conftest import (
    API,
    client_for,
    create_user,
    login,
    pair_new_device,
    setup_admin,
)
from tests.backup.test_guided_restore import _wait, leftovers  # noqa: F401


@asynccontextmanager
async def enforced_app(settings: Settings) -> AsyncIterator[FastAPI]:
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


@pytest.mark.usefixtures("idle_scheduler", "clean_db")
async def test_lead_runs_backup_but_cannot_set_up_or_restore(backup_settings: Settings) -> None:
    async with enforced_app(backup_settings) as app:
        admin = client_for(app)
        await setup_admin(admin)
        lead = await create_user(admin, "Lena Leitung", "4711", "Turnierleitung")
        cash = await create_user(admin, "Karl Kasse", "4712", "Kasse")
        tablet = await pair_new_device(app, admin)
        await login(tablet, lead["id"], "4711")
        run = await tablet.post(f"{API}/backup/run")
        recheck = await tablet.post(f"{API}/backup/usb/recheck")
        status = await tablet.get(f"{API}/backup/status")
        settings = await tablet.put(f"{API}/backup/settings", json={"enabled": True})
        passphrase = await tablet.put(
            f"{API}/backup/passphrase", json={"passphrase": "ein langes Passwort"}
        )
        sources = await tablet.get(f"{API}/backup/restore/sources")
        restore_status = await tablet.get(f"{API}/backup/restore/status")
        other = await pair_new_device(app, admin)
        await login(other, cash["id"], "4712")
        cash_run = await other.post(f"{API}/backup/run")
        admin_sources = await admin.get(f"{API}/backup/restore/sources")

    assert run.status_code == 200, run.text
    assert run.json()[0]["ok"] is True
    assert recheck.status_code == 200
    assert status.status_code == 200
    assert settings.status_code == passphrase.status_code == 403
    assert sources.status_code == restore_status.status_code == 403
    assert "backup.restore" in sources.json()["detail"]
    assert cash_run.status_code == 403
    assert "backup.run" in cash_run.json()["detail"]
    assert admin_sources.status_code == 200


@pytest.mark.usefixtures("idle_scheduler", "clean_db", "leftovers")
async def test_admin_missing_from_backup_must_accept_lockout(
    backup_settings: Settings, engine: AsyncEngine
) -> None:
    async with enforced_app(backup_settings) as app:
        anna = client_for(app)
        await setup_admin(anna)
        local, *_ = (await anna.post(f"{API}/backup/run")).json()
        source_id = f"local:{local['file_name']}"

        # Nach der Sicherung: zweiter Administrator an einem neuen Gerät.
        bodo_account = await create_user(anna, "Bodo Admin", "5678", "Administrator")
        bodo = await pair_new_device(app, anna)
        await login(bodo, bodo_account["id"], "5678")

        bodo_preview = (
            await bodo.post(f"{API}/backup/restore/preview", json={"source_id": source_id})
        ).json()
        anna_preview = (
            await anna.post(f"{API}/backup/restore/preview", json={"source_id": source_id})
        ).json()

        body = {"source_id": source_id, "confirm": source_id}
        await bodo.post(f"{API}/backup/restore/execute", json=body)
        refused = await _wait(anna)
        await bodo.post(f"{API}/backup/restore/execute", json={**body, "accept_lockout": True})
        done = await _wait(anna)
        bodo_after = await bodo.get(f"{API}/backup/restore/status")
        anna_after = await anna.get(f"{API}/backup/restore/status")
    await engine.dispose()

    access = bodo_preview["access"]
    assert access["enforced_now"] is True
    assert access["account_in_backup"] is False
    assert access["device_in_backup"] is False
    assert access["lockout_risk"] is True
    assert "auth.cli" in access["message_de"]
    assert anna_preview["access"]["lockout_risk"] is False
    assert anna_preview["access"]["session_in_backup"] is True
    assert refused["state"] == "failed"
    assert "accept_lockout" in refused["error_de"]
    assert done["state"] == "succeeded", done
    # Bodo und sein Gerät gibt es nach der Wiederherstellung nicht mehr; Anna bleibt angemeldet.
    assert bodo_after.status_code == 401
    assert bodo_after.json()["code"] == "device_unknown"
    assert anna_after.status_code == 200
