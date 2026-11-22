"""Rollenliste für die Personenverwaltung, Abgleich der Startrollen, Audit mit Namen und Filtern."""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.auth import permissions
from app.modules.auth.audit import ACTION_TEXTS
from tests.auth.conftest import (
    API,
    AppFactory,
    client_for,
    create_user,
    login,
    pair_new_device,
    role_id,
    setup_admin,
    sql,
)

# --- GET /roles mit user.manage ----------------------------------------------


async def test_role_list_needs_role_or_user_manage(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        response = await admin.post(
            f"{API}/roles", json={"name": "Personalstelle", "permissions": ["user.manage"]}
        )
        assert response.status_code == 201, response.text
        staff = await create_user(admin, "Paula Personal", "2468", "Personalstelle")
        kasse = await create_user(admin, "Karl Kasse", "1357", "Kasse")
        kasse_role = await role_id(admin, "Kasse")

        tablet = await pair_new_device(app, admin)
        assert (await login(tablet, staff["id"], "2468")).status_code == 200
        listed = await tablet.get(f"{API}/roles")
        single = await tablet.get(f"{API}/roles/{kasse_role}")
        changed = await tablet.patch(f"{API}/roles/{kasse_role}", json={"name": "Kasse 2"})
        created = await tablet.post(f"{API}/roles", json={"name": "Neu"})

        other = await pair_new_device(app, admin)
        assert (await login(other, kasse["id"], "1357")).status_code == 200
        refused = await other.get(f"{API}/roles")

    assert listed.status_code == 200
    assert {"Administrator", "Kasse", "Personalstelle"} <= {r["name"] for r in listed.json()}
    assert all({"id", "name"} <= set(role) for role in listed.json())
    # Nur die Liste; einzelne Rolle lesen und ändern bleibt bei role.manage.
    assert single.status_code == 403
    assert changed.status_code == 403
    assert created.status_code == 403
    assert refused.status_code == 403
    assert "role.manage" in refused.json()["detail"]


# --- Abgleich der Startrollen ---------------------------------------------------


async def test_unchanged_starter_roles_follow_the_current_mapping(
    make_app: AppFactory, engine: AsyncEngine
) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await role_id(admin, "Kasse")
        auswertung = await role_id(admin, "Auswertung")
        await admin.patch(
            f"{API}/roles/{auswertung}", json={"permissions": ["result.read", "entry.create"]}
        )
        own = (
            await admin.post(
                f"{API}/roles",
                json={
                    "name": "Eigene",
                    "permissions": ["entry.cancel", "entry.*", "zukunft.probe"],
                },
            )
        ).json()
    # Alter Stand wie aus einer früheren Version: veraltete Rechte in einer Startrolle.
    stale = ["person.*", "entry.create", "entry.cancel", "start.*", "export.read"]
    await sql(
        engine,
        "UPDATE role SET permissions = CAST(:p AS jsonb) WHERE id = :id",
        p=json.dumps(stale),
        id=kasse,
    )

    async with make_app() as app, client_for(app) as client:
        roles = {role["name"]: role for role in (await client.get(f"{API}/roles")).json()}
        audit = (await client.get(f"{API}/audit", params={"action": "role.*"})).json()["items"]

    # Nie von Hand geändert: zurück auf die aktuelle Zuordnung.
    assert roles["Kasse"]["permissions"] == list(permissions.STARTER_ROLES["Kasse"])
    assert (roles["Kasse"]["starter_key"], roles["Kasse"]["customized"]) == ("Kasse", False)
    # Von Hand geändert: bleibt, nur der veraltete Name fällt weg.
    assert roles["Auswertung"]["permissions"] == ["result.read"]
    assert roles["Auswertung"]["customized"] is True
    # Eigene Rolle: veraltete Namen fallen weg, Muster und Namen ohne Modul bleiben.
    assert roles["Eigene"]["permissions"] == ["entry.*", "zukunft.probe"]
    assert (roles["Eigene"]["starter_key"], roles["Eigene"]["customized"]) == (None, False)
    assert roles["Administrator"]["permissions"] == ["*"]

    by_action = {}
    for item in audit:
        by_action.setdefault(item["action"], []).append(item)
    (reconciled,) = by_action["role.reconciled"]
    assert reconciled["entity_id"] == kasse
    assert reconciled["details"]["before"] == stale
    assert reconciled["user_id"] is None
    removed = {
        item["entity_id"]: item["details"]["removed"]
        for item in by_action["role.permissions_removed"]
    }
    assert removed == {auswertung: ["entry.create"], own["id"]: ["entry.cancel"]}
    assert reconciled["action_text"] == ACTION_TEXTS["role.reconciled"]

    # Dritter Start: nichts mehr zu tun, kein neuer Eintrag.
    async with make_app() as app, client_for(app) as client:
        again = (await client.get(f"{API}/audit", params={"action": "role.*"})).json()
    assert again["total"] == len(audit)


async def test_renamed_starter_role_is_still_reconciled(
    make_app: AppFactory, engine: AsyncEngine
) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        anzeige = await role_id(admin, "Anzeige")
        await admin.patch(f"{API}/roles/{anzeige}", json={"name": "Hallenanzeige"})
    await sql(
        engine,
        "UPDATE role SET permissions = CAST(:p AS jsonb) WHERE id = :id",
        p=json.dumps(["start.read"]),
        id=anzeige,
    )
    async with make_app() as app, client_for(app) as client:
        roles = {role["name"]: role for role in (await client.get(f"{API}/roles")).json()}
    assert roles["Hallenanzeige"]["permissions"] == list(permissions.STARTER_ROLES["Anzeige"])
    assert roles["Hallenanzeige"]["customized"] is False


def test_obsolete_entries() -> None:
    known = ["entry.read", "entry.edit", "start.read", "result.capture"]
    entries = ["entry.create", "entry.*", "*", "display.read", "start.read", "result.cancel"]
    assert permissions.obsolete_entries(entries, known) == ["entry.create", "result.cancel"]


def test_starter_mapping_has_no_obsolete_entries() -> None:
    known = [item.permission for item in permissions.known_permissions()]
    for name, entries in permissions.STARTER_ROLES.items():
        assert permissions.obsolete_entries(entries, known) == [], name


# --- Status ------------------------------------------------------------------


async def test_status_shows_pin_and_lock_parameters(make_app: AppFactory) -> None:
    async with make_app(pin_min_length=5, lockout_minutes=2.5) as app, client_for(app) as client:
        status = (await client.get(f"{API}/auth/status")).json()
    assert status["pin_min_length"] == 5
    assert status["lockout_minutes"] == 2.5
    assert status["max_failed_logins"] == 5


# --- Audit mit Namen und Filtern ---------------------------------------------


async def test_audit_names_texts_and_filters(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        status = (await admin.get(f"{API}/auth/status")).json()
        admin_id, admin_device = status["user"]["id"], status["device"]["id"]
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        tablet = await pair_new_device(app, admin)
        await login(tablet, kasse["id"], "4711")
        tablet_id = (await tablet.get(f"{API}/auth/status")).json()["device"]["id"]
        await tablet.post(f"{API}/auth/logout")

        everything = (await admin.get(f"{API}/audit", params={"limit": 200})).json()["items"]
        by_user = (await admin.get(f"{API}/audit", params={"user_id": kasse["id"]})).json()
        by_device = (await admin.get(f"{API}/audit", params={"device_id": tablet_id})).json()
        by_action = (await admin.get(f"{API}/audit", params={"action": "user.created"})).json()
        by_area = (await admin.get(f"{API}/audit", params={"action": "auth.*"})).json()
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        none_yet = (await admin.get(f"{API}/audit", params={"since": future})).json()
        window = (await admin.get(f"{API}/audit", params={"since": past, "until": future})).json()
        actions = (await admin.get(f"{API}/audit/actions")).json()

        # Gerät und Person gelöscht bzw. umbenannt: Namen zum Zeitpunkt der Abfrage.
        await admin.delete(f"{API}/devices/{tablet_id}")
        await admin.patch(f"{API}/users/{kasse['id']}", json={"name": "Karla Kasse"})
        later = (await admin.get(f"{API}/audit", params={"user_id": kasse["id"]})).json()
        denied = await tablet.get(f"{API}/audit/actions")

    created = next(item for item in everything if item["action"] == "user.created")
    assert (created["user_id"], created["user_name"]) == (admin_id, "Anna Admin")
    assert (created["device_id"], created["device_name"]) == (admin_device, "Kasse 1")
    assert created["action_text"] == "Person mit Zugang angelegt"

    assert {item["action"] for item in by_user["items"]} == {"auth.login", "auth.logout"}
    assert by_user["total"] == 2
    assert {item["device_name"] for item in by_user["items"]} == {"Tablet"}
    assert {"device.paired", "auth.login", "auth.logout"} <= {
        item["action"] for item in by_device["items"]
    }
    assert [item["action"] for item in by_action["items"]] == ["user.created"]
    assert {item["action"] for item in by_area["items"]} == {
        "auth.setup",
        "auth.login",
        "auth.logout",
    }
    assert none_yet["total"] == 0
    assert window["total"] == len(everything)

    assert {(a["action"], a["action_text"]) for a in actions} >= {
        ("auth.login", "Angemeldet"),
        ("role.reconciled", ACTION_TEXTS["role.reconciled"]),
    }

    login_later = next(item for item in later["items"] if item["action"] == "auth.login")
    assert login_later["user_name"] == "Karla Kasse"
    assert login_later["device_name"] is None
    assert denied.status_code == 401


async def test_audit_falls_back_to_technical_name(
    make_app: AppFactory, engine: AsyncEngine
) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        await sql(
            engine,
            "INSERT INTO audit_log (id, at, action, entity, details) "
            "VALUES (gen_random_uuid(), now(), 'zukunft.gemacht', 'x', '{}')",
        )
        items = (await admin.get(f"{API}/audit", params={"action": "zukunft.gemacht"})).json()
        actions = (await admin.get(f"{API}/audit/actions")).json()
    (item,) = items["items"]
    assert item["action_text"] == "zukunft.gemacht"
    assert (item["user_name"], item["device_name"]) == (None, None)
    assert {"action": "zukunft.gemacht", "action_text": "zukunft.gemacht"} in actions
