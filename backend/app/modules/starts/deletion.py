"""Löschprüfer für das Turnier-Modul: Was Anmeldungen, Starts oder Durchgänge hat, bleibt."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.starts.models import Entry, Heat, Start
from app.modules.turnier.hooks import DeletionTarget
from app.modules.turnier.models import Competition


def _count(number: int, singular: str, plural: str) -> str:
    return f"{number} {singular if number == 1 else plural}"


async def _scalar(session: AsyncSession, statement: object) -> int:
    return await session.scalar(statement) or 0  # type: ignore[call-overload]


async def turnier_deletion_check(
    session: AsyncSession, target: DeletionTarget, item_id: uuid.UUID
) -> str | None:
    match target:
        case "tournament":
            entries = await _scalar(
                session, select(func.count()).where(Entry.tournament_id == item_id)
            )
            if entries:
                return (
                    f"Das Turnier hat {_count(entries, 'Anmeldung', 'Anmeldungen')} "
                    "und kann nicht gelöscht werden."
                )
        case "class":
            entries = await _scalar(session, select(func.count()).where(Entry.class_id == item_id))
            if entries:
                return (
                    f"Die Klasse hat {_count(entries, 'Anmeldung', 'Anmeldungen')} "
                    "und kann nicht gelöscht werden."
                )
        case "competition":
            starts = await _scalar(
                session, select(func.count()).where(Start.competition_id == item_id)
            )
            if starts:
                return (
                    f"Der Wettbewerb hat {_count(starts, 'Start', 'Starts')} "
                    "und kann nicht gelöscht werden."
                )
        case "range":
            heats = await _scalar(session, select(func.count()).where(Heat.range_id == item_id))
            starts = await _scalar(
                session,
                select(func.count())
                .select_from(Start)
                .join(Competition, Competition.id == Start.competition_id)
                .where(Competition.range_id == item_id),
            )
            parts = []
            if heats:
                parts.append(_count(heats, "Durchgang", "Durchgänge"))
            if starts:
                parts.append(_count(starts, "Start", "Starts"))
            if parts:
                return f"Der Schießstand hat {' und '.join(parts)} und kann nicht gelöscht werden."
    return None
