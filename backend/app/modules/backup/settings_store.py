"""Globale Einstellungen: Tabelle `setting`, ein JSONB-Wert je Schlüssel, geprüft per Schema.

Bewusst ohne Abhängigkeit zum Sicherungsmodul, damit es sich unverändert nach `app.core`
verschieben lässt. Fehlt ein Schlüssel, gelten die Standardwerte des Schemas; fehlen einzelne
Felder (neue Version), ergänzt das Schema sie ebenso.
"""

from typing import Any

from pydantic import BaseModel
from sqlalchemy import String, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey


class Setting(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)


async def get_setting[M: BaseModel](session: AsyncSession, key: str, schema: type[M]) -> M:
    value = await session.scalar(select(Setting.value).where(Setting.key == key))
    return schema() if value is None else schema.model_validate(value)


async def put_setting(session: AsyncSession, key: str, value: BaseModel) -> None:
    """Legt den Wert an oder ersetzt ihn. Der Aufrufer bestätigt die Transaktion."""
    data = value.model_dump(mode="json")
    statement = insert(Setting).values(key=key, value=data)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[Setting.key], set_={"value": data, "updated_at": func.now()}
        )
    )
