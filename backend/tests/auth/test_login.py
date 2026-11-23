"""Anmeldung mit PIN: Auswahl, richtig/falsch, Sperre, Sitzungsablauf, Abmelden, PIN-Reset."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from tests.auth.conftest import (
    ADMIN_PIN,
    API,
    AppFactory,
    client_for,
    create_user,
    login,
    pair_new_device,
    set_time,
    setup_admin,
    sql,
)

WRONG_PIN = "Die Anmeldung ist fehlgeschlagen. Bitte Benutzer und PIN prüfen."


async def test_login_options_need_a_paired_device(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin, client_for(app) as stranger:
        await setup_admin(admin)
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        inactive = await create_user(admin, "Ina Inaktiv", "4711", "Kasse")
        await admin.patch(f"{API}/users/{inactive['id']}", json={"active": False})
        tablet = await pair_new_device(app, admin)
        unpaired = await stranger.get(f"{API}/auth/users")
        options = await tablet.get(f"{API}/auth/users")
        login_unpaired = await login(stranger, kasse["id"], "4711")

    assert unpaired.status_code == 401
    assert "nicht gekoppelt" in unpaired.json()["detail"]
    assert login_unpaired.status_code == 401
    assert options.status_code == 200
    assert options.json() == [
        {"id": options.json()[0]["id"], "name": "Anna Admin"},
        {"id": kasse["id"], "name": "Karl Kasse"},
    ]


async def test_login_with_correct_and_wrong_pin(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        tablet = await pair_new_device(app, admin)
        wrong = await login(tablet, kasse["id"], "0000")
        unknown = await login(tablet, str(uuid.uuid4()), "4711")
        right = await login(tablet, kasse["id"], "4711")
        status = (await tablet.get(f"{API}/auth/status")).json()

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"] == WRONG_PIN
    assert right.status_code == 200
    assert "HttpOnly" in right.headers["set-cookie"]
    assert right.json() == status
    assert status["user"] == {"id": kasse["id"], "name": "Karl Kasse"}
    assert status["role"]["name"] == "Kasse"
    assert "role.manage" not in status["permissions"]


async def test_lockout_after_repeated_failures(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        tablet = await pair_new_device(app, admin)
        failures = [await login(tablet, kasse["id"], "0000") for _ in range(5)]
        while_locked = await login(tablet, kasse["id"], "4711")
        listed = next(
            u for u in (await admin.get(f"{API}/users")).json() if u["name"] == "Karl Kasse"
        )
        await set_time(engine, "user_account", "locked_until", datetime.now(UTC) - timedelta(1))
        after_lock = await login(tablet, kasse["id"], "4711")
        audit = await sql(
            engine, "SELECT action FROM audit_log WHERE entity_id = :id", id=kasse["id"]
        )

    assert [r.status_code for r in failures] == [401, 401, 401, 401, 429]
    assert failures[4].json()["detail"] == (
        "Zu viele Fehlversuche. Die Anmeldung ist für 5 Minuten gesperrt."
    )
    assert int(failures[4].headers["retry-after"]) > 240
    assert while_locked.status_code == 429
    assert listed["locked_until"] is not None
    assert after_lock.status_code == 200
    actions = [row.action for row in audit]
    assert actions.count("auth.login_failed") == 4
    assert actions.count("auth.locked") == 1
    assert "auth.login" in actions


async def test_lockout_limits_are_configurable(make_app: AppFactory) -> None:
    async with make_app(max_failed_logins=2, lockout_minutes=1) as app, client_for(app) as admin:
        await setup_admin(admin)
        own = (await admin.get(f"{API}/auth/status")).json()["user"]["id"]
        first = await login(admin, own, "0000")
        second = await login(admin, own, "0000")

    assert first.status_code == 401
    assert second.status_code == 429
    assert second.json()["detail"].endswith("für 1 Minute gesperrt.")


async def test_session_expires_after_inactivity(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        assert (await admin.get(f"{API}/roles")).status_code == 200
        await set_time(engine, "session", "expires_at", datetime.now(UTC) - timedelta(seconds=1))
        status = (await admin.get(f"{API}/auth/status")).json()
        protected = await admin.get(f"{API}/roles")

    assert status["user"] is None
    assert status["device"]["name"] == "Kasse 1"
    assert protected.status_code == 401
    assert protected.json() == {
        "detail": "Die Anmeldung ist abgelaufen. Bitte erneut mit der PIN anmelden.",
        "code": "session_expired",
    }


async def test_session_is_extended_by_activity(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app(session_idle_hours=2) as app, client_for(app) as admin:
        await setup_admin(admin)
        start = (await sql(engine, "SELECT expires_at FROM session"))[0].expires_at
        await admin.get(f"{API}/auth/status")
        unchanged = (await sql(engine, "SELECT expires_at FROM session"))[0].expires_at
        await set_time(engine, "session", "expires_at", datetime.now(UTC) + timedelta(minutes=5))
        await admin.get(f"{API}/auth/status")
        extended = (await sql(engine, "SELECT expires_at FROM session"))[0].expires_at

    assert timedelta(hours=1, minutes=59) < start - datetime.now(UTC) <= timedelta(hours=2)
    assert unchanged == start
    assert extended - datetime.now(UTC) > timedelta(hours=1, minutes=59)


async def test_logout_ends_the_session(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        response = await admin.post(f"{API}/auth/logout")
        status = (await admin.get(f"{API}/auth/status")).json()
        sessions = await sql(engine, "SELECT id FROM session")

    assert response.status_code == 204
    assert 'schiesshub_session=""' in response.headers["set-cookie"]
    assert status["user"] is None
    assert status["device"] is not None
    assert sessions == []


async def test_relogin_replaces_the_previous_session(
    make_app: AppFactory, engine: AsyncEngine
) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        response = await login(admin, kasse["id"], "4711")
        sessions = await sql(engine, "SELECT user_id FROM session")

    assert response.json()["user"]["name"] == "Karl Kasse"
    assert [str(row.user_id) for row in sessions] == [kasse["id"]]


async def test_pin_reset_unlocks_and_logs_out(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        other = await pair_new_device(app, admin)
        assert (await login(other, kasse["id"], "4711")).status_code == 200
        tablet = await pair_new_device(app, admin)
        for _ in range(5):
            await login(tablet, kasse["id"], "0000")
        assert (await login(tablet, kasse["id"], "4711")).status_code == 429
        reset = await admin.post(f"{API}/users/{kasse['id']}/pin", json={"pin": "8888"})
        other_status = (await other.get(f"{API}/auth/status")).json()
        old_pin = await login(tablet, kasse["id"], "4711")
        new_pin = await login(tablet, kasse["id"], "8888")
        too_short = await admin.post(f"{API}/users/{kasse['id']}/pin", json={"pin": "12"})

    assert reset.status_code == 200
    assert reset.json()["locked_until"] is None
    assert other_status["user"] is None
    assert old_pin.status_code == 401
    assert new_pin.status_code == 200
    assert too_short.status_code == 422


async def test_deactivated_user_cannot_log_in(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        tablet = await pair_new_device(app, admin)
        assert (await login(tablet, kasse["id"], "4711")).status_code == 200
        await admin.patch(f"{API}/users/{kasse['id']}", json={"active": False})
        status = (await tablet.get(f"{API}/auth/status")).json()
        again = await login(tablet, kasse["id"], "4711")

    assert status["user"] is None
    assert again.status_code == 401
    assert again.json()["detail"] == WRONG_PIN


async def test_admin_pin_is_accepted(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        own = (await admin.get(f"{API}/auth/status")).json()["user"]["id"]
        await admin.post(f"{API}/auth/logout")
        response = await login(admin, own, ADMIN_PIN)

    assert response.status_code == 200
    assert response.json()["role"]["name"] == "Administrator"
