"""Notzugang über die Server-Konsole (`python -m app.modules.auth.cli`)."""

import asyncio
import io
import os
import re
import sys
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.db import create_session_factory
from app.core.events import EventHub
from app.modules.auth import cli, credentials, service
from app.modules.auth.identity import now
from app.modules.auth.models import AuditLog, AuthSession, Device, PairingCode, Role, UserAccount
from app.modules.auth.schemas import PairIn
from tests.conftest import BACKEND_DIR

PIN = "4711"


@pytest.fixture
async def session(clean_db: None, engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with create_session_factory(engine)() as session:
        await service.seed_roles(session)
        await session.commit()
        yield session


@pytest.fixture
def settings(test_database_url: str) -> Settings:
    return Settings(database_url=test_database_url)


async def _role(session: AsyncSession, *, system: bool) -> Role:
    statement = select(Role).where(Role.is_system.is_(system)).order_by(Role.name)
    role = (await session.scalars(statement)).first()
    assert role is not None
    return role


async def _user(
    session: AsyncSession, name: str, *, admin: bool = True, active: bool = True
) -> UserAccount:
    user = UserAccount(
        name=name,
        pin_hash=await credentials.hash_pin(PIN),
        role_id=(await _role(session, system=admin)).id,
        active=active,
    )
    session.add(user)
    await session.commit()
    return user


async def _audit(session: AsyncSession) -> list[AuditLog]:
    return list(await session.scalars(select(AuditLog).order_by(AuditLog.created_at)))


def _no_secret(entries: list[AuditLog], *secrets: str) -> None:
    for entry in entries:
        assert entry.details.get("via") == service.CONSOLE_VIA
        assert entry.user_id is None
        assert entry.device_id is None
        for secret in secrets:
            assert secret not in str(entry.details)


# --- pairing-code ------------------------------------------------------------


async def test_pairing_code_without_base_url(session: AsyncSession, settings: Settings) -> None:
    out = io.StringIO()
    code = await cli.pairing_code(session, settings, name="Leitstand", minutes=None, out=out)
    text = out.getvalue()
    assert f"Kopplungscode: {code}" in text
    assert f"/pair?code={code}" in text
    assert "PUBLIC_BASE_URL ist nicht gesetzt" in text

    pairing = await session.scalar(select(PairingCode))
    assert pairing is not None
    assert pairing.name == "Leitstand"
    assert pairing.code_hash == credentials.token_hash(code)
    remaining = pairing.expires_at - now()
    assert timedelta(minutes=9) < remaining <= timedelta(minutes=10)
    entries = await _audit(session)
    assert [entry.action for entry in entries] == ["device.pairing_code_created"]
    _no_secret(entries, code)

    # Der Code koppelt wie einer aus der API, und nur einmal.
    paired = await service.pair(session, EventHub(), PairIn(code=code))
    assert paired.device_token
    assert (await session.scalar(select(Device))).name == "Leitstand"
    with pytest.raises(HTTPException):
        await service.pair(session, EventHub(), PairIn(code=code))


async def test_pairing_code_with_base_urls_and_minutes(
    session: AsyncSession, settings: Settings
) -> None:
    settings = settings.model_copy(
        update={"public_base_url": "https://schiesshub.local/, https://192.168.178.20"}
    )
    out = io.StringIO()
    code = await cli.pairing_code(session, settings, name=None, minutes=60, out=out)
    text = out.getvalue()
    assert f"  https://schiesshub.local/pair?code={code}" in text
    assert f"  https://192.168.178.20/pair?code={code}" in text
    assert "PUBLIC_BASE_URL" not in text
    pairing = await session.scalar(select(PairingCode))
    assert pairing is not None
    assert pairing.expires_at - now() > timedelta(minutes=59)
    assert (await _audit(session))[0].details["minutes"] == 60


@pytest.mark.parametrize("minutes", [0, -5, 24 * 60 + 1])
async def test_pairing_code_rejects_minutes(
    session: AsyncSession, settings: Settings, minutes: float
) -> None:
    with pytest.raises(cli.CliError):
        await cli.pairing_code(session, settings, name=None, minutes=minutes, out=io.StringIO())
    assert await session.scalar(select(PairingCode)) is None


# --- list-users --------------------------------------------------------------


async def test_list_users(session: AsyncSession) -> None:
    await _user(session, "Anna Admin")
    await _user(session, "Bert Kasse", admin=False, active=False)
    locked = await _user(session, "Carla Stand", admin=False)
    locked.locked_until = now() + timedelta(minutes=5)
    await session.commit()

    out = io.StringIO()
    await cli.list_users(session, out=out)
    lines = out.getvalue().splitlines()
    assert lines[0].startswith("Anna Admin")
    assert "Administrator" in lines[0]
    assert "aktiv" in lines[0]
    assert "gesperrt" not in lines[0]
    assert "inaktiv" in lines[1]
    assert "gesperrt bis" in lines[2]
    assert "keinen aktiven Administrator" not in out.getvalue()
    assert "argon2" not in out.getvalue()
    entries = await _audit(session)
    assert [entry.action for entry in entries] == ["user.listed"]
    _no_secret(entries)


async def test_list_users_warns_without_admin(session: AsyncSession) -> None:
    await _user(session, "Anna Admin", active=False)
    out = io.StringIO()
    await cli.list_users(session, out=out)
    assert "keinen aktiven Administrator" in out.getvalue()


# --- reset-pin ---------------------------------------------------------------


async def test_reset_pin_random_unlocks_and_ends_sessions(
    session: AsyncSession, settings: Settings
) -> None:
    user = await _user(session, "Anna Admin")
    user.locked_until = now() + timedelta(minutes=5)
    user.failed_login_count = 3
    device = Device(name="Kasse", token_hash="x" * 64, paired_at=now())
    session.add(device)
    await session.flush()
    session.add(
        AuthSession(
            device_id=device.id,
            user_id=user.id,
            token_hash="y" * 64,
            expires_at=now() + timedelta(hours=1),
        )
    )
    await session.commit()

    out = io.StringIO()
    await cli.reset_pin(session, settings, who="anna admin", pin=None, out=out)
    pin = re.search(r"Neue PIN: (\d+)", out.getvalue())
    assert pin is not None
    assert len(pin.group(1)) >= 6
    await session.refresh(user)
    assert await credentials.verify_pin(user.pin_hash, pin.group(1))
    assert user.locked_until is None
    assert user.failed_login_count == 0
    assert await session.scalar(select(AuthSession)) is None
    entries = await _audit(session)
    assert [entry.action for entry in entries] == ["user.pin_reset"]
    _no_secret(entries, pin.group(1))


async def test_reset_pin_by_id_with_given_pin(session: AsyncSession, settings: Settings) -> None:
    user = await _user(session, "Anna Admin")
    out = io.StringIO()
    await cli.reset_pin(session, settings, who=str(user.id), pin="98765", out=out)
    assert "Neue PIN" not in out.getvalue()
    await session.refresh(user)
    assert await credentials.verify_pin(user.pin_hash, "98765")


async def test_reset_pin_rules(session: AsyncSession, settings: Settings) -> None:
    await _user(session, "Anna Admin")
    with pytest.raises(HTTPException, match="mindestens 4 Ziffern"):
        await cli.reset_pin(session, settings, who="Anna Admin", pin="12", out=io.StringIO())
    with pytest.raises(HTTPException, match="gibt es nicht"):
        await cli.reset_pin(session, settings, who="Niemand", pin=None, out=io.StringIO())
    longer = settings.model_copy(update={"auth_pin_min_length": 8})
    out = io.StringIO()
    await cli.reset_pin(session, longer, who="Anna Admin", pin=None, out=out)
    pin = re.search(r"Neue PIN: (\d+)", out.getvalue())
    assert pin is not None
    assert len(pin.group(1)) == 8
    assert await _audit(session)
    assert len(await _audit(session)) == 1


# --- ensure-admin ------------------------------------------------------------


async def test_ensure_admin_creates(session: AsyncSession, settings: Settings) -> None:
    out = io.StringIO()
    await cli.ensure_admin(session, settings, name="  Notfall Admin ", pin=None, out=out)
    pin = re.search(r"Neue PIN: (\d+)", out.getvalue())
    assert pin is not None
    user = await session.scalar(select(UserAccount))
    assert user is not None
    assert user.name == "Notfall Admin"
    assert user.active
    assert user.role_id == (await _role(session, system=True)).id
    assert await credentials.verify_pin(user.pin_hash, pin.group(1))
    assert not await service.setup_required(session)
    entries = await _audit(session)
    assert [entry.action for entry in entries] == ["user.created"]
    _no_secret(entries, pin.group(1))


async def test_ensure_admin_reactivates_existing(session: AsyncSession, settings: Settings) -> None:
    user = await _user(session, "Anna Admin", admin=False, active=False)
    user.locked_until = now() + timedelta(minutes=5)
    await session.commit()

    out = io.StringIO()
    await cli.ensure_admin(session, settings, name="anna admin", pin=None, out=out)
    text = out.getvalue()
    assert "Rolle Administrator" in text
    assert "wieder aktiv" in text
    assert "entsperrt" in text
    assert "PIN unverändert" in text
    assert "Neue PIN" not in text
    await session.refresh(user)
    assert user.active
    assert user.locked_until is None
    assert user.role_id == (await _role(session, system=True)).id
    assert await credentials.verify_pin(user.pin_hash, PIN)
    entries = await _audit(session)
    assert [entry.action for entry in entries] == ["user.role_changed"]
    _no_secret(entries)

    await cli.ensure_admin(session, settings, name="Anna Admin", pin="24680", out=io.StringIO())
    await session.refresh(user)
    assert await credentials.verify_pin(user.pin_hash, "24680")
    entries = await _audit(session)
    assert entries[-1].action == "user.updated"
    assert entries[-1].details["pin_reset"] is True
    _no_secret(entries, "24680")


async def test_ensure_admin_rejects_short_pin(session: AsyncSession, settings: Settings) -> None:
    with pytest.raises(HTTPException, match="mindestens"):
        await cli.ensure_admin(session, settings, name="Notfall", pin="1", out=io.StringIO())
    with pytest.raises(cli.CliError):
        await cli.ensure_admin(session, settings, name="   ", pin=None, out=io.StringIO())
    assert await session.scalar(select(UserAccount)) is None
    assert await _audit(session) == []


# --- Aufruf als Programm -----------------------------------------------------


async def _run_cli(database_url: str, *args: str) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.modules.auth.cli",
        *args,
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url, "PUBLIC_BASE_URL": ""},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    assert process.returncode is not None
    return process.returncode, stdout.decode(), stderr.decode()


async def test_program_exit_codes(session: AsyncSession, test_database_url: str) -> None:
    await _user(session, "Anna Admin")

    code, stdout, _ = await _run_cli(test_database_url, "list-users")
    assert code == cli.EXIT_OK
    assert "Anna Admin" in stdout

    code, stdout, _ = await _run_cli(test_database_url, "pairing-code", "--name", "Leitstand")
    assert code == cli.EXIT_OK
    assert re.search(r"/pair\?code=[A-Z0-9]{10}", stdout)

    code, _, stderr = await _run_cli(test_database_url, "reset-pin", "Niemand")
    assert code == cli.EXIT_ERROR
    assert "Fehler: Eine Person „Niemand“ gibt es nicht." in stderr

    code, _, stderr = await _run_cli(test_database_url, "unbekannt")
    assert code == cli.EXIT_USAGE
