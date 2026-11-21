"""Tabellen des Katalogs.

Die Zeilen werden beim Import per Upsert geschrieben. Was nicht mehr in den Dateien steht, bleibt
mit `active = false` erhalten, damit Turniere weiter darauf verweisen können.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Federation(Base):
    """Verband mit Katalogkopf (katalog.yaml)."""

    __tablename__ = "catalog_federation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    short_name: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(Text)
    rulebook_name: Mapped[str] = mapped_column(Text)
    rulebook_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    # Übrige Angaben des Kopfs: regelwerk (vollständig), hinweise, nicht_enthalten, glossar, …
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Angaben auf Dateiebene der klassen.yaml: quelle, geprueft, stichtag, regeln, unsicher.
    classes_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Group(Base):
    """Disziplingruppe mit Wertung und Abläufen (gruppen/<gruppe>.yaml)."""

    __tablename__ = "catalog_group"
    __table_args__ = (UniqueConstraint("federation_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    federation_id: Mapped[int] = mapped_column(ForeignKey("catalog_federation.id"))
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(Text)
    weapon_type: Mapped[str] = mapped_column(String(20))
    distance_m: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    verified: Mapped[bool] = mapped_column(Boolean)
    # `wertung` der Datei, unverändert.
    scoring: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # `ablaeufe` der Datei: Schlüssel -> {beschreibung, varianten}.
    procedures: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_file: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Discipline(Base):
    __tablename__ = "catalog_discipline"
    __table_args__ = (UniqueConstraint("federation_id", "code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    federation_id: Mapped[int] = mapped_column(ForeignKey("catalog_federation.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("catalog_group.id"), index=True)
    # Kennziffer, immer Text.
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(Text)
    weapon: Mapped[str] = mapped_column(Text)
    ammunition: Mapped[str] = mapped_column(Text)
    sights: Mapped[str] = mapped_column(Text)
    position: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text)
    # Schlüssel in Group.procedures.
    procedure_key: Mapped[str] = mapped_column(String(80))
    optional: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(Text)
    to_check: Mapped[list[str]] = mapped_column(JSONB)
    former_code: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CompetitionClass(Base):
    """Wettbewerbsklasse (klassen.yaml)."""

    __tablename__ = "catalog_class"
    __table_args__ = (UniqueConstraint("federation_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    federation_id: Mapped[int] = mapped_column(ForeignKey("catalog_federation.id"))
    key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str] = mapped_column(String(40))
    gender: Mapped[str] = mapped_column(String(20))
    age_hint: Mapped[str | None] = mapped_column(Text)
    min_starters_dm: Mapped[int | None] = mapped_column(Integer)
    merge_into: Mapped[list[str]] = mapped_column(JSONB)
    merge_by_age: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(Text)
    # Reihenfolge wie in der Datei.
    sort_order: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ImportState(Base):
    """Ergebnis des letzten Importversuchs (genau eine Zeile mit id = 1)."""

    __tablename__ = "catalog_import_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
