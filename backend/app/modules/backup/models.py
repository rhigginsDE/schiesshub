"""Protokoll der Sicherungsläufe (siehe docs/DATENMODELL.md, Abschnitt System)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

KIND_SNAPSHOT = "snapshot"
KIND_JOURNAL = "journal"
TARGET_LOCAL = "local"
TARGET_USB = "usb"


class BackupRun(UUIDPrimaryKey, Timestamps, Base):
    """Ein Lauf: Abzug lokal, Kopie auf den Stick oder Nachziehen der Mitschrift."""

    __tablename__ = "backup_run"

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(20))
    target: Mapped[str] = mapped_column(String(20))
    # Dateiname im Sicherungsverzeichnis (lokal) bzw. auf dem Stick.
    file_name: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
