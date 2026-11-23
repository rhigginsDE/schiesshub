"""Berechtigungsprüfung zur Laufzeit: in der App einschalten, nur auf der Konsole ausschalten.

Wirksam ist sie, wenn `AUTH_ENFORCED` gesetzt ist oder der gespeicherte Schalter an ist. Der
Schalter liegt im Speicher; der Server liest ihn beim Start und in kurzen Abständen neu, damit er
eine Änderung über die Konsole mitbekommt.
"""

import asyncio
import io
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.db import create_session_factory
from app.modules.auth import cli, enforcement, service
from app.modules.auth.models import AuditLog
from tests.auth.conftest import (
    ADMIN_PIN,
    API,
    AppFactory,
    client_for,
    create_user,
    login,
    pair_new_device,
    setup_admin,
    sql,
)
from tests.auth.test_cli import _run_cli

ENFORCEMENT = f"{API}/auth/enforcement"
ENABLE = f"{ENFORCEMENT}/enable"


def _codes(body: dict[str, Any]) -> list[str]:
    return [blocker["code"] for blocker in body["blockers"]]


async def _admin(app: FastAPI) -> httpx.AsyncClient:
    client = client_for(app)
    await setup_admin(client)
    return client


async def _audit_actions(engine: AsyncEngine) -> list[AuditLog]:
    async with create_session_factory(engine)() as session:
        statement = select(AuditLog).where(AuditLog.action.like("auth.enforcement%"))
        return list(await session.scalars(statement.order_by(AuditLog.created_at)))


async def _wait_for(check: Any) -> None:
    """Wartet bis zu 3 Sekunden, bis `check` wahr wird."""
    for _ in range(150):
        if await check():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("Zeit abgelaufen")


# --- GET /auth/enforcement ---------------------------------------------------


async def test_fresh_server_lists_all_blockers(make_app: AppFactory) -> None:
    async with make_app() as app:
        response = await client_for(app).get(ENFORCEMENT)

    assert response.status_code == 200
    body = response.json()
    assert body["enforced"] is False
    assert body["source"] is None
    assert body["can_enable"] is False
    assert _codes(body) == ["no_admin_with_pin", "device_not_paired", "not_logged_in"]
    assert all(blocker["message_de"] for blocker in body["blockers"])
    assert "keinen Administrator mit PIN" in body["blockers"][0]["message_de"]


async def test_logged_in_admin_can_enable(make_app: AppFactory) -> None:
    async with make_app() as app:
        admin = await _admin(app)
        mine = (await admin.get(ENFORCEMENT)).json()
        other = (await client_for(app).get(ENFORCEMENT)).json()

    assert mine == {"enforced": False, "source": None, "can_enable": True, "blockers": []}
    assert _codes(other) == ["device_not_paired", "not_logged_in"]


async def test_paired_device_needs_admin_login(make_app: AppFactory) -> None:
    async with make_app() as app:
        admin = await _admin(app)
        cashier = await create_user(admin, "Karl Kasse", "5555", "Kasse")
        tablet = await pair_new_device(app, admin)
        nobody = (await tablet.get(ENFORCEMENT)).json()
        assert (await login(tablet, cashier["id"], "5555")).status_code == 200
        wrong_role = (await tablet.get(ENFORCEMENT)).json()

    assert _codes(nobody) == ["not_logged_in"]
    assert _codes(wrong_role) == ["not_admin"]
    assert "nicht als Administrator angemeldet" in wrong_role["blockers"][0]["message_de"]


async def test_custom_role_with_all_management_rights_counts_as_admin(
    make_app: AppFactory,
) -> None:
    full = ["role.manage", "user.manage", "device.manage", "system.manage"]
    async with make_app() as app:
        admin = await _admin(app)
        for name, rights in (("Vorstand", full), ("Halb", full[:3])):
            created = await admin.post(f"{API}/roles", json={"name": name, "permissions": rights})
            assert created.status_code == 201, created.text
        await create_user(admin, "Vera Vorstand", "6666", "Vorstand")
        half = await create_user(admin, "Hans Halb", "7777", "Halb")
        board = (await admin.get(f"{API}/users")).json()
        vera = next(user for user in board if user["name"] == "Vera Vorstand")

        tablet = await pair_new_device(app, admin)
        assert (await login(tablet, vera["id"], "6666")).status_code == 200
        as_board = (await tablet.get(ENFORCEMENT)).json()
        assert (await login(tablet, half["id"], "7777")).status_code == 200
        as_half = (await tablet.get(ENFORCEMENT)).json()

    assert as_board["can_enable"] is True
    assert _codes(as_half) == ["not_admin"]


async def test_inactive_admin_does_not_count(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app:
        await _admin(app)
        await sql(engine, "UPDATE user_account SET active = false")
        body = (await client_for(app).get(ENFORCEMENT)).json()

    assert "no_admin_with_pin" in _codes(body)


async def test_env_switch_is_reported_as_source(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app:
        body = (await client_for(app).get(ENFORCEMENT)).json()

    assert body == {"enforced": True, "source": "env", "can_enable": False, "blockers": []}


# --- POST /auth/enforcement/enable --------------------------------------------


async def test_enable_switches_on_at_once(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app:
        admin = await _admin(app)
        stranger = client_for(app)
        assert (await stranger.get(f"{API}/probe/tournament.read")).status_code == 200
        queue = app.state.events.subscribe()

        response = await admin.post(ENABLE)

        names = [queue.get_nowait() for _ in range(queue.qsize())]
        probe = await stranger.get(f"{API}/probe/tournament.read")
        status = (await stranger.get(f"{API}/auth/status")).json()
        allowed = await admin.post(f"{API}/probe/tournament.edit")
        permissions = await stranger.get(f"{API}/auth/permissions")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "enforced": True,
        "source": "setting",
        "can_enable": False,
        "blockers": [],
    }
    assert probe.status_code == 401
    assert probe.json()["code"] == "device_unknown"
    assert status["auth_enforced"] is True
    assert allowed.status_code == 200
    assert permissions.status_code == 401
    changed = [event for event in names if event.name == enforcement.EVENT_CHANGED]
    assert [event.data for event in changed] == [{"enforced": True, "source": "setting"}]
    entries = await _audit_actions(engine)
    assert [entry.action for entry in entries] == ["auth.enforcement_enabled"]
    assert entries[0].user_id is not None
    assert entries[0].device_id is not None


async def test_enable_refused_with_reasons(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app:
        await _admin(app)
        stranger = client_for(app)
        response = await stranger.post(ENABLE)
        after = (await stranger.get(ENFORCEMENT)).json()
        probe = await stranger.get(f"{API}/probe/tournament.read")

    assert response.status_code == 409
    assert response.json()["code"] == "enforcement_blocked"
    assert "nicht gekoppelt" in response.json()["detail"]
    assert after["enforced"] is False
    assert probe.status_code == 200
    assert await _audit_actions(engine) == []


async def test_enable_refused_for_non_admin(make_app: AppFactory) -> None:
    async with make_app() as app:
        admin = await _admin(app)
        cashier = await create_user(admin, "Karl Kasse", "5555", "Kasse")
        tablet = await pair_new_device(app, admin)
        await login(tablet, cashier["id"], "5555")
        response = await tablet.post(ENABLE)

    assert response.status_code == 409
    assert "nicht als Administrator" in response.json()["detail"]


async def test_enable_needs_csrf_header(make_app: AppFactory) -> None:
    async with make_app() as app:
        admin = await _admin(app)
        bare = client_for(app, csrf=False)
        bare.cookies = admin.cookies
        response = await bare.post(ENABLE)

    assert response.status_code == 403


async def test_enable_again_changes_nothing(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app:
        admin = await _admin(app)
        assert (await admin.post(ENABLE)).status_code == 200
        again = await admin.post(ENABLE)

    assert again.status_code == 200
    assert again.json()["enforced"] is True
    assert len(await _audit_actions(engine)) == 1


async def test_enable_while_on_needs_system_manage(make_app: AppFactory) -> None:
    async with make_app() as app:
        admin = await _admin(app)
        cashier = await create_user(admin, "Karl Kasse", "5555", "Kasse")
        tablet = await pair_new_device(app, admin)
        await login(tablet, cashier["id"], "5555")
        assert (await admin.post(ENABLE)).status_code == 200
        response = await tablet.post(ENABLE)

    assert response.status_code == 403


async def test_there_is_no_way_to_switch_off_over_http(make_app: AppFactory) -> None:
    async with make_app() as app:
        admin = await _admin(app)
        await admin.post(ENABLE)
        attempts = [
            await admin.post(f"{ENFORCEMENT}/disable"),
            await admin.delete(ENFORCEMENT),
            await admin.put(ENFORCEMENT, json={"enforced": False}),
            await admin.patch(ENFORCEMENT, json={"enforced": False}),
        ]
        still = (await admin.get(ENFORCEMENT)).json()

    assert all(attempt.status_code in {404, 405} for attempt in attempts)
    assert still["enforced"] is True


async def test_switch_survives_restart(make_app: AppFactory) -> None:
    async with make_app() as app:
        admin = await _admin(app)
        await admin.post(ENABLE)

    async with make_app() as app:
        body = (await client_for(app).get(ENFORCEMENT)).json()
        probe = await client_for(app).get(f"{API}/probe/tournament.read")

    assert body["enforced"] is True
    assert body["source"] == "setting"
    assert probe.status_code == 401


async def test_switch_is_not_read_per_request(make_app: AppFactory, engine: AsyncEngine) -> None:
    """Der Schalter kommt aus dem Speicher: Eine Änderung direkt in der Datenbank wirkt erst,
    wenn der Server ihn neu liest."""
    async with make_app(enforcement_poll_seconds=3600) as app:
        await sql(
            engine,
            "INSERT INTO setting (id, key, value) VALUES (gen_random_uuid(), :key, :value)",
            key=enforcement.SETTING_KEY,
            value='{"enforced": true}',
        )
        before = (await client_for(app).get(ENFORCEMENT)).json()
        assert await enforcement.refresh(app) is True
        after = (await client_for(app).get(ENFORCEMENT)).json()

    assert before["enforced"] is False
    assert after["enforced"] is True


# --- Konsole und laufender Server ---------------------------------------------


@pytest.fixture
def cli_settings(test_database_url: str) -> Settings:
    return Settings(database_url=test_database_url, auth_enforced=False)


async def test_console_off_reaches_running_server(
    make_app: AppFactory, engine: AsyncEngine, cli_settings: Settings
) -> None:
    async with make_app(enforcement_poll_seconds=0.05) as app:
        admin = await _admin(app)
        await admin.post(ENABLE)
        stranger = client_for(app)
        assert (await stranger.get(f"{API}/probe/tournament.read")).status_code == 401
        queue = app.state.events.subscribe()

        out = io.StringIO()
        async with create_session_factory(engine)() as session:
            await cli.enforcement(session, cli_settings, action="off", out=out)

        async def opened() -> bool:
            return (await stranger.get(f"{API}/probe/tournament.read")).status_code == 200

        await _wait_for(opened)
        status = (await stranger.get(f"{API}/auth/status")).json()
        names = [queue.get_nowait() for _ in range(queue.qsize())]

    assert status["auth_enforced"] is False
    assert "ausgeschaltet" in out.getvalue()
    changed = [event.data for event in names if event.name == enforcement.EVENT_CHANGED]
    assert changed == [{"enforced": False, "source": None}]
    entries = await _audit_actions(engine)
    assert [entry.action for entry in entries] == [
        "auth.enforcement_enabled",
        "auth.enforcement_disabled",
    ]
    assert entries[1].details["via"] == service.CONSOLE_VIA
    assert entries[1].user_id is None


async def test_console_on_reaches_running_server(
    make_app: AppFactory, engine: AsyncEngine, cli_settings: Settings
) -> None:
    async with make_app(enforcement_poll_seconds=0.05) as app:
        await _admin(app)
        stranger = client_for(app)
        out = io.StringIO()
        async with create_session_factory(engine)() as session:
            await cli.enforcement(session, cli_settings, action="on", out=out)

        async def closed() -> bool:
            return (await stranger.get(f"{API}/probe/tournament.read")).status_code == 401

        await _wait_for(closed)

    assert "eingeschaltet" in out.getvalue()


async def test_console_on_refuses_without_admin(
    clean_db: None, engine: AsyncEngine, cli_settings: Settings
) -> None:
    async with create_session_factory(engine)() as session:
        await service.seed_roles(session)
        await session.commit()
        with pytest.raises(cli.CliError, match="ensure-admin"):
            await cli.enforcement(session, cli_settings, action="on", out=io.StringIO())
        assert await enforcement.load(session) is False


async def test_console_status_and_env_wins(
    make_app: AppFactory, engine: AsyncEngine, test_database_url: str
) -> None:
    async with make_app() as app:
        admin = await _admin(app)
        await admin.post(ENABLE)

    env_on = Settings(database_url=test_database_url, auth_enforced=True)
    async with create_session_factory(engine)() as session:
        status = io.StringIO()
        await cli.enforcement(session, env_on, action="status", out=status)
        off = io.StringIO()
        await cli.enforcement(session, env_on, action="off", out=off)
        again = io.StringIO()
        await cli.enforcement(session, env_on, action="off", out=again)
        assert await enforcement.load(session) is False

    assert "an" in status.getvalue()
    assert "AUTH_ENFORCED" in status.getvalue()
    assert "AUTH_ENFORCED=true" in off.getvalue()
    assert "neu starten" in off.getvalue()
    assert "bereits aus" in again.getvalue()


async def test_console_status_plain(
    clean_db: None, engine: AsyncEngine, cli_settings: Settings
) -> None:
    async with create_session_factory(engine)() as session:
        out = io.StringIO()
        await cli.enforcement(session, cli_settings, action="status", out=out)

    assert "aus" in out.getvalue()


async def test_console_program(clean_db: None, test_database_url: str) -> None:
    code, stdout, _ = await _run_cli(test_database_url, "enforcement", "status")
    assert code == cli.EXIT_OK
    assert "Berechtigungsprüfung" in stdout

    code, _, stderr = await _run_cli(test_database_url, "enforcement", "on")
    assert code == cli.EXIT_ERROR
    assert "ensure-admin" in stderr

    code, _, _ = await _run_cli(test_database_url, "enforcement", "toggle")
    assert code == cli.EXIT_USAGE


async def test_status_pin_kept_unchanged_by_enable(make_app: AppFactory) -> None:
    """Nach dem Einschalten bleibt die eigene Anmeldung bestehen (niemand sperrt sich aus)."""
    async with make_app() as app:
        admin = await _admin(app)
        await admin.post(ENABLE)
        status = (await admin.get(f"{API}/auth/status")).json()
        users = await admin.get(f"{API}/users")

    assert status["user"] is not None
    assert users.status_code == 200
    assert ADMIN_PIN not in users.text
