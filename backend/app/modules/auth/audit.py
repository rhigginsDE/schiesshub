"""Audit-Protokoll für Vorgänge außerhalb der Ergebnisse.

Andere Module rufen `record_audit` in derselben Transaktion wie ihre Änderung auf; geschrieben
wird mit deren Commit. In `details` gehören nie PINs, Token oder Codes.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Actor
from app.modules.auth.models import AuditLog


def record_audit(
    session: AsyncSession,
    actor: Actor,
    action: str,
    entity: str,
    entity_id: UUID | str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=actor.user_id,
        device_id=actor.device_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details or {},
    )
    session.add(entry)
    return entry


async def list_audit(session: AsyncSession, limit: int, offset: int) -> tuple[int, list[AuditLog]]:
    total = await session.scalar(select(func.count()).select_from(AuditLog)) or 0
    entries = await session.scalars(
        select(AuditLog)
        .order_by(AuditLog.at.desc(), AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return total, list(entries)
