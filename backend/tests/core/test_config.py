"""Konfiguration: Auth-Variablen in den zentralen Einstellungen, Einstellungs-Speicher."""

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import Settings
from app.core.settings_store import get_setting, put_setting
from app.modules.auth.settings import AuthSettings

AUTH_VARIABLES = (
    "AUTH_ENFORCED",
    "AUTH_PAIRING_CODE_MINUTES",
    "AUTH_PIN_MIN_LENGTH",
    "AUTH_MAX_FAILED_LOGINS",
    "AUTH_LOCKOUT_MINUTES",
    "AUTH_SESSION_IDLE_HOURS",
    "AUTH_COOKIE_SECURE",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in AUTH_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_auth_defaults(clean_env: pytest.MonkeyPatch) -> None:
    auth = AuthSettings.from_settings(Settings(database_url="postgresql+asyncpg://x/y"))

    assert auth == AuthSettings()
    assert auth.enforced is False
    assert (auth.pin_min_length, auth.max_failed_logins) == (4, 5)
    assert auth.cookie_secure == "auto"


def test_auth_values_come_from_the_environment(clean_env: pytest.MonkeyPatch) -> None:
    values = {
        "AUTH_ENFORCED": "true",
        "AUTH_PAIRING_CODE_MINUTES": "3",
        "AUTH_PIN_MIN_LENGTH": "6",
        "AUTH_MAX_FAILED_LOGINS": "2",
        "AUTH_LOCKOUT_MINUTES": "0.5",
        "AUTH_SESSION_IDLE_HOURS": "8",
        "AUTH_COOKIE_SECURE": "always",
    }
    for name, value in values.items():
        clean_env.setenv(name, value)

    auth = AuthSettings.from_settings(Settings(database_url="postgresql+asyncpg://x/y"))

    assert auth == AuthSettings(
        enforced=True,
        pairing_code_minutes=3,
        pin_min_length=6,
        max_failed_logins=2,
        lockout_minutes=0.5,
        session_idle_hours=8,
        cookie_secure="always",
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AUTH_PIN_MIN_LENGTH", "3"),
        ("AUTH_MAX_FAILED_LOGINS", "0"),
        ("AUTH_COOKIE_SECURE", "manchmal"),
        ("AUTH_SESSION_IDLE_HOURS", "0"),
    ],
)
def test_invalid_auth_values_are_rejected(
    clean_env: pytest.MonkeyPatch, name: str, value: str
) -> None:
    clean_env.setenv(name, value)

    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+asyncpg://x/y")


def test_development_flag() -> None:
    assert Settings(database_url="x", environment="development").is_development
    assert not Settings(database_url="x", environment="production").is_development


class Example(BaseModel):
    count: int = 1
    label: str = "Standard"


async def test_settings_store_roundtrip(engine: AsyncEngine, clean_db: None) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        assert await get_setting(session, "test.example", Example) == Example()
        await put_setting(session, "test.example", Example(count=3))
        await session.commit()
        await put_setting(session, "test.example", Example(count=4, label="Neu"))
        await session.commit()

    async with factory() as session:
        assert await get_setting(session, "test.example", Example) == Example(count=4, label="Neu")
