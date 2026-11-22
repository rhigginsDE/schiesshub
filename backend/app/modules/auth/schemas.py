"""Ein- und Ausgabeformate der Auth-API (Feldnamen englisch)."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.auth.models import NAME_LENGTH

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_LENGTH)
]
# Länge und Ziffern prüft der Service (Mindestlänge ist einstellbar, Meldung auf Deutsch).
Pin = Annotated[str, Field(max_length=64)]


class StrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Status, Ersteinrichtung, Kopplung, Anmeldung ----------------------------


class DeviceBrief(BaseModel):
    id: UUID
    name: str
    default_role_id: UUID | None


class UserBrief(BaseModel):
    id: UUID
    name: str


class RoleBrief(BaseModel):
    id: UUID
    name: str


class StatusOut(BaseModel):
    # Noch kein aktiver Administrator: POST /auth/setup ist möglich.
    setup_required: bool
    # Der echte Prüfer ist aktiv (AUTH_ENFORCED).
    auth_enforced: bool
    device: DeviceBrief | None
    user: UserBrief | None
    # Rolle der angemeldeten Person, sonst die Standardrolle des Geräts.
    role: RoleBrief | None
    permissions: list[str]
    # Für Formulare und Hinweise; nichts davon ist geheim.
    pin_min_length: int
    # Nach so vielen Fehlversuchen in Folge wird eine Person gesperrt …
    max_failed_logins: int
    # … für so viele Minuten.
    lockout_minutes: float


class SetupIn(StrictIn):
    name: Name
    pin: Pin
    device_name: Name


class PairIn(StrictIn):
    code: Annotated[str, Field(min_length=1, max_length=40)]
    # Ohne Angabe gilt der Name aus dem Kopplungscode.
    device_name: Name | None = None


class LoginIn(StrictIn):
    user_id: UUID
    pin: Pin


# --- Geräte ------------------------------------------------------------------


class PairingCodeIn(StrictIn):
    name: Name | None = None
    default_role_id: UUID | None = None


class PairingCodeOut(BaseModel):
    code: str
    # Pfad für den QR-Code; das Frontend setzt Herkunft (Schema, Host, Port) davor.
    pair_path: str
    expires_at: datetime
    name: str | None
    default_role_id: UUID | None


class DeviceOut(BaseModel):
    id: UUID
    name: str
    paired_at: datetime
    last_seen_at: datetime | None
    default_role_id: UUID | None
    blocked: bool
    # Das Gerät, von dem die Anfrage kommt.
    is_current: bool


class DeviceUpdateIn(StrictIn):
    name: Name | None = None
    default_role_id: UUID | None = None
    blocked: bool | None = None


# --- Rollen ------------------------------------------------------------------


PermissionEntry = Annotated[str, Field(min_length=1, max_length=120)]


class RoleIn(StrictIn):
    name: Name
    # Namen (`club.edit`) oder Muster (`person.*`, `*`).
    permissions: list[PermissionEntry] = []


class RoleUpdateIn(StrictIn):
    name: Name | None = None
    permissions: list[PermissionEntry] | None = None


class RoleOut(BaseModel):
    id: UUID
    name: str
    is_system: bool
    # Startrolle, aus der die Rolle entstand (z. B. „Kasse“), sonst null.
    starter_key: str | None
    # Rechte von Hand geändert; sonst gleicht der Server eine Startrolle beim Start an.
    customized: bool
    # Gespeicherte Einträge, wie angelegt.
    permissions: list[str]
    # Bekannte Berechtigungen, die die Rolle tatsächlich gewährt (Muster ausgewertet).
    effective_permissions: list[str]
    user_count: int


class PermissionOut(BaseModel):
    permission: str
    module: str
    module_title: str


# --- Personen ----------------------------------------------------------------


class UserIn(StrictIn):
    name: Name
    pin: Pin
    role_id: UUID


class UserUpdateIn(StrictIn):
    name: Name | None = None
    role_id: UUID | None = None
    active: bool | None = None


class PinResetIn(StrictIn):
    pin: Pin


class UserOut(BaseModel):
    id: UUID
    name: str
    role_id: UUID
    active: bool
    locked_until: datetime | None
    created_at: datetime


# --- Audit -------------------------------------------------------------------


class AuditEntryOut(BaseModel):
    id: UUID
    at: datetime
    user_id: UUID | None
    # Name der Person bzw. des Geräts zum Zeitpunkt der Abfrage; null, wenn gelöscht oder leer.
    user_name: str | None
    device_id: UUID | None
    device_name: str | None
    action: str
    # Lesbarer deutscher Kurztext zur Aktion; unbekannte Aktionen zeigen den technischen Namen.
    action_text: str
    entity: str
    entity_id: str | None
    details: dict[str, Any]


class AuditActionOut(BaseModel):
    action: str
    action_text: str


class AuditPageOut(BaseModel):
    items: list[AuditEntryOut]
    total: int
    limit: int
    offset: int
