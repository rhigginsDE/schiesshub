"""Berechtigungsliste, Wildcard-Zuordnung der Startrollen, Audit-Protokoll, Hashes in der DB."""

import hashlib

import pytest
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncEngine

import app.modules
from app.core.module import ModuleManifest
from app.modules.auth import permissions
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

# Berechtigungen, wie sie andere Module (auch spätere) mitbringen.
FUTURE = ModuleManifest(
    name="zukunft",
    title="Zukünftige Module",
    router=APIRouter(),
    permissions=(
        "tournament.read",
        "tournament.edit",
        "tournament.reopen",
        "person.read",
        "person.edit",
        "person.delete",
        "person.export",
        "club.edit",
        "entry.read",
        "entry.edit",
        "start.read",
        "start.edit",
        "start.call",
        "result.capture",
        "result.read",
        "result.correct",
        "display.read",
        "display.control",
        "export.read",
        "backup.read",
        "backup.manage",
        "role.manage",
        # Gibt es in keinem echten Modul.
        "zukunft.probe",
    ),
)


@pytest.fixture
def future_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.modules, "MODULES", [*app.modules.MODULES, FUTURE])


def role_grants(role: str) -> set[str]:
    return set(permissions.expand(permissions.STARTER_ROLES[role]))


@pytest.fixture
def fixed_catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nur die Berechtigungen aus FUTURE: Die Zuordnung wird unabhängig davon geprüft, welche
    Module es gerade gibt."""
    monkeypatch.setattr(app.modules, "MODULES", [FUTURE])


@pytest.mark.usefixtures("fixed_catalogue")
def test_wildcard_mapping_of_starter_roles() -> None:
    every = set(FUTURE.permissions)

    assert role_grants("Administrator") == every
    assert role_grants("Kasse") == {
        "entry.read",
        "entry.edit",
        "start.read",
        "start.edit",
        "person.read",
        "person.edit",
        "person.delete",
        "person.export",
        "club.edit",
        "tournament.read",
    }
    assert role_grants("Auswertung") == {
        "result.read",
        "result.capture",
        "start.read",
        "start.call",
        "entry.read",
        "tournament.read",
    }
    assert role_grants("Anzeige") == {
        "display.read",
        "start.read",
        "result.read",
        "tournament.read",
    }
    turnier = role_grants("Turnierleitung")
    assert {
        "tournament.reopen",
        "entry.edit",
        "start.call",
        "result.correct",
        "display.control",
        "export.read",
        "backup.read",
    } <= turnier
    assert not turnier & {"backup.manage", "role.manage"}


def test_starter_roles_name_only_real_permissions() -> None:
    """Ein genauer Eintrag (kein Muster) muss existieren, sobald sein Bereich existiert.

    Fängt Tippfehler und veraltete Namen ab (z. B. `entry.create`), bricht aber nicht, wenn ein
    Modul neue Berechtigungen mitbringt oder ein Bereich (noch) fehlt.
    """
    known = {item.permission for item in permissions.known_permissions()}
    areas = {permission.split(".")[0] for permission in known}
    for role, entries in permissions.STARTER_ROLES.items():
        for entry in entries:
            assert permissions.PERMISSION_PATTERN.match(entry), (role, entry)
            if entry == "*" or entry.endswith(".*"):
                continue
            if entry.split(".")[0] in areas:
                assert entry in known, f"{role}: {entry} gibt es nicht"


def test_pattern_matching() -> None:
    assert permissions.grants(["*"], "anything.at_all")
    assert permissions.grants(["result.*"], "result.capture")
    assert not permissions.grants(["result.*"], "results.capture")
    assert not permissions.grants(["result.capture"], "result.correct")
    assert not permissions.grants([], "result.read")


@pytest.mark.usefixtures("future_modules")
async def test_permissions_endpoint_lists_all_modules(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        listed = (await admin.get(f"{API}/auth/permissions")).json()
        roles = {role["name"]: role for role in (await admin.get(f"{API}/roles")).json()}

    names = [item["permission"] for item in listed]
    assert names == sorted(set(names))
    by_name = {item["permission"]: item for item in listed}
    # Führen zwei Module dieselbe Berechtigung, gilt das erste (hier: auth vor zukunft).
    assert by_name["role.manage"] == {
        "permission": "role.manage",
        "module": "auth",
        "module_title": "Anmeldung und Rechte",
    }
    assert by_name["zukunft.probe"]["module"] == "zukunft"
    assert "entry.edit" in roles["Kasse"]["effective_permissions"]
    assert roles["Kasse"]["permissions"] == list(permissions.STARTER_ROLES["Kasse"])
    assert set(roles["Administrator"]["effective_permissions"]) == set(names)


async def test_audit_endpoint(make_app: AppFactory) -> None:
    async with make_app(enforced=True) as app, client_for(app) as admin:
        await setup_admin(admin)
        kasse = await create_user(admin, "Karl Kasse", "4711", "Kasse")
        await admin.post(f"{API}/users/{kasse['id']}/pin", json={"pin": "5555"})
        tablet = await pair_new_device(app, admin)
        await login(tablet, kasse["id"], "5555")
        first_page = await admin.get(f"{API}/audit", params={"limit": 2})
        everything = (await admin.get(f"{API}/audit", params={"limit": 200})).json()
        denied = await tablet.get(f"{API}/audit")
        too_large = await admin.get(f"{API}/audit", params={"limit": 500})

    page = first_page.json()
    assert page["total"] == everything["total"] == len(everything["items"])
    assert page["limit"] == 2
    assert page["offset"] == 0
    assert len(page["items"]) == 2
    actions = [item["action"] for item in everything["items"]]
    assert actions[0] == "auth.login"
    assert {
        "auth.setup",
        "user.created",
        "user.pin_reset",
        "device.pairing_code_created",
        "device.paired",
    } <= set(actions)
    setup = next(item for item in everything["items"] if item["action"] == "auth.setup")
    assert setup["user_id"] is not None
    assert setup["device_id"] is not None
    assert denied.status_code == 403
    assert too_large.status_code == 422


async def test_audit_records_actor_also_without_switch(make_app: AppFactory) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        status = (await admin.get(f"{API}/auth/status")).json()
        await create_user(admin, "Karl Kasse", "4711", "Kasse")
        items = (await admin.get(f"{API}/audit")).json()["items"]

    created = next(item for item in items if item["action"] == "user.created")
    assert created["user_id"] == status["user"]["id"]
    assert created["device_id"] == status["device"]["id"]


async def test_only_hashes_are_stored(make_app: AppFactory, engine: AsyncEngine) -> None:
    async with make_app() as app, client_for(app) as admin:
        await setup_admin(admin)
        code = (await admin.post(f"{API}/devices/pairing-codes", json={"name": "TV"})).json()[
            "code"
        ]
        device_token = admin.cookies["schiesshub_device"]
        session_token = admin.cookies["schiesshub_session"]
        pairing_hashes = [row.code_hash for row in await sql(engine, "SELECT * FROM pairing_code")]
        tablet = await pair_new_device(app, admin)
        tablet_token = tablet.cookies["schiesshub_device"]
        devices = {row.token_hash for row in await sql(engine, "SELECT token_hash FROM device")}
        sessions = {row.token_hash for row in await sql(engine, "SELECT token_hash FROM session")}
        users = await sql(engine, "SELECT pin_hash FROM user_account")
        rows = []
        for table in ("audit_log", "device", "session", "user_account", "pairing_code"):
            rows += await sql(engine, f'SELECT * FROM "{table}"')
        dump = " ".join(str(row) for row in rows)

    def sha(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    assert pairing_hashes == [sha(code)]
    assert devices == {sha(device_token), sha(tablet_token)}
    assert sessions == {sha(session_token)}
    assert users[0].pin_hash.startswith("$argon2id$")
    for secret in (code, device_token, session_token, tablet_token):
        assert secret not in dump
    assert f"'{ADMIN_PIN}'" not in dump
