"""Ersteinrichtung, Status, Cookies, CSRF-Header und Gerätekopplung."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from tests.auth.conftest import (
    ADMIN_NAME,
    API,
    AppFactory,
    client_for,
    pair_new_device,
    role_id,
    set_time,
    setup_admin,
    sql,
)


async def test_status_before_setup(make_app: AppFactory) -> None:
    async with make_app(pin_min_length=6, max_failed_logins=3) as app, client_for(app) as client:
        response = await client.get(f"{API}/auth/status")

    assert response.status_code == 200
    assert response.json() == {
        "setup_required": True,
        "auth_enforced": False,
        "device": None,
        "user": None,
        "role": None,
        "permissions": [],
        "pin_min_length": 6,
        "max_failed_logins": 3,
        "lockout_minutes": 5.0,
    }


async def test_setup_creates_admin_pairs_device_and_logs_in(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as client:
        response = await setup_admin(client)
        status = (await client.get(f"{API}/auth/status")).json()

    body = response.json()
    assert body == status
    assert status["setup_required"] is False
    assert status["device"]["name"] == "Kasse 1"
    assert status["user"]["name"] == ADMIN_NAME
    assert status["role"]["name"] == "Administrator"
    assert {"role.manage", "user.manage", "device.manage", "system.manage"} <= set(
        status["permissions"]
    )
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    for cookie in cookies:
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        assert "Secure" not in cookie
        assert "Path=/" in cookie


async def test_setup_works_only_once(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as first, client_for(app) as second:
        await setup_admin(first)
        response = await second.post(
            f"{API}/auth/setup", json={"name": "Mallory", "pin": "9999", "device_name": "Fremd"}
        )
        status = (await second.get(f"{API}/auth/status")).json()

    assert response.status_code == 409
    assert response.json()["detail"] == "Die Ersteinrichtung ist bereits abgeschlossen."
    assert status["device"] is None


async def test_setup_validates_pin(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as client:
        letters = await client.post(
            f"{API}/auth/setup", json={"name": "Anna", "pin": "12a4", "device_name": "PC"}
        )
        short = await client.post(
            f"{API}/auth/setup", json={"name": "Anna", "pin": "123", "device_name": "PC"}
        )
        status = (await client.get(f"{API}/auth/status")).json()

    assert letters.status_code == short.status_code == 422
    assert short.json()["detail"] == "Die PIN muss aus mindestens 4 Ziffern bestehen."
    assert status["setup_required"] is True


async def test_pin_min_length_is_configurable(make_app: AppFactory) -> None:
    async with make_app(pin_min_length=6) as app, client_for(app) as client:
        response = await client.post(
            f"{API}/auth/setup", json={"name": "Anna", "pin": "12345", "device_name": "PC"}
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Die PIN muss aus mindestens 6 Ziffern bestehen."


async def test_writes_without_csrf_header_are_rejected(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app, csrf=False) as client:
        response = await client.post(
            f"{API}/auth/setup", json={"name": "Anna", "pin": "1234", "device_name": "PC"}
        )
        status = await client.get(f"{API}/auth/status")

    assert response.status_code == 403
    assert "X-Schiesshub-Request" in response.json()["detail"]
    assert status.status_code == 200
    assert status.json()["setup_required"] is True


async def test_cookies_are_secure_over_https(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app, https=True) as client:
        response = await setup_admin(client)

    assert all("Secure" in cookie for cookie in response.headers.get_list("set-cookie"))


async def test_cookie_secure_can_be_forced(make_app: AppFactory) -> None:
    async with make_app(cookie_secure="always") as app, client_for(app) as client:
        response = await setup_admin(client)

    assert all("Secure" in cookie for cookie in response.headers.get_list("set-cookie"))


async def test_pairing_code_is_single_use(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        created = await admin.post(f"{API}/devices/pairing-codes", json={"name": "Anzeige Halle"})
        code = created.json()["code"]
        async with client_for(app) as tablet, client_for(app) as other:
            # Groß-/Kleinschreibung und Trennzeichen beim Abtippen sind egal.
            paired = await tablet.post(
                f"{API}/auth/pair", json={"code": f"{code[:5].lower()}-{code[5:]}"}
            )
            status = (await tablet.get(f"{API}/auth/status")).json()
            again = await other.post(
                f"{API}/auth/pair", json={"code": code, "device_name": "Zweites Gerät"}
            )
        devices = (await admin.get(f"{API}/devices")).json()

    assert created.status_code == 201
    body = created.json()
    assert body["pair_path"] == f"/pair?code={code}"
    assert len(code) == 10
    assert paired.status_code == 201
    assert status["device"]["name"] == "Anzeige Halle"
    assert status["user"] is None
    assert "HttpOnly" in paired.headers["set-cookie"]
    assert again.status_code == 422
    assert "ungültig, abgelaufen oder wurde schon benutzt" in again.json()["detail"]
    assert sorted(device["name"] for device in devices) == ["Anzeige Halle", "Kasse 1"]
    assert [device["is_current"] for device in devices if device["name"] == "Kasse 1"] == [True]


async def test_pairing_code_expires(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app, client_for(app) as admin, client_for(app) as tablet:
        await setup_admin(admin)
        created = (await admin.post(f"{API}/devices/pairing-codes", json={})).json()
        expires_at = datetime.fromisoformat(created["expires_at"])
        await set_time(engine, "pairing_code", "expires_at", datetime.now(UTC) - timedelta(1))
        response = await tablet.post(
            f"{API}/auth/pair", json={"code": created["code"], "device_name": "Tablet"}
        )

    lifetime = expires_at - datetime.now(UTC)
    assert timedelta(minutes=9) < lifetime <= timedelta(minutes=10)
    assert response.status_code == 422


async def test_pairing_code_lifetime_is_configurable(make_app: AppFactory) -> None:
    async with make_app(pairing_code_minutes=2) as app, client_for(app) as admin:
        await setup_admin(admin)
        created = (await admin.post(f"{API}/devices/pairing-codes", json={})).json()

    lifetime = datetime.fromisoformat(created["expires_at"]) - datetime.now(UTC)
    assert timedelta(minutes=1) < lifetime <= timedelta(minutes=2)


async def test_pairing_needs_a_device_name(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin, client_for(app) as tablet:
        await setup_admin(admin)
        code = (await admin.post(f"{API}/devices/pairing-codes", json={})).json()["code"]
        response = await tablet.post(f"{API}/auth/pair", json={"code": code})

    assert response.status_code == 422
    assert response.json()["detail"] == "Bitte einen Namen für das Gerät angeben."


async def test_device_rename_block_and_delete(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        tablet = await pair_new_device(app, admin)
        device_id = (await tablet.get(f"{API}/auth/status")).json()["device"]["id"]
        renamed = await admin.patch(f"{API}/devices/{device_id}", json={"name": "Stand 2"})
        blocked = await admin.patch(f"{API}/devices/{device_id}", json={"blocked": True})
        blocked_status = (await tablet.get(f"{API}/auth/status")).json()
        users = await tablet.get(f"{API}/auth/users")
        deleted = await admin.delete(f"{API}/devices/{device_id}")
        missing = await admin.delete(f"{API}/devices/{device_id}")
        actions = [row.action for row in await sql(engine, "SELECT action FROM audit_log")]

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Stand 2"
    assert blocked.json()["blocked"] is True
    assert blocked_status["device"] is None
    assert users.status_code == 401
    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Das Gerät gibt es nicht."
    assert {"device.paired", "device.updated", "device.blocked", "device.deleted"} <= set(actions)


async def test_device_default_role_can_be_set_and_cleared(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        display = await role_id(admin, "Anzeige")
        own = (await admin.get(f"{API}/auth/status")).json()["device"]["id"]
        set_role = await admin.patch(f"{API}/devices/{own}", json={"default_role_id": display})
        unknown = await admin.patch(
            f"{API}/devices/{own}", json={"default_role_id": "00000000-0000-0000-0000-000000000000"}
        )
        cleared = await admin.patch(f"{API}/devices/{own}", json={"default_role_id": None})

    assert set_role.json()["default_role_id"] == display
    assert unknown.status_code == 422
    assert cleared.json()["default_role_id"] is None


async def test_last_seen_is_throttled(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        await admin.get(f"{API}/auth/status")
        first = (await sql(engine, "SELECT last_seen_at FROM device"))[0].last_seen_at
        await admin.get(f"{API}/auth/status")
        second = (await sql(engine, "SELECT last_seen_at FROM device"))[0].last_seen_at
        old = datetime.now(UTC) - timedelta(minutes=5)
        await set_time(engine, "device", "last_seen_at", old)
        await admin.get(f"{API}/auth/status")
        third = (await sql(engine, "SELECT last_seen_at FROM device"))[0].last_seen_at

    assert first is not None
    assert second == first
    assert third > old + timedelta(minutes=4)


async def test_events_are_published(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        queue = app.state.events.subscribe()
        await setup_admin(admin)
        await pair_new_device(app, admin)
        names = [queue.get_nowait().name for _ in range(queue.qsize())]

    assert names == ["auth.setup", "device.pairing_code_created", "device.paired"]
