"""Tabelle `display`: eine öffentliche Anzeige (Fernseher, Bildschirm am Stand).

Was eine Anzeige zeigt, steht in `config` (geprüft nach `schemas.DisplayConfig`). Die Anzeige
selbst wird von niemandem bedient; eingestellt wird sie von den Stationen aus.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey


class Display(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "display"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    # Gezeigtes Turnier; leer heißt „automatisch“: das aktive Turnier, wenn es genau eines gibt.
    # Der Löschprüfer verhindert das Löschen eines fest gewählten Turniers; SET NULL ist nur die
    # Absicherung auf Ebene der Datenbank.
    tournament_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tournament.id", ondelete="SET NULL"), index=True
    )
    # Gekoppeltes Gerät, das diese Anzeige automatisch zeigt (höchstens eine Anzeige je Gerät).
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("device.id", ondelete="SET NULL"), unique=True
    )
    # Vollständig nach schemas.DisplayConfig, inklusive der Standardwerte.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sort: Mapped[int] = mapped_column(Integer)
