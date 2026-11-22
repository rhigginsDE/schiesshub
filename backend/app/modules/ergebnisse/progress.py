"""Erfassungsfortschritt für die Sichten am Stand (Anmeldung bei `starts.hooks`).

Aus `result_current.computed` je Start: der Abschnitt, in dem gerade geschossen wird (der erste
unvollständige, sonst der letzte), wie viele seiner Serien vollständig erfasst sind und ob alle
Rohwerte vollständig sind. Starts ohne Stand oder mit nicht wertbarem Stand fehlen im Ergebnis.
"""

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ergebnisse.models import ResultCurrent
from app.modules.starts.schemas import LaneProgressOut


def progress_of(computed: Mapping[str, Any] | None) -> LaneProgressOut | None:
    """Fortschritt aus einem gespeicherten `computed` (JSON); None, wenn es keins gibt."""
    if not computed:
        return None
    sections = [item for item in computed.get("sections") or [] if isinstance(item, Mapping)]
    complete = bool(computed.get("complete"))
    if not sections:
        return LaneProgressOut(section_id=None, series_done=0, series_total=0, complete=complete)
    current = next((item for item in sections if not item.get("complete")), sections[-1])
    series = [item for item in current.get("series") or [] if isinstance(item, Mapping)]
    return LaneProgressOut(
        section_id=str(current.get("id")) if current.get("id") is not None else None,
        series_done=sum(1 for item in series if item.get("complete")),
        series_total=len(series),
        complete=complete,
    )


async def lane_progress(
    session: AsyncSession, start_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, LaneProgressOut]:
    rows = await session.execute(
        select(ResultCurrent.start_id, ResultCurrent.computed).where(
            ResultCurrent.start_id.in_(start_ids)
        )
    )
    result = {}
    for start_id, computed in rows:
        progress = progress_of(computed)
        if progress is not None:
            result[start_id] = progress
    return result
