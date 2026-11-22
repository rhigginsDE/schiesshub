"""Tabellen für Geräte, Personen, Rollen, Sitzungen, Kopplungscodes und das Audit-Protokoll.

Geräte-Token, Sitzungs-Token und Kopplungscodes stehen nur als SHA-256-Hash in der Datenbank,
PINs nur als Argon2id-Hash.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

NAME_LENGTH = 80
HASH_LENGTH = 64


class Role(UUIDPrimaryKey, Timestamps, Base):
    """Sammlung von Berechtigungen. Einträge sind Namen (`club.edit`) oder Muster (`person.*`)."""

    __tablename__ = "role"

    name: Mapped[str] = mapped_column(String(NAME_LENGTH), unique=True)
    permissions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Systemrolle (Administrator): nicht löschbar, hat immer alle Rechte.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    # Startrolle, aus der die Rolle entstand (Schlüssel in `permissions.STARTER_ROLES`); leer
    # bei selbst angelegten Rollen. Bleibt beim Umbenennen erhalten.
    starter_key: Mapped[str | None] = mapped_column(String(NAME_LENGTH))
    # Rechte von Hand geändert: Der Abgleich beim Start setzt sie dann nicht mehr zurück.
    customized: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class UserAccount(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "user_account"

    name: Mapped[str] = mapped_column(String(NAME_LENGTH), unique=True)
    pin_hash: Mapped[str] = mapped_column(Text)
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("role.id", ondelete="RESTRICT"), index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Fehlversuche seit der letzten erfolgreichen Anmeldung oder Sperre.
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Device(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "device"

    name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    token_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), unique=True)
    paired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Mit dieser Rolle arbeitet das Gerät, solange niemand angemeldet ist (z. B. die Anzeige).
    default_role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("role.id", ondelete="SET NULL"), index=True
    )
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)


class AuthSession(UUIDPrimaryKey, Timestamps, Base):
    """Anmeldung einer Person an einem Gerät."""

    __tablename__ = "session"

    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), unique=True)
    # Wird bei Aktivität verlängert (gedrosselt).
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PairingCode(UUIDPrimaryKey, Timestamps, Base):
    """Einmaliger, kurzlebiger Code zum Koppeln eines neuen Geräts."""

    __tablename__ = "pairing_code"

    code_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), unique=True)
    # Vorschlag für den Gerätenamen.
    name: Mapped[str | None] = mapped_column(String(NAME_LENGTH))
    default_role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("role.id", ondelete="SET NULL"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(UUIDPrimaryKey, Timestamps, Base):
    """Protokoll für alles außerhalb der Ergebnisse. Ohne Fremdschlüssel, damit es bleibt."""

    __tablename__ = "audit_log"

    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(NAME_LENGTH))
    entity: Mapped[str] = mapped_column(String(NAME_LENGTH))
    entity_id: Mapped[str | None] = mapped_column(String(NAME_LENGTH))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
