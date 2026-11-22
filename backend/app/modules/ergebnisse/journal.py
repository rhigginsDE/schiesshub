"""Mitschrift der Ergebnis-Ereignisse in der Sicherung (`backup.append_journal`).

Geschrieben wird nach dem Commit. Ein Fehler hier lässt die Erfassung nie scheitern: Das
Ereignis steht in der Datenbank und damit im nächsten Abzug; der Fehler wird protokolliert.
Inhalt: IDs, Startnummer, Rohwerte und Grund – keine Namen.
"""

import logging
from typing import Any

from app.modules.backup import append_journal
from app.modules.ergebnisse.models import ResultEvent
from app.modules.starts.models import Entry, Start
from app.modules.turnier.models import Competition

logger = logging.getLogger(__name__)

RECORD_KIND = "result_event"


def event_record(
    event: ResultEvent, start: Start, entry: Entry, competition: Competition
) -> dict[str, Any]:
    def text(value: object) -> str | None:
        return str(value) if value is not None else None

    return {
        "kind": RECORD_KIND,
        "event_id": str(event.id),
        "tournament_id": str(entry.tournament_id),
        "competition_id": str(competition.id),
        "definition_revision": competition.definition_revision,
        "entry_id": str(entry.id),
        "start_id": str(start.id),
        "start_number": entry.start_number,
        "attempt": start.attempt,
        "seq": event.seq,
        "type": event.type,
        "payload": event.payload,
        "reason": event.reason,
        "user_id": text(event.user_id),
        "device_id": text(event.device_id),
        "created_at": event.created_at.isoformat(),
    }


async def write_event(
    event: ResultEvent, start: Start, entry: Entry, competition: Competition
) -> None:
    try:
        await append_journal(event_record(event, start, entry, competition))
    except Exception:
        logger.exception(
            "Ergebnis-Ereignis nicht in die Mitschrift geschrieben (Start %s, Nr. %s)",
            start.id,
            event.seq,
        )
