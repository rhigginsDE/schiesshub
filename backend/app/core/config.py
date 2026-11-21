"""Konfiguration ausschließlich über Umgebungsvariablen."""

from functools import lru_cache
from pathlib import Path

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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # Werte kommen aus der Umgebung
