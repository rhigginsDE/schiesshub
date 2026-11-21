"""Rollen und Personen verwalten, inklusive Schutzregeln für Administratoren."""

from sqlalchemy.ext.asyncio import AsyncEngine

from tests.auth.conftest import (
    API,
    AppFactory,
    client_for,
    create_user,
    pair_new_device,
    role_id,
    setup_admin,
    sql,
)

LAST_ADMIN = "Es muss immer mindestens ein aktiver Administrator bleiben."


async def test_starter_roles_are_created_once(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await role_id(admin, "Kasse")
        await admin.patch(f"{API}/roles/{kasse}", json={"permissions": ["person.read"]})
    # Neustart auf derselben Datenbank: nichts doppelt, Änderungen bleiben.
    async with make_app() as app, client_for(app) as client:
        roles = (await client.get(f"{API}/roles")).json()

    assert [role["name"] for role in roles] == [
        "Administrator",
        "Anzeige",
        "Auswertung",
        "Kasse",
        "Turnierleitung",
    ]
    assert [role["is_system"] for role in roles] == [True, False, False, False, False]
    assert roles[0]["permissions"] == ["*"]
    assert roles[0]["user_count"] == 1
    assert roles[3]["permissions"] == ["person.read"]


async def test_role_crud(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        created = await admin.post(
            f"{API}/roles",
            json={"name": "Standaufsicht", "permissions": ["start.*", "result.read", "start.*"]},
        )
        role = created.json()
        duplicate = await admin.post(f"{API}/roles", json={"name": "standaufsicht"})
        invalid = await admin.post(
            f"{API}/roles", json={"name": "Kaputt", "permissions": ["Start Lesen"]}
        )
        extra = await admin.post(f"{API}/roles", json={"name": "X", "unbekannt": 1})
        fetched = await admin.get(f"{API}/roles/{role['id']}")
        updated = await admin.patch(
            f"{API}/roles/{role['id']}",
            json={"name": "Standaufsicht Halle", "permissions": ["result.read"]},
        )
        deleted = await admin.delete(f"{API}/roles/{role['id']}")
        missing = await admin.get(f"{API}/roles/{role['id']}")
        audit = await sql(engine, "SELECT action, details FROM audit_log WHERE entity = 'role'")

    assert created.status_code == 201
    assert role["permissions"] == ["start.*", "result.read"]
    assert role["is_system"] is False
    assert role["user_count"] == 0
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Eine Rolle mit dem Namen „standaufsicht“ gibt es bereits."
    assert invalid.status_code == 422
    assert "„Start Lesen“ ist keine gültige Berechtigung" in invalid.json()["detail"]
    assert extra.status_code == 422
    assert fetched.json() == role
    assert updated.json()["name"] == "Standaufsicht Halle"
    assert updated.json()["permissions"] == ["result.read"]
    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert [row.action for row in audit] == ["role.created", "role.updated", "role.deleted"]
    assert audit[1].details["permissions"] == {
        "before": ["start.*", "result.read"],
        "after": ["result.read"],
    }


async def test_administrator_role_is_protected(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        admin_role = await role_id(admin, "Administrator")
        restrict = await admin.patch(
            f"{API}/roles/{admin_role}", json={"permissions": ["tournament.read"]}
        )
        rename = await admin.patch(f"{API}/roles/{admin_role}", json={"name": "Chef"})
        remove = await admin.delete(f"{API}/roles/{admin_role}")

    assert restrict.status_code == 409
    assert "hat immer alle Rechte" in restrict.json()["detail"]
    assert rename.status_code == 200
    assert rename.json()["permissions"] == ["*"]
    assert remove.status_code == 409
    assert remove.json()["detail"] == "Die Systemrolle „Chef“ kann nicht gelöscht werden."


async def test_role_in_use_cannot_be_deleted(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await role_id(admin, "Kasse")
        display = await role_id(admin, "Anzeige")
        await create_user(admin, "Karl Kasse", "4711", "Kasse")
        own_device = (await admin.get(f"{API}/auth/status")).json()["device"]["id"]
        await admin.patch(f"{API}/devices/{own_device}", json={"default_role_id": display})
        in_use = await admin.delete(f"{API}/roles/{kasse}")
        display_deleted = await admin.delete(f"{API}/roles/{display}")
        devices = (await admin.get(f"{API}/devices")).json()

    assert in_use.status_code == 409
    assert in_use.json()["detail"] == (
        "Die Rolle „Kasse“ ist noch 1 Person zugewiesen. "
        "Bitte diesen Personen zuerst eine andere Rolle geben."
    )
    assert display_deleted.status_code == 204
    assert devices[0]["default_role_id"] is None


async def test_user_crud(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        duplicate = await admin.post(
            f"{API}/users",
            json={"name": "karl kasse", "pin": "4711", "role_id": kasse["role_id"]},
        )
        bad_role = await admin.post(
            f"{API}/users",
            json={"name": "Neu", "pin": "4711", "role_id": "00000000-0000-0000-0000-000000000000"},
        )
        changed = await admin.patch(
            f"{API}/users/{kasse['id']}",
            json={"name": "Karl K.", "role_id": await role_id(admin, "Auswertung")},
        )
        deactivated = await admin.patch(f"{API}/users/{kasse['id']}", json={"active": False})
        users = (await admin.get(f"{API}/users")).json()
        missing = await admin.patch(
            f"{API}/users/00000000-0000-0000-0000-000000000000", json={"active": False}
        )
        audit = await sql(
            engine, "SELECT action FROM audit_log WHERE entity_id = :id", id=kasse["id"]
        )

    assert set(kasse) == {"id", "name", "role_id", "active", "locked_until", "created_at"}
    assert duplicate.status_code == 409
    assert bad_role.status_code == 422
    assert bad_role.json()["detail"] == "Die angegebene Rolle gibt es nicht."
    assert changed.json()["name"] == "Karl K."
    assert deactivated.json()["active"] is False
    assert [user["name"] for user in users] == ["Anna Admin", "Karl K."]
    assert missing.status_code == 404
    assert [row.action for row in audit] == ["user.created", "user.role_changed", "user.updated"]


async def test_last_active_admin_is_protected(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        own = (await admin.get(f"{API}/auth/status")).json()["user"]["id"]
        kasse_role = await role_id(admin, "Kasse")
        deactivate = await admin.patch(f"{API}/users/{own}", json={"active": False})
        demote = await admin.patch(f"{API}/users/{own}", json={"role_id": kasse_role})
        second = await create_user(admin, "Bernd Backup", "2222", "Administrator")
        demote_ok = await admin.patch(f"{API}/users/{own}", json={"role_id": kasse_role})
        last = await admin.patch(f"{API}/users/{second['id']}", json={"active": False})
        status = (await admin.get(f"{API}/auth/status")).json()

    assert deactivate.status_code == demote.status_code == 409
    assert deactivate.json()["detail"] == LAST_ADMIN
    assert demote_ok.status_code == 200
    assert last.status_code == 409
    assert status["setup_required"] is False
    assert status["role"]["name"] == "Kasse"


async def test_role_change_takes_effect_immediately(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        tablet = await pair_new_device(app, admin)
        await tablet.post(f"{API}/auth/login", json={"user_id": kasse["id"], "pin": "4711"})
        before = await tablet.get(f"{API}/probe/tournament.edit")
        await admin.patch(f"{API}/roles/{kasse['role_id']}", json={"permissions": ["tournament.*"]})
        after = await tablet.get(f"{API}/probe/tournament.edit")

    assert before.status_code == 403
    assert after.status_code == 200
