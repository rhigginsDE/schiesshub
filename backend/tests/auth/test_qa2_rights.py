"""Befunde aus QA-Durchlauf 2: Rechte-Liste für jedes Gerät, `requires`, Standardrolle ohne
Verwaltungsrechte, 401 mit `code`, Klartexte im Protokoll, Migration 0015."""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.auth import audit, permissions
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

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "20261122_0700_0015_auth_rechte.py"
)


async def device_id_of(client: httpx.AsyncClient) -> str:
    return (await client.get(f"{API}/auth/status")).json()["device"]["id"]


# --- GET /auth/permissions ---------------------------------------------------


async def test_permissions_readable_by_every_paired_device(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Klara Kasse", "4711", "Kasse")
        tablet = await pair_new_device(app, admin)
        without_login = await tablet.get(f"{API}/auth/permissions")
        await login(tablet, kasse["id"], "4711")
        as_kasse = await tablet.get(f"{API}/auth/permissions")
        stranger = await client_for(app).get(f"{API}/auth/permissions")
        await admin.patch(f"{API}/devices/{await device_id_of(tablet)}", json={"blocked": True})
        revoked = await tablet.get(f"{API}/auth/permissions")

    assert without_login.status_code == 200, without_login.text
    assert as_kasse.status_code == 200
    assert as_kasse.json() == without_login.json()
    assert "role.manage" in {item["permission"] for item in as_kasse.json()}
    assert stranger.status_code == 401
    assert stranger.json()["code"] == "device_unknown"
    assert revoked.status_code == 401
    assert revoked.json()["code"] == "device_revoked"


async def test_permissions_carry_requires(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        listed = (await admin.get(f"{API}/auth/permissions")).json()

    by_name = {item["permission"]: item for item in listed}
    assert by_name["start.call"]["requires"] == ["start.read", "tournament.read"]
    assert by_name["result.capture"]["requires"] == ["result.read", "start.read", "tournament.read"]
    assert by_name["start.read"]["requires"] == ["tournament.read"]
    assert by_name["backup.manage"]["requires"] == ["backup.read"]
    assert by_name["tournament.read"]["requires"] == []
    assert by_name["display.read"]["requires"] == []
    for item in listed:
        assert item["permission"] not in item["requires"]
        assert set(item["requires"]) <= set(by_name), item


def test_requires_names_only_real_permissions() -> None:
    """Die Tabelle nennt nur Berechtigungen, die es gibt (sobald ihr Bereich existiert)."""
    known = {item.permission for item in permissions.known_permissions()}
    areas = {permission.split(".")[0] for permission in known}
    for permission, needed in permissions.REQUIRES.items():
        for entry in (permission, *needed):
            if entry.split(".")[0] in areas:
                assert entry in known, f"{permission}: {entry} gibt es nicht"


# --- Standardrolle eines Geräts ------------------------------------------------


async def test_role_with_administration_rights_refused_as_device_default(
    make_app: AppFactory,
) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        tablet = await pair_new_device(app, admin)
        device = await device_id_of(tablet)
        refused = {}
        for name, entries in {
            "Hilfskraft Sicherung": ["backup.*"],
            "Gerätewart": ["device.manage", "start.read"],
            "Alles": ["*"],
        }.items():
            created = await admin.post(f"{API}/roles", json={"name": name, "permissions": entries})
            assert created.status_code == 201, created.text
            refused[name] = await admin.patch(
                f"{API}/devices/{device}", json={"default_role_id": created.json()["id"]}
            )
        administrator = await role_id(admin, "Administrator")
        refused["Administrator"] = await admin.patch(
            f"{API}/devices/{device}", json={"default_role_id": administrator}
        )
        code = await admin.post(
            f"{API}/devices/pairing-codes", json={"name": "TV", "default_role_id": administrator}
        )
        turnierleitung = await admin.patch(
            f"{API}/devices/{device}",
            json={"default_role_id": await role_id(admin, "Turnierleitung")},
        )
        devices = (await admin.get(f"{API}/devices")).json()

    for name, response in refused.items():
        assert response.status_code == 422, name
        body = response.json()
        assert body["errors"][0]["field"] == "default_role_id"
        assert f"„{name}“ enthält Verwaltungsrechte" in body["detail"]
    assert code.status_code == 422
    assert code.json()["errors"][0]["field"] == "default_role_id"
    # Turnierleitung liest die Sicherung nur (`backup.read`) und darf ohne PIN gelten.
    assert turnierleitung.status_code == 200, turnierleitung.text
    tablet_row = next(item for item in devices if item["id"] == device)
    assert tablet_row["default_role_id"] == turnierleitung.json()["default_role_id"]


async def test_device_with_administration_default_role_gets_no_rights(
    make_app: AppFactory, engine: AsyncEngine
) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        tablet = await pair_new_device(app, admin)
        device = await device_id_of(tablet)
        # So eingestellt, bevor es die Prüfung gab: wird nicht geändert, gilt aber nicht.
        await sql(
            engine,
            "UPDATE device SET default_role_id = (SELECT id FROM role WHERE is_system) "
            "WHERE id = :id",
            id=device,
        )
        status = (await tablet.get(f"{API}/auth/status")).json()
        probe = await tablet.get(f"{API}/probe/tournament.read")
        roles = await tablet.get(f"{API}/roles")
        stored = await sql(engine, "SELECT default_role_id FROM device WHERE id = :id", id=device)

    assert status["device"]["id"] == device
    assert status["role"] is None
    assert status["permissions"] == []
    assert probe.status_code == roles.status_code == 401
    assert probe.json()["code"] == "login_required"
    assert stored[0].default_role_id is not None


# --- 401 mit code ------------------------------------------------------------


async def test_unauthorized_responses_carry_code(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Klara Kasse", "4711", "Kasse")
        tablet = await pair_new_device(app, admin)
        never_logged_in = await tablet.get(f"{API}/probe/tournament.read")
        wrong_pin = await login(tablet, kasse["id"], "0000")
        await login(tablet, kasse["id"], "4711")
        await sql(
            engine,
            "UPDATE session SET expires_at = :value WHERE user_id = :user",
            value=datetime.now(UTC) - timedelta(minutes=1),
            user=kasse["id"],
        )
        expired = await tablet.get(f"{API}/probe/tournament.read")
        stranger = client_for(app)
        unknown = await stranger.get(f"{API}/probe/tournament.read")
        unknown_users = await stranger.get(f"{API}/auth/users")
        await admin.patch(f"{API}/devices/{await device_id_of(tablet)}", json={"blocked": True})
        revoked = await tablet.get(f"{API}/probe/tournament.read")
        revoked_users = await tablet.get(f"{API}/auth/users")
        revoked_login = await login(tablet, kasse["id"], "4711")
        revoked_status = (await tablet.get(f"{API}/auth/status")).json()
        unknown_status = (await stranger.get(f"{API}/auth/status")).json()

    def code(response: httpx.Response) -> str:
        assert response.status_code == 401, response.text
        return response.json()["code"]

    assert code(never_logged_in) == "login_required"
    assert code(wrong_pin) == "login_failed"
    assert code(expired) == "session_expired"
    assert expired.json()["detail"] == (
        "Die Anmeldung ist abgelaufen. Bitte erneut mit der PIN anmelden."
    )
    assert code(unknown) == code(unknown_users) == "device_unknown"
    assert code(revoked) == code(revoked_users) == code(revoked_login) == "device_revoked"
    assert revoked.json()["detail"].startswith("Dieses Gerät wurde gesperrt.")
    assert revoked_status["device"] is None
    assert revoked_status["device_revoked"] is True
    assert unknown_status["device_revoked"] is False


async def test_unblocked_device_works_again(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        display = await role_id(admin, "Anzeige")
        tv = await pair_new_device(app, admin, default_role_id=display)
        device = await device_id_of(tv)
        await admin.patch(f"{API}/devices/{device}", json={"blocked": True})
        blocked = await tv.get(f"{API}/probe/display.read")
        await admin.patch(f"{API}/devices/{device}", json={"blocked": False})
        again = await tv.get(f"{API}/probe/display.read")

    assert blocked.json()["code"] == "device_revoked"
    assert again.status_code == 200


# --- Protokoll ---------------------------------------------------------------


def test_action_texts_for_display_and_console() -> None:
    assert audit.action_text("user.listed") == "Personen mit Zugang aufgelistet"
    assert audit.action_text("display.device_assigned") == "Gerät einer Anzeige zugewiesen"
    assert audit.action_text("role.migrated").startswith("Rechte einer Rolle")
    for action in (
        "display.created",
        "display.updated",
        "display.config_changed",
        "display.scenes_reordered",
        "display.device_released",
        "display.deleted",
    ):
        assert audit.action_text(action) != action


# --- Migration 0015 ----------------------------------------------------------


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0015", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROLES = {
    # name: (is_system, starter_key, permissions)
    "Administrator": (True, "Administrator", ["*"]),
    "Standaufsicht": (False, None, ["start.call", "start.read", "tournament.read"]),
    "Auswertung": (False, "Auswertung", ["result.read", "start.call", "start.read"]),
    "Leitung": (False, "Turnierleitung", ["start.*", "tournament.*"]),
    "Kasse": (False, "Kasse", ["entry.*", "start.edit"]),
    "Hallenanzeige": (
        False,
        "Anzeige",
        ["tournament.read", "display.read", "result.read", "start.read"],
    ),
    "Anzeige mit Export": (
        False,
        "Anzeige",
        ["display.read", "start.read", "result.read", "tournament.read", "export.read"],
    ),
    "Eigene Anzeige": (
        False,
        None,
        ["display.read", "start.read", "result.read", "tournament.read"],
    ),
}


async def test_migration_0015(clean_db: None, engine: AsyncEngine) -> None:
    for name, (is_system, starter_key, entries) in ROLES.items():
        await sql(
            engine,
            "INSERT INTO role (id, name, permissions, is_system, starter_key, customized) "
            "VALUES (gen_random_uuid(), :name, CAST(:permissions AS jsonb), :is_system, "
            ":starter_key, true)",
            name=name,
            permissions=json.dumps(entries),
            is_system=is_system,
            starter_key=starter_key,
        )
    migration = load_migration()

    async def run(*, downgrade: bool = False) -> tuple[int, dict[str, list[str]]]:
        async with engine.begin() as connection:
            changed = await connection.run_sync(
                lambda sync: migration.migrate_roles(sync, downgrade=downgrade)
            )
        rows = await sql(engine, "SELECT name, permissions FROM role")
        return changed, {row.name: row.permissions for row in rows}

    changed, upgraded = await run()
    again, unchanged = await run()
    audit_rows = await sql(
        engine, "SELECT entity_id, details FROM audit_log WHERE action = 'role.migrated'"
    )
    _, downgraded = await run(downgrade=True)

    assert upgraded["Standaufsicht"] == [
        "start.call",
        "start.abort",
        "start.read",
        "tournament.read",
    ]
    assert upgraded["Auswertung"] == ["result.read", "start.call", "start.abort", "start.read"]
    assert upgraded["Hallenanzeige"] == ["display.read"]
    for name in ("Administrator", "Leitung", "Kasse", "Anzeige mit Export", "Eigene Anzeige"):
        assert upgraded[name] == ROLES[name][2], name
    assert changed == 3
    assert again == 0
    assert unchanged == upgraded
    assert len(audit_rows) == 3
    hall = next(row.details for row in audit_rows if row.details["name"] == "Hallenanzeige")
    assert hall["before"] == ROLES["Hallenanzeige"][2]
    assert hall["after"] == ["display.read"]
    for name in ("Standaufsicht", "Auswertung", "Leitung", "Kasse"):
        assert downgraded[name] == ROLES[name][2], name
    assert set(downgraded["Hallenanzeige"]) == set(ROLES["Hallenanzeige"][2])
