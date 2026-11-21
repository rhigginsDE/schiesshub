"""Tabellen der Teilnehmer: Verein und Person (siehe docs/DATENMODELL.md).

Name und Mitgliedsnummer einer Person liegen nur verschlüsselt in der Datenbank. Gesucht wird
über einen Index im Arbeitsspeicher (`index.py`). Es gibt bewusst kein Geburtsdatum und kein
Geburtsjahr.
"""

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedText
from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

DISPLAY_MODES = ("full", "short", "hidden")


class Club(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "club"
    __table_args__ = (
        # Vereinsnamen sind ohne Groß-/Kleinschreibung eindeutig.
        Index("uq_club_name_ci", text("lower(name)"), unique=True),
    )

    name: Mapped[str] = mapped_column(String(200))
    short: Mapped[str | None] = mapped_column(String(40))


class Person(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "person"
    __table_args__ = (
        CheckConstraint(
            "display_mode IN ('full', 'short', 'hidden')",
            name="display_mode",
        ),
    )

    name_enc: Mapped[str] = mapped_column(EncryptedText)
    member_no_enc: Mapped[str | None] = mapped_column(EncryptedText)
    club_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("club.id"), index=True)
    display_mode: Mapped[str] = mapped_column(String(10), default="full")
    show_club: Mapped[bool] = mapped_column(Boolean, default=True)
