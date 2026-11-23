"""Rechte der Sicherung: `backup.run`, `backup.restore`, Vorlagen und Migration 0016."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.auth import permissions
from tests.auth.conftest import sql

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "20261122_0800_0016_sicherung_rechte.py"
)


def test_lead_may_run_but_not_set_up_or_restore() -> None:
    lead = permissions.STARTER_ROLES["Turnierleitung"]
    assert permissions.grants(lead, "backup.read")
    assert permissions.grants(lead, "backup.run")
    assert not permissions.grants(lead, "backup.manage")
    assert not permissions.grants(lead, "backup.restore")


def test_restore_only_for_administrator_template() -> None:
    """Kein Muster (`backup.*`, `*`) in einer anderen Vorlage darf `backup.restore` gewähren."""
    for name, entries in permissions.STARTER_ROLES.items():
        granted = permissions.grants(entries, "backup.restore")
        assert granted == (name == permissions.ADMIN_ROLE_NAME), name
    # Verwaltungsrecht: nie Standardrolle eines Geräts ohne PIN.
    assert "backup.restore" in permissions.ADMINISTRATION_PERMISSIONS
    assert "backup.run" not in permissions.ADMINISTRATION_PERMISSIONS


def test_known_permissions_and_requires() -> None:
    known = {item.permission: item for item in permissions.known_permissions()}
    assert known["backup.run"].requires == ("backup.read",)
    assert known["backup.restore"].requires == ("backup.read",)
    assert known["backup.run"].module == "backup"


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0016", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OLD_LEAD = [
    "tournament.*",
    "entry.*",
    "start.*",
    "result.*",
    "person.*",
    "club.edit",
    "export.*",
    "display.*",
    "backup.read",
]
ROLES = {
    # name: (is_system, starter_key, permissions)
    "Administrator": (True, "Administrator", ["*"]),
    "Turnierleitung": (False, "Turnierleitung", OLD_LEAD),
    "Leitung eigen": (False, "Turnierleitung", ["tournament.*", "backup.read"]),
    "Sicherungswart": (False, None, ["backup.read", "backup.manage", "tournament.read"]),
    "Hilfskraft Sicherung": (False, None, ["start.read", "backup.*"]),
    "Kasse": (False, "Kasse", ["entry.*"]),
}


async def test_migration_0016(clean_db: None, engine: AsyncEngine) -> None:
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
    migration = _load_migration()

    async def run(*, downgrade: bool = False) -> tuple[int, dict[str, list[str]]]:
        async with engine.begin() as connection:
            changed = await connection.run_sync(
                lambda sync: migration.migrate_roles(sync, downgrade=downgrade)
            )
        rows = await sql(engine, "SELECT name, permissions FROM role")
        return changed, {row.name: row.permissions for row in rows}

    changed, upgraded = await run()
    again, unchanged = await run()
    audit_rows = await sql(engine, "SELECT details FROM audit_log WHERE action = 'role.migrated'")
    _, downgraded = await run(downgrade=True)

    assert upgraded["Turnierleitung"] == [*OLD_LEAD, "backup.run"]
    assert upgraded["Sicherungswart"] == [
        "backup.read",
        "backup.manage",
        "backup.run",
        "tournament.read",
    ]
    assert upgraded["Hilfskraft Sicherung"] == [
        "start.read",
        "backup.read",
        "backup.manage",
        "backup.run",
    ]
    assert not permissions.grants(upgraded["Hilfskraft Sicherung"], "backup.restore")
    for name in ("Administrator", "Leitung eigen", "Kasse"):
        assert upgraded[name] == ROLES[name][2], name
    assert changed == 3
    assert again == 0
    assert unchanged == upgraded
    assert len(audit_rows) == 3
    assert downgraded["Turnierleitung"] == OLD_LEAD
    assert downgraded["Sicherungswart"] == ROLES["Sicherungswart"][2]
