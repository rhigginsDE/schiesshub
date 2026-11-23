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


class BackupWarningOut(BaseModel):
    """Was jedes gekoppelte Gerät über die Sicherung erfährt: nur die Warnung und wo sie gilt.

    `warning.message_de` ist die allgemeine Fassung ohne Pfade, Dateinamen oder Größen;
    Einzelheiten stehen in `GET /backup/status` (Recht „Sicherung ansehen“).
    """

    warning: WarningOut | None
    warn_all_stations: bool
    warn_on_display: bool


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


# --- Geführte Wiederherstellung ---------------------------------------------------------

RestoreLocation = Literal["usb", "local", "pre_restore"]


class RestoreMessageOut(BaseModel):
    """Hinweis mit fester Kennung: Die Oberfläche unterscheidet an `code` (bleibt gleich), der
    Text `message_de` darf sich ändern. Die Kennungen stehen in `docs/WIEDERHERSTELLUNG.md`."""

    code: str
    message_de: str


class RestoreSourceOut(BaseModel):
    """Eine Sicherung, die sich wiederherstellen lässt.

    Dieselbe Sicherung (gleicher Zeitpunkt im Dateinamen) liegt oft mehrfach: auf dem Server, als
    Kopie auf dem Stick und, wenn sie vor einer Wiederherstellung entstand, unter `pre_restore`.
    Die Liste zeigt sie einmal. `id`, `location` und die Dateiangaben gehören zur bevorzugten
    Quelle: Stick vor Server vor `pre_restore`, weil nur die Stick-Kopie die Schlüssel enthält.
    `locations` nennt alle Orte, `other_ids` die Kennungen der übrigen Kopien (z. B. vom Server
    ohne Sicherungspasswort, wenn es vergessen ist). Jede dieser Kennungen funktioniert in
    Vorschau und Ausführung.
    """

    # Kennung für Vorschau und Ausführung, z. B. `usb:snapshot-20261122T101500123456Z.shb`.
    id: str
    # `usb`: Stick · `local`: Server (`DATA_DIR/backups/snapshots`) · `pre_restore`: automatisch
    # vor einer früheren Wiederherstellung angelegt.
    location: RestoreLocation
    # Alle Orte dieser Sicherung, bevorzugter zuerst (z. B. `["usb", "local"]`).
    locations: list[RestoreLocation] = Field(default_factory=list)
    # Kennungen derselben Sicherung an den anderen Orten, in der Reihenfolge von `locations`.
    other_ids: list[str] = Field(default_factory=list)
    file_name: str
    # Zeitpunkt der Sicherung (UTC), aus dem Dateinamen.
    created_at: datetime
    size_bytes: int
    checksum_present: bool
    encrypted: bool
    # Verschlüsselte Sicherungen brauchen das Sicherungspasswort.
    needs_passphrase: bool
    # Sicherungen vom Stick enthalten das Schlüsselverzeichnis, Abzüge vom Server nicht.
    contains_keys: bool
    # Mitschrift ab dem Tag der Sicherung liegt vor (Server oder Stick).
    journal_available: bool


class RestoreSourcesOut(BaseModel):
    usb_present: bool
    # Neueste zuerst.
    sources: list[RestoreSourceOut]
    restore_running: bool


class RestorePreviewIn(StrictModel):
    source_id: str = Field(min_length=1, max_length=200)
    passphrase: str | None = Field(default=None, max_length=1024)


class RestoreExecuteIn(StrictModel):
    source_id: str = Field(min_length=1, max_length=200)
    passphrase: str | None = Field(default=None, max_length=1024)
    # Ausdrückliche Bestätigung: dieselbe Kennung wie `source_id` (aus der Vorschau `confirm`).
    confirm: str = Field(min_length=1, max_length=200)
    # Ergebnis-Ereignisse aus der Mitschrift nachtragen, die nach der Sicherung entstanden.
    apply_journal: bool = True
    # Pflicht, wenn die Vorschau `you.lockout_risk` meldet.
    accept_lockout: bool = False


class SchemaCheckOut(BaseModel):
    backup: list[str]
    current: list[str]
    # same: passt · older: wird nach dem Einspielen aktualisiert · newer: abgelehnt
    state: Literal["same", "older", "newer"]
    message_de: str


class TournamentPreviewOut(BaseModel):
    id: UUID
    name: str
    status: str
    date_from: str | None
    starts: int
    final_results: int
    result_events: int


class ComparisonOut(BaseModel):
    """Vergleich der Sicherung mit dem jetzigen Stand (Ergebnis-Ereignisse und Starts)."""

    events_now: int
    events_in_backup: int
    # Im jetzigen Stand, aber nicht in der Sicherung.
    events_since_backup: int
    # Davon aus der Mitschrift nachtragbar …
    events_from_journal: int
    # … und verloren, aufgeschlüsselt nach Grund.
    events_lost: int
    lost_start_missing: int
    lost_not_in_journal: int
    lost_conflict: int
    # In der Sicherung, aber nicht mehr im jetzigen Stand (kommen zurück).
    events_only_in_backup: int
    # Insgesamt aus der Mitschrift nachtragbar (auch Ereignisse, die heute fehlen).
    journal_applicable: int
    starts_now: int
    starts_in_backup: int
    starts_since_backup: int
    journal_files: int
    journal_unreadable: list[str]
    summary_de: str


class KeysCheckOut(BaseModel):
    # same: gleich · compatible: Server-Schlüssel enthält alle aus der Sicherung · install: fehlt
    # auf dem Server, wird geschrieben · replace_unused: Server-Schlüssel ist unbenutzt (keine
    # Personen) und wird beiseitegelegt · conflict: abgelehnt · none: Sicherung ohne Schlüssel
    field_keys: Literal["same", "compatible", "install", "replace_unused", "conflict", "none"]
    # keep_current: Das heutige Sicherungspasswort bleibt.
    backup_key: Literal["same", "keep_current", "install", "none"]
    message_de: str


class AccessCheckOut(BaseModel):
    """Was nach der Wiederherstellung mit dem Zugang der auslösenden Person geschieht."""

    enforced_now: bool
    enforced_after: bool
    account_in_backup: bool | None
    account_is_admin_in_backup: bool | None
    device_in_backup: bool | None
    session_in_backup: bool | None
    pin_changed: bool | None
    admins_in_backup: int | None
    lockout_risk: bool
    message_de: str
    # Dieselbe Aussage in Teilen mit Kennung (`message_de` oben = alle Texte hintereinander).
    reasons: list[RestoreMessageOut] = Field(default_factory=list)


class RestorePreviewOut(BaseModel):
    source: RestoreSourceOut
    # Für `POST /backup/restore/execute` als `confirm` zurückschicken.
    confirm: str
    checksum_ok: bool
    created_at: datetime | None
    app_version: str | None
    app_version_current: str
    schema_check: SchemaCheckOut
    tournaments: list[TournamentPreviewOut]
    persons: int | None
    comparison: ComparisonOut
    keys: KeysCheckOut
    access: AccessCheckOut
    restorable: bool
    # Gründe, warum es nicht geht (`restorable` false), und Hinweise – als Text …
    problems: list[str]
    notes: list[str]
    # … und mit Kennung (gleiche Reihenfolge und Texte).
    problem_items: list[RestoreMessageOut] = Field(default_factory=list)
    note_items: list[RestoreMessageOut] = Field(default_factory=list)


RestoreStepKey = Literal[
    "check", "maintenance", "pre_backup", "load", "upgrade", "journal", "verify", "swap", "finish"
]


class RestoreStepOut(BaseModel):
    key: RestoreStepKey
    label_de: str
    state: Literal["pending", "running", "done", "skipped", "failed"]
    detail_de: str | None = None


class SkippedStartOut(BaseModel):
    """Ein Start, dessen seit der Sicherung erfasste Ergebnisse nicht nachgetragen wurden."""

    # Leer, wenn der Wettbewerb in der Sicherung fehlt.
    competition_name: str | None
    competition_code: str | None
    start_number: int | None
    attempt: int | None
    # start_not_in_backup: erst nach der Sicherung gebucht (Person und Start neu anlegen, Ergebnis
    # vom Startzettel erfassen) · does_not_match: passt nicht zum Stand der Sicherung (Start
    # prüfen und Ergebnis von Hand nachtragen)
    reason_code: Literal["start_not_in_backup", "does_not_match"]
    message_de: str


class JournalReportOut(BaseModel):
    applied: int
    present: int
    missing_events: int
    conflicts: int
    status_changes: int
    recomputed_competitions: int
    # Wie die Konsole sie ausgibt.
    lines: list[str]
    # Betroffene Starts, nach Wettbewerb und Startnummer sortiert.
    skipped_starts: list[SkippedStartOut] = Field(default_factory=list)


class RestoreResultOut(BaseModel):
    database: str
    # Die vorherige Datenbank bleibt unter diesem Namen erhalten.
    previous_database: str
    # Sicherung des Stands vor der Wiederherstellung (DATA_DIR/backups/pre-restore).
    pre_restore_backup: str | None
    schema_upgraded: bool
    journal: JournalReportOut | None
    keys_installed: list[str]
    keys_set_aside: list[str]
    after_backup_ok: bool | None
    notes: list[str]
    note_items: list[RestoreMessageOut] = Field(default_factory=list)
    # Wie `journal.skipped_starts` (leer ohne Nachtragen).
    skipped_starts: list[SkippedStartOut] = Field(default_factory=list)


class RestoreStatusOut(BaseModel):
    state: Literal["idle", "running", "succeeded", "failed"]
    step: RestoreStepKey | None
    # 0 … 1, nach erledigten Schritten.
    progress: float
    steps: list[RestoreStepOut]
    source: RestoreSourceOut | None
    started_at: datetime | None
    finished_at: datetime | None
    result: RestoreResultOut | None
    error_de: str | None
    maintenance: bool


class MaintenanceOut(BaseModel):
    active: bool
    exclusive: bool
    message_de: str | None
    since: datetime | None
