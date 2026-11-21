"""Ein- und Ausgabeformate der Sicherungs-API."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SETTINGS_KEY = "backup"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BackupSettings(StrictModel):
    """Einstellungen der Sicherung (Tabelle `setting`, Schlüssel `backup`)."""

    enabled: bool = True
    usb_enabled: bool = True
    snapshot_interval_minutes: int = Field(default=5, ge=1, le=24 * 60)
    keep_local: int = Field(default=20, ge=1, le=1000)
    keep_usb: int = Field(default=20, ge=1, le=1000)
    # Wo die Warnung „Stick fehlt“ erscheint.
    warn_all_stations: bool = True
    warn_on_display: bool = False
    # Kopien auf dem Stick verschlüsseln (Sicherungspasswort nötig).
    encrypt: bool = True


class PassphraseIn(StrictModel):
    passphrase: str = Field(min_length=12, max_length=1024)
    # Pflicht, wenn bereits ein Passwort gesetzt ist.
    current_passphrase: str | None = Field(default=None, max_length=1024)


class PassphraseOut(BaseModel):
    passphrase_set: bool
    key_id: str


class InitializeUsbIn(StrictModel):
    # Ausdrückliche Bestätigung: Der Stick wird damit zum Sicherungsziel.
    confirm: Literal[True]


class VerifyIn(StrictModel):
    # Für verschlüsselte Sicherungen nötig; geprüft wird genau der Weg der Wiederherstellung.
    passphrase: str | None = Field(default=None, max_length=1024)


class UsbStatusOut(BaseModel):
    present: bool
    writable: bool
    free_bytes: int | None
    last_seen_at: datetime | None


class RunOut(BaseModel):
    id: UUID
    started_at: datetime
    finished_at: datetime
    kind: Literal["snapshot", "journal"]
    target: Literal["local", "usb"]
    file_name: str | None
    size_bytes: int | None
    sha256: str | None
    ok: bool
    error: str | None


class JournalStatusOut(BaseModel):
    # Zeilen, die noch nicht auf dem Stick bestätigt sind.
    pending: int


class WarningOut(BaseModel):
    code: Literal[
        "backup_disabled",
        "snapshot_failed",
        "usb_missing",
        "usb_not_writable",
        "usb_full",
        "passphrase_missing",
        "usb_copy_failed",
        "journal_sync_failed",
    ]
    message_de: str
    since: datetime


class BackupStatusOut(BaseModel):
    usb: UsbStatusOut
    last_snapshot: RunOut | None
    last_usb_copy: RunOut | None
    journal: JournalStatusOut
    warning: WarningOut | None
    passphrase_set: bool


class VerifyOut(BaseModel):
    ok: bool
    file_name: str
    location: Literal["local", "usb"]
    encrypted: bool
    size_bytes: int
    checksum_ok: bool
    entries: list[str]
    database_toc_entries: int | None
    manifest: dict | None
    error: str | None
