"""Einstellungen des Moduls `auth`.

Die Werte kommen aus `app.core.config.Settings` (Umgebungsvariablen `AUTH_…`, dort geprüft und
dokumentiert). `AuthSettings` ist nur die Sicht des Moduls darauf, ohne Präfix; Tests bauen sie
direkt mit einzelnen abweichenden Werten.

Solange `AUTH_ENFORCED` nicht gesetzt ist, bleibt der offene Prüfer aus `app.core.security`
aktiv: Alle Endpunkte mit `require(...)` sind dann ohne Anmeldung erreichbar. Kopplung, Anmeldung
und die Verwaltung funktionieren trotzdem, damit das Frontend sie schon benutzen kann.
"""

from typing import Any, Literal, Self

from fastapi import Request
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings

PREFIX = "auth_"


def _default(name: str) -> Any:
    return Settings.model_fields[f"{PREFIX}{name}"].default


class AuthSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enforced: bool = _default("enforced")
    pairing_code_minutes: float = _default("pairing_code_minutes")
    pin_min_length: int = _default("pin_min_length")
    max_failed_logins: int = _default("max_failed_logins")
    lockout_minutes: float = _default("lockout_minutes")
    session_idle_hours: float = _default("session_idle_hours")
    cookie_secure: Literal["auto", "always", "never"] = _default("cookie_secure")

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(**{name: getattr(settings, f"{PREFIX}{name}") for name in cls.model_fields})


def get_auth_settings(request: Request) -> AuthSettings:
    return request.app.state.auth_settings
