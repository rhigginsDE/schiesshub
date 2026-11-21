"""Einstellungen des Moduls `auth`, gelesen aus Umgebungsvariablen mit dem Präfix `AUTH_`.

Solange `AUTH_ENFORCED` nicht gesetzt ist, bleibt der offene Prüfer aus `app.core.security`
aktiv: Alle Endpunkte mit `require(...)` sind dann ohne Anmeldung erreichbar. Kopplung, Anmeldung
und die Verwaltung funktionieren trotzdem, damit das Frontend sie schon benutzen kann.
"""

from typing import Literal

from fastapi import Request
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", extra="ignore")

    # Echten Prüfer registrieren (sonst bleibt alles offen).
    enforced: bool = False
    # Gültigkeit eines Kopplungscodes.
    pairing_code_minutes: float = Field(default=10, gt=0)
    # Mindestlänge der PIN (nur Ziffern).
    pin_min_length: int = Field(default=4, ge=4, le=12)
    # Nach so vielen Fehlversuchen in Folge wird die Person gesperrt …
    max_failed_logins: int = Field(default=5, ge=1)
    # … für so viele Minuten.
    lockout_minutes: float = Field(default=5, gt=0)
    # Eine Sitzung endet nach so vielen Stunden ohne Anfrage.
    session_idle_hours: float = Field(default=12, gt=0)
    # `auto`: Secure nur, wenn die Anfrage über HTTPS kam (Entwicklung läuft über http://localhost).
    cookie_secure: Literal["auto", "always", "never"] = "auto"


def get_auth_settings(request: Request) -> AuthSettings:
    return request.app.state.auth_settings
