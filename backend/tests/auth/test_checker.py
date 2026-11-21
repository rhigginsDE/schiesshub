"""Der echte Prüfer: 401/403/ok, CSRF, Geräte mit Standardrolle, offener Prüfer ohne Schalter."""

from tests.auth.conftest import (
    ADMIN_NAME,
    API,
    AppFactory,
    client_for,
    create_user,
    login,
    pair_new_device,
    role_id,
    setup_admin,
)


async def test_without_switch_everything_stays_open(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as stranger:
        probe = await stranger.post(f"{API}/probe/tournament.edit")
        roles = await stranger.get(f"{API}/roles")

    assert probe.status_code == 200
    assert probe.json() == {
        "user_id": None,
        "device_id": None,
        "user_name": None,
        "permissions": [],
    }
    assert roles.status_code == 200


async def test_unpaired_device_gets_401(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app, client_for(app) as stranger:
        probe = await stranger.get(f"{API}/probe/tournament.read")
        roles = await stranger.get(f"{API}/roles")
        status = await stranger.get(f"{API}/auth/status")

    assert probe.status_code == roles.status_code == 401
    assert "nicht gekoppelt" in probe.json()["detail"]
    assert status.status_code == 200
    assert status.json()["auth_enforced"] is True


async def test_paired_device_without_login_gets_401(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        tablet = await pair_new_device(app, admin)
        response = await tablet.get(f"{API}/probe/tournament.read")

    assert response.status_code == 401
    assert response.json()["detail"] == "Bitte zuerst mit der PIN anmelden."


async def test_missing_permission_gets_403_and_granted_returns_actor(
    make_app: AppFactory,
) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        tablet = await pair_new_device(app, admin)
        await login(tablet, kasse["id"], "4711")
        device_id = (await tablet.get(f"{API}/auth/status")).json()["device"]["id"]
        allowed = await tablet.get(f"{API}/probe/tournament.read")
        denied = await tablet.get(f"{API}/probe/tournament.edit")
        roles = await tablet.get(f"{API}/roles")
        admin_probe = await admin.post(f"{API}/probe/result.correct")

    assert allowed.status_code == 200
    actor = allowed.json()
    assert actor["user_id"] == kasse["id"]
    assert actor["device_id"] == device_id
    assert actor["user_name"] == "Karl Kasse"
    assert "tournament.read" in actor["permissions"]
    assert "role.manage" not in actor["permissions"]
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Dafür fehlt die Berechtigung „tournament.edit“."
    assert roles.status_code == 403
    assert admin_probe.status_code == 200
    assert admin_probe.json()["user_name"] == ADMIN_NAME


async def test_checker_requires_csrf_header_for_writes(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        read = await admin.get(f"{API}/probe/tournament.read", headers={"X-Schiesshub-Request": ""})
        write = await admin.post(
            f"{API}/probe/tournament.edit", headers={"X-Schiesshub-Request": ""}
        )

    assert read.status_code == 200
    assert write.status_code == 403
    assert "X-Schiesshub-Request" in write.json()["detail"]


async def test_device_with_default_role_works_without_login(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        display = await role_id(admin, "Anzeige")
        tv = await pair_new_device(app, admin, name="Anzeige", default_role_id=display)
        status = (await tv.get(f"{API}/auth/status")).json()
        allowed = await tv.get(f"{API}/probe/result.read")
        denied = await tv.post(f"{API}/probe/tournament.edit")

    assert status["device"]["default_role_id"] == display
    assert status["user"] is None
    assert status["role"]["name"] == "Anzeige"
    assert allowed.status_code == 200
    assert allowed.json()["user_id"] is None
    assert allowed.json()["device_id"] == status["device"]["id"]
    assert denied.status_code == 403


async def test_blocked_device_gets_401(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        tablet = await pair_new_device(app, admin)
        await login(tablet, kasse["id"], "4711")
        device_id = (await tablet.get(f"{API}/auth/status")).json()["device"]["id"]
        await admin.patch(f"{API}/devices/{device_id}", json={"blocked": True})
        response = await tablet.get(f"{API}/probe/tournament.read")

    assert response.status_code == 401
    assert "gesperrt" in response.json()["detail"]
