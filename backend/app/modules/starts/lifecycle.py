"""Statuswechsel eines Starts – öffentliche Schnittstelle, auch für das Ergebnis-Modul.

Ablauf für ein anderes Modul (z. B. `ergebnisse` beim Erfassen und Abschließen):

    start = await lifecycle.load_start(session, start_id)          # sperrt die Zeile
    change = await lifecycle.transition(session, start, "captured", actor)
    ...  # eigene Zeilen in derselben Transaktion schreiben
    await session.commit()
    lifecycle.publish_status(events, change)                        # erst nach dem Commit

`transition` prüft die Übergangstabelle (`rules.TRANSITIONS`) und das Turnier (nicht
abgeschlossen), committet aber nicht. `registered → captured` ist erlaubt (nachträgliche
Erfassung ohne Aufrufen); bei der Reihenfolge bleibt `lane` dann leer, bei einem Durchgang
bleibt der gebuchte Schützenstand als Angabe stehen – belegt wird er in beiden Fällen nicht.

Belegung des Schützenstands (`start.on_lane`): Der Aufruf (`→ called`) belegt ihn, das Erfassen
(`called → captured`) lässt ihn belegt – der Schütze schießt ja noch. Frei wird er mit
`final`, `aborted`, beim Zurückstellen (`→ registered`) oder über `release_lane`. Ein
Wiederöffnen (`final → captured`) belegt sie nicht wieder. `lane` bleibt als Angabe stehen, wo
geschossen wurde. Ein Start der Reihenfolge, der aufgerufen,
zurückgestellt oder abgebrochen wird, verlässt bzw. betritt die Warteschlange; die Plätze werden
dabei lückenlos neu vergeben.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import EventHub
from app.core.security import Actor
from app.modules.auth.audit import record_audit
from app.modules.starts.common import (
    ConflictError,
    NotFoundError,
    event_ids,
    renumber_queue,
    writable_tournament,
)
from app.modules.starts.models import Entry, Start
from app.modules.starts.rules import (
    REASON_REQUIRED,
    AbortReason,
    RuleError,
    StartStatus,
    check_transition,
)
from app.modules.turnier.models import Competition

EVENT_STATUS_CHANGED = "start.status_changed"

# Mit diesen Wechseln wird der Schützenstand frei (`on_lane`). `captured` lässt ihn, wie er ist.
LANE_RELEASING: frozenset[StartStatus] = frozenset({"registered", "final", "aborted"})


@dataclass(frozen=True, slots=True)
class StatusChange:
    """Ergebnis eines Statuswechsels; Grundlage für das Ereignis nach dem Commit."""

    start_id: uuid.UUID
    entry_id: uuid.UUID
    competition_id: uuid.UUID
    tournament_id: uuid.UUID
    range_id: uuid.UUID | None
    previous: StartStatus
    current: StartStatus


async def load_start(session: AsyncSession, start_id: uuid.UUID, *, lock: bool = True) -> Start:
    """Lädt einen Start, standardmäßig mit Zeilensperre bis zum Ende der Transaktion."""
    query = select(Start).where(Start.id == start_id)
    if lock:
        query = query.with_for_update()
    start = await session.scalar(query)
    if start is None:
        raise NotFoundError("Der Start wurde nicht gefunden.")
    return start


async def transition(
    session: AsyncSession,
    start: Start,
    to: StartStatus,
    actor: Actor,
    *,
    reason: str | None = None,
    abort_reason: AbortReason | None = None,
) -> StatusChange:
    """Wechselt den Status eines Starts, ohne zu committen.

    - `to="aborted"` verlangt `abort_reason` (dns, dnf, dsq).
    - `final → captured` (Wiederöffnen) und `aborted → captured|registered` (Abbruch
      zurücknehmen) verlangen `reason`; er landet im Audit-Protokoll (`start.reopened` bzw.
      `start.abort_undone`). Zurückgenommen wird der Abbruchgrund gelöscht.
    - Für `to="called"` muss `start.lane` gesetzt sein (das erledigen Aufruf-Funktionen).

    Fehler: `ConflictError` (HTTP 409) bei verbotenem Übergang oder abgeschlossenem Turnier.
    """
    entry = await session.get(Entry, start.entry_id)
    competition = await session.get(Competition, start.competition_id)
    # Durch Fremdschlüssel gesichert.
    assert entry is not None
    assert competition is not None
    await writable_tournament(session, entry.tournament_id)
    previous: StartStatus = start.status
    previous_abort = start.abort_reason
    try:
        check_transition(previous, to, abort_reason=abort_reason, reason=reason)
    except RuleError as exc:
        raise ConflictError(str(exc)) from exc
    if to == "called" and start.lane is None:
        raise ConflictError("Zum Aufrufen braucht der Start einen Schützenstand.")

    start.status = to
    start.abort_reason = abort_reason
    if to == "called":
        start.called_at = datetime.now(UTC)
        start.on_lane = True
    elif to == "registered":
        start.called_at = None
    if to in LANE_RELEASING:
        start.on_lane = False
    if to != "registered":
        start.queue_position = None
    elif start.heat_id is None:
        # Zurückgestellt in die Reihenfolge: Der Schützenstand wird beim nächsten Aufruf neu
        # vergeben.
        start.lane = None
    if competition.range_id is not None and competition.planning == "queue":
        await renumber_queue(session, competition.range_id)

    if to == "aborted" or (previous, to) in REASON_REQUIRED:
        if to == "aborted":
            action = "start.aborted"
        elif previous == "aborted":
            action = "start.abort_undone"
        else:
            action = "start.reopened"
        record_audit(
            session,
            actor,
            action,
            "start",
            start.id,
            {
                "tournament_id": str(entry.tournament_id),
                "entry_id": str(entry.id),
                "competition_id": str(competition.id),
                "competition_code": competition.catalog_code,
                "competition_name": competition.name,
                "start_number": entry.start_number,
                "attempt": start.attempt,
                "from": previous,
                "abort_reason": abort_reason or previous_abort,
                "reason": reason,
            },
        )
    return StatusChange(
        start_id=start.id,
        entry_id=entry.id,
        competition_id=competition.id,
        tournament_id=entry.tournament_id,
        range_id=competition.range_id,
        previous=previous,
        current=to,
    )


def publish_status(events: EventHub, change: StatusChange) -> None:
    """Meldet den Wechsel an die Clients. Erst nach dem Commit aufrufen."""
    events.publish(
        EVENT_STATUS_CHANGED,
        {
            **event_ids(
                tournament_id=change.tournament_id,
                entry_id=change.entry_id,
                start_id=change.start_id,
                competition_id=change.competition_id,
                range_id=change.range_id,
            ),
            "from": change.previous,
            "to": change.current,
        },
    )
