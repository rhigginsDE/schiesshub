"""Audit-Protokoll für Vorgänge außerhalb der Ergebnisse.

Andere Module rufen `record_audit` in derselben Transaktion wie ihre Änderung auf; geschrieben
wird mit deren Commit. In `details` gehören nie PINs, Token oder Codes.

`ACTION_TEXTS` ordnet den technischen Aktionsnamen einen kurzen deutschen Text zu. Aktionen, die
hier (noch) fehlen, zeigt die Oberfläche mit ihrem technischen Namen.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Actor
from app.modules.auth.models import AuditLog, Device, UserAccount

ACTION_TEXTS: dict[str, str] = {
    # Anmeldung und Rechte
    "auth.setup": "Ersteinrichtung abgeschlossen",
    "auth.login": "Angemeldet",
    "auth.login_failed": "Anmeldung fehlgeschlagen",
    "auth.locked": "Wegen Fehlversuchen gesperrt",
    "auth.logout": "Abgemeldet",
    "device.pairing_code_created": "Kopplungscode erzeugt",
    "device.paired": "Gerät gekoppelt",
    "device.updated": "Gerät geändert",
    "device.blocked": "Gerät gesperrt",
    "device.deleted": "Gerät entfernt",
    "role.created": "Rolle angelegt",
    "role.updated": "Rolle geändert",
    "role.deleted": "Rolle gelöscht",
    "role.reconciled": "Startrolle an aktuelle Rechte angeglichen",
    "role.permissions_removed": "Veraltete Berechtigungen aus Rolle entfernt",
    "user.created": "Person mit Zugang angelegt",
    "user.updated": "Person mit Zugang geändert",
    "user.role_changed": "Rolle einer Person geändert",
    "user.pin_reset": "PIN zurückgesetzt",
    # Turnier
    "competition.definition_changed": "Wertung eines Wettbewerbs geändert",
    # Anmeldung und Starts
    "entry.created": "Anmeldung angelegt",
    "entry.updated": "Anmeldung geändert",
    "entry.deleted": "Anmeldung gelöscht",
    "start.booked": "Starts gebucht",
    "start.cancelled": "Start storniert",
    "start.aborted": "Start abgebrochen",
    "start.reopened": "Abgeschlossenes Ergebnis wieder geöffnet",
    "start.moved": "Reihenfolge am Stand geändert",
    "start.returned": "Start zurückgestellt",
    "start.lane_released": "Bahn freigegeben",
    "start.slot_assigned": "Start einem Durchgang und einer Bahn zugewiesen",
    "start.slot_cleared": "Start aus dem Durchgang genommen",
    "heat.created": "Durchgang angelegt",
    "heat.updated": "Durchgang geändert",
    "heat.deleted": "Durchgang gelöscht",
    # Ergebnisse
    "result.finalized": "Ergebnis abgeschlossen",
    "result.corrected": "Ergebnis korrigiert",
    "result.recomputed": "Ergebnisse neu berechnet",
}


def action_text(action: str) -> str:
    return ACTION_TEXTS.get(action, action)


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


@dataclass(frozen=True, slots=True)
class AuditFilter:
    """Filter der Abfrage. `action` ist ein Name (`role.updated`) oder ein Bereich (`role.*`)."""

    since: datetime | None = None
    until: datetime | None = None
    user_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    action: str | None = None

    def apply[T: tuple[Any, ...]](self, statement: Select[T]) -> Select[T]:
        if self.since is not None:
            statement = statement.where(AuditLog.at >= self.since)
        if self.until is not None:
            statement = statement.where(AuditLog.at < self.until)
        if self.user_id is not None:
            statement = statement.where(AuditLog.user_id == self.user_id)
        if self.device_id is not None:
            statement = statement.where(AuditLog.device_id == self.device_id)
        if self.action:
            if self.action.endswith(".*"):
                prefix = self.action[:-1]
                statement = statement.where(AuditLog.action.startswith(prefix, autoescape=True))
            else:
                statement = statement.where(AuditLog.action == self.action)
        return statement


@dataclass(frozen=True, slots=True)
class AuditRow:
    entry: AuditLog
    user_name: str | None
    device_name: str | None


async def list_audit(
    session: AsyncSession, limit: int, offset: int, filters: AuditFilter | None = None
) -> tuple[int, list[AuditRow]]:
    """Einträge, neueste zuerst, mit den heutigen Namen von Person und Gerät."""
    filters = filters or AuditFilter()
    total = await session.scalar(filters.apply(select(func.count()).select_from(AuditLog))) or 0
    rows = await session.execute(
        filters.apply(
            select(AuditLog, UserAccount.name, Device.name)
            .outerjoin(UserAccount, UserAccount.id == AuditLog.user_id)
            .outerjoin(Device, Device.id == AuditLog.device_id)
        )
        .order_by(AuditLog.at.desc(), AuditLog.created_at.desc(), AuditLog.id)
        .limit(limit)
        .offset(offset)
    )
    return total, [
        AuditRow(entry, user_name, device_name) for entry, user_name, device_name in rows
    ]


async def known_actions(session: AsyncSession) -> list[tuple[str, str]]:
    """Alle Aktionen mit Text: die bekannten und die, die schon im Protokoll stehen."""
    used = set(await session.scalars(select(AuditLog.action).distinct()))
    return sorted((action, action_text(action)) for action in used | set(ACTION_TEXTS))
