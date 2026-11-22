"""Konfiguration ausschließlich über Umgebungsvariablen."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_PREFIX = "/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    environment: str = "development"
    # z. B. postgresql+asyncpg://benutzer:passwort@db:5432/schiesshub – bewusst ohne Standardwert.
    database_url: str
    catalog_dir: Path = Path("/catalog")
    # Erlaubte Browser-Herkünfte, mit Komma getrennt.
    cors_origins: str = "http://localhost:5180"
    sse_heartbeat_seconds: float = Field(default=15.0, gt=0)
    log_level: str = "INFO"
    # Beständige Daten außerhalb der Datenbank: Schlüssel (keys/), lokale Sicherungen (backups/).
    data_dir: Path = Path("/data")
    # Hier ist der Sicherungs-Stick eingehängt. Vorhanden ist er nur mit Marker-Datei.
    backup_usb_dir: Path = Path("/backup-usb")
    backup_usb_marker: str = ".schiesshub-backup"

    # --- Anmeldung und Rechte (Modul `auth`) ---
    # Echten Berechtigungsprüfer registrieren; sonst sind alle Endpunkte offen.
    auth_enforced: bool = False
    # Gültigkeit eines Kopplungscodes.
    auth_pairing_code_minutes: float = Field(default=10, gt=0)
    # Mindestlänge der PIN (nur Ziffern).
    auth_pin_min_length: int = Field(default=4, ge=4, le=12)
    # Nach so vielen Fehlversuchen in Folge wird die Person gesperrt …
    auth_max_failed_logins: int = Field(default=5, ge=1)
    # … für so viele Minuten.
    auth_lockout_minutes: float = Field(default=5, gt=0)
    # Eine Sitzung endet nach so vielen Stunden ohne Anfrage.
    auth_session_idle_hours: float = Field(default=12, gt=0)
    # `auto`: Secure nur, wenn die Anfrage über HTTPS kam (Entwicklung läuft über http://localhost).
    auth_cookie_secure: Literal["auto", "always", "never"] = "auto"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # Werte kommen aus der Umgebung
