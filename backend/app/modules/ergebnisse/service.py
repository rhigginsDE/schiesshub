"""Erfassen, Abschließen, Korrigieren, Wiederöffnen und Abbrechen eines Ergebnisses.

Jeder Vorgang läuft in einer Transaktion:

1. Stand (Bahn-Sperre, dann Start-Sperre) laden; bei einer Wiederholung mit demselben
   `Idempotency-Key` sofort den aktuellen Stand liefern.
2. `base_seq` mit der letzten Sequenznummer vergleichen; weicht sie ab, hat ein anderes Gerät
   inzwischen erfasst (`SeqConflict`, HTTP 409 mit dem aktuellen Stand).
3. Rohwerte mit `app.scoring.validate_raw` prüfen (HTTP 422 mit Pfad und Meldung je Fehler).
4. Ereignis anhängen, `result_current` neu rechnen, Status des Starts über
   `starts.lifecycle.transition` wechseln, bestätigen.
5. Erst danach: Ereignisse an die Clients (`start.status_changed`, `result.<type>`) und der
   Eintrag in der Mitschrift der Sicherung (`journal.write_event`).

Zeitstempel und Sequenznummern vergibt nur der Server.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FieldError, InputError
from app.core.events import EventHub
from app.core.security import Actor
from app.modules.ergebnisse import journal
from app.modules.ergebnisse.models import ResultCurrent, ResultEvent
from app.modules.ergebnisse.rules import Evaluation, evaluate, request_hash, scoring_definition
from app.modules.ergebnisse.schemas import ResultState
from app.modules.starts.common import (
    ConflictError,
    NotFoundError,
    event_ids,
    get_range,
    get_start,
    writable_tournament,
)
from app.modules.starts.lifecycle import StatusChange, publish_status, transition
from app.modules.starts.models import Entry, Start
from app.modules.starts.rules import AbortReason
from app.modules.turnier.models import Competition, Tournament
from app.scoring import DefinitionError, Issue, validate_raw

EVENT_PREFIX = "result."


class SeqConflict(Exception):
    """`base_seq` ist veraltet: Ein anderes Gerät hat inzwischen erfasst."""

    def __init__(self, state: ResultState) -> None:
        super().__init__(
            "Ein anderes Gerät hat diesen Start inzwischen geändert. Bitte den aktuellen Stand "
            "prüfen und die Eingabe gegebenenfalls wiederholen."
        )
        self.state = state


# --- Laden und Darstellen ----------------------------------------------------------


@dataclass(slots=True)
class Loaded:
    start: Start
    entry: Entry
    competition: Competition
    tournament: Tournament
    current: ResultCurrent | None
    changes: list[StatusChange] = field(default_factory=list)

    @property
    def seq(self) -> int:
        return self.current.last_seq if self.current is not None else 0

    @property
    def definition(self) -> dict[str, Any]:
        return scoring_definition(self.competition.definition)


async def load(
    session: AsyncSession, tournament_id: uuid.UUID, start_id: uuid.UUID, *, lock: bool
) -> Loaded:
    """Start mit Anmeldung, Wettbewerb, Turnier und aktuellem Stand.

    Mit `lock` erst der Stand (wie alle Vorgänge an seinen Bahnen), dann der Start gesperrt.
    Ist der Stand mit einer älteren Revision der Definition gerechnet, wird er nachgezogen.
    """
    context = await get_start(session, tournament_id, start_id)
    if lock:
        if context.competition.range_id is not None:
            await get_range(session, tournament_id, context.competition.range_id, lock=True)
        await session.refresh(context.start, with_for_update=True)
    tournament = await session.get(Tournament, tournament_id)
    assert tournament is not None  # get_start hat das Turnier gefunden
    current = await session.get(ResultCurrent, start_id)
    loaded = Loaded(context.start, context.entry, context.competition, tournament, current)
    if (
        current is not None
        and current.definition_revision != context.competition.definition_revision
    ):
        store(
            session,
            loaded,
            current.raw,
            is_final=current.is_final,
            finalized_at=current.finalized_at,
            provisional_until=current.provisional_until,
        )
    return loaded


async def competition_of(
    session: AsyncSession, tournament_id: uuid.UUID, competition_id: uuid.UUID
) -> Competition:
    competition = await session.get(Competition, competition_id)
    if competition is None or competition.tournament_id != tournament_id:
        raise NotFoundError("Der Wettbewerb wurde in diesem Turnier nicht gefunden.")
    return competition


def evaluation_of(loaded: Loaded, raw: dict[str, Any], *, is_final: bool) -> Evaluation:
    return evaluate(loaded.definition, loaded.competition.capture_mode, raw, is_final=is_final)


def is_provisional(current: ResultCurrent | None, now: datetime) -> bool:
    return bool(
        current is not None
        and current.is_final
        and current.provisional_until is not None
        and current.provisional_until > now
    )


def state_of(loaded: Loaded, now: datetime) -> ResultState:
    current = loaded.current
    start = loaded.start
    if current is None:
        # Noch nichts erfasst: Zwischenstand der leeren Rohwerte (alles offen).
        empty = evaluation_of(loaded, {}, is_final=False)
        return ResultState(
            start_id=start.id,
            status=start.status,
            abort_reason=start.abort_reason,
            seq=0,
            raw={},
            computed=empty.computed,
            score=empty.score,
            is_final=False,
            finalized_at=None,
            provisional_until=None,
            is_provisional=False,
            needs_review=False,
            review_reason=None,
            definition_revision=loaded.competition.definition_revision,
        )
    return ResultState(
        start_id=start.id,
        status=start.status,
        abort_reason=start.abort_reason,
        seq=current.last_seq,
        raw=current.raw,
        computed=current.computed,
        score=current.score,
        is_final=current.is_final,
        finalized_at=current.finalized_at,
        provisional_until=current.provisional_until,
        is_provisional=is_provisional(current, now),
        needs_review=current.needs_review,
        review_reason=current.review_reason,
        definition_revision=current.definition_revision,
    )


async def server_now(session: AsyncSession) -> datetime:
    """Zeit der Transaktion; dieselbe, die `created_at` des Ereignisses bekommt."""
    now = await session.scalar(select(func.now()))
    assert now is not None
    return now


def store(
    session: AsyncSession,
    loaded: Loaded,
    raw: dict[str, Any],
    *,
    is_final: bool,
    finalized_at: datetime | None = None,
    provisional_until: datetime | None = None,
    seq: int | None = None,
) -> ResultCurrent:
    """Rechnet und schreibt `result_current` (neu oder aktualisiert), ohne zu bestätigen.

    `seq` ist die Nummer des neuen Ereignisses; ohne sie (Nachziehen nach einer Änderung der
    Definition) bleibt `last_seq` stehen.
    """
    evaluation = evaluation_of(loaded, raw, is_final=is_final)
    current = loaded.current
    if current is None:
        assert seq is not None
        current = ResultCurrent(start_id=loaded.start.id, competition_id=loaded.competition.id)
        session.add(current)
        loaded.current = current
    apply_evaluation(current, evaluation, loaded.competition.definition_revision)
    current.raw = raw
    current.is_final = is_final
    current.finalized_at = finalized_at
    current.provisional_until = provisional_until
    if seq is not None:
        current.last_seq = seq
    return current


def apply_evaluation(current: ResultCurrent, evaluation: Evaluation, revision: int) -> None:
    current.computed = evaluation.computed_json
    current.score = evaluation.score
    current.rank_keys = evaluation.rank_keys
    current.needs_review = evaluation.review_reason is not None
    current.review_reason = evaluation.review_reason
    current.definition_revision = revision


async def get_state(
    session: AsyncSession, tournament_id: uuid.UUID, start_id: uuid.UUID
) -> tuple[Loaded, ResultState]:
    loaded = await load(session, tournament_id, start_id, lock=False)
    state = state_of(loaded, await server_now(session))
    if session.dirty:
        # Stand nach einer Änderung der Definition nachgezogen.
        await session.commit()
    return loaded, state


# --- Bausteine der Vorgänge ------------------------------------------------------------


def raw_issues(issues: list[Issue]) -> InputError:
    return InputError(
        [
            FieldError(field=f"raw.{issue.path}" if issue.path else "raw", message=issue.message)
            for issue in issues
        ]
    )


def check_raw(loaded: Loaded, raw: dict[str, Any], *, partial: bool) -> None:
    try:
        issues = validate_raw(
            loaded.definition, loaded.competition.capture_mode, raw, partial=partial
        )
    except DefinitionError as exc:
        raise ConflictError(
            f"Die Definition des Wettbewerbs lässt sich nicht werten: {exc}. Bitte in der "
            "Turnierleitung prüfen."
        ) from exc
    if issues:
        raise raw_issues(issues)


@dataclass(frozen=True, slots=True)
class Request:
    """Ein schreibender Vorgang, wie er ankam (für Wiederholung und Konfliktprüfung)."""

    action: str
    body: dict[str, Any]
    idempotency_key: str | None
    base_seq: int | None

    @property
    def hash(self) -> str:
        return request_hash(self.action, self.body)


async def begin(
    session: AsyncSession, tournament_id: uuid.UUID, start_id: uuid.UUID, request: Request
) -> tuple[Loaded, bool]:
    """Lädt und sperrt; liefert `(loaded, replay)`. `replay`: schon verarbeitet, nichts tun."""
    loaded = await load(session, tournament_id, start_id, lock=True)
    if request.idempotency_key is not None:
        earlier = await session.scalar(
            select(ResultEvent.request_hash).where(
                ResultEvent.start_id == start_id,
                ResultEvent.idempotency_key == request.idempotency_key,
            )
        )
        if earlier is not None:
            if earlier != request.hash:
                raise InputError.single(
                    None,
                    "Dieser Idempotency-Key wurde für diesen Start schon mit einer anderen "
                    "Eingabe verwendet.",
                )
            return loaded, True
    if request.base_seq is not None and request.base_seq != loaded.seq:
        raise SeqConflict(state_of(loaded, await server_now(session)))
    await writable_tournament(session, tournament_id)
    return loaded, False


def append(
    session: AsyncSession,
    loaded: Loaded,
    request: Request,
    actor: Actor,
    event_type: str,
    payload: dict[str, Any],
    reason: str | None = None,
) -> ResultEvent:
    event = ResultEvent(
        id=uuid.uuid4(),
        start_id=loaded.start.id,
        seq=loaded.seq + 1,
        type=event_type,
        payload=payload,
        reason=reason,
        user_id=actor.user_id,
        device_id=actor.device_id,
        idempotency_key=request.idempotency_key,
        request_hash=request.hash if request.idempotency_key is not None else None,
    )
    session.add(event)
    return event


async def move(
    session: AsyncSession, loaded: Loaded, to: str, actor: Actor, **options: Any
) -> None:
    loaded.changes.append(await transition(session, loaded.start, to, actor, **options))


def provisional_until(loaded: Loaded, now: datetime) -> datetime | None:
    minutes = loaded.tournament.settings.get("protest_minutes")
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        return None
    return now + timedelta(minutes=minutes)


async def finish(
    session: AsyncSession, events: EventHub, loaded: Loaded, event: ResultEvent | None
) -> ResultState:
    """Bestätigt, meldet und schreibt die Mitschrift. `event` None: Wiederholung, nichts neu."""
    if event is None:
        return state_of(loaded, await server_now(session))
    await session.flush()
    now = await server_now(session)
    await session.commit()
    await session.refresh(event)
    state = state_of(loaded, now)
    for change in loaded.changes:
        publish_status(events, change)
    events.publish(
        f"{EVENT_PREFIX}{event.type}",
        {
            **event_ids(
                tournament_id=loaded.tournament.id,
                competition_id=loaded.competition.id,
                entry_id=loaded.entry.id,
                start_id=loaded.start.id,
            ),
            "seq": event.seq,
        },
    )
    await journal.write_event(event, loaded.start, loaded.entry, loaded.competition)
    return state


# --- Vorgänge --------------------------------------------------------------------


async def set_raw(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    raw: dict[str, Any],
    base_seq: int,
    idempotency_key: str | None,
) -> ResultState:
    request = Request("raw_set", {"raw": raw, "base_seq": base_seq}, idempotency_key, base_seq)
    loaded, replay = await begin(session, tournament_id, start_id, request)
    if replay:
        return await finish(session, events, loaded, None)
    status = loaded.start.status
    if status == "final":
        raise ConflictError(
            "Das Ergebnis ist abgeschlossen. Änderungen gehen nur als Korrektur (mit Grund) "
            "oder nach dem Wiederöffnen."
        )
    if status == "aborted":
        raise ConflictError("Der Start ist abgebrochen; Rohwerte lassen sich nicht mehr erfassen.")
    check_raw(loaded, raw, partial=True)

    event = append(session, loaded, request, actor, "raw_set", {"raw": raw})
    store(session, loaded, raw, is_final=False, seq=event.seq)
    if status == "registered" and loaded.start.lane is not None:
        # Zeitplan: Die Bahn steht fest, der Start ist damit aufgerufen.
        await move(session, loaded, "called", actor)
    elif status == "registered":
        # Nachträgliche Erfassung ohne Aufrufen (Reihenfolge): Die Bahn bleibt leer.
        await move(session, loaded, "captured", actor)
    if loaded.start.status == "called":
        await move(session, loaded, "captured", actor)
    return await finish(session, events, loaded, event)


async def finalize(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    base_seq: int,
    idempotency_key: str | None,
) -> ResultState:
    request = Request("finalized", {"base_seq": base_seq}, idempotency_key, base_seq)
    loaded, replay = await begin(session, tournament_id, start_id, request)
    if replay:
        return await finish(session, events, loaded, None)
    if loaded.start.status != "captured" or loaded.current is None:
        raise ConflictError(
            "Abschließen geht nur bei einem erfassten Start, der noch nicht abgeschlossen ist."
        )
    raw = loaded.current.raw
    check_raw(loaded, raw, partial=False)
    now = await server_now(session)
    until = provisional_until(loaded, now)
    payload = {"provisional_until": until.isoformat() if until else None}
    event = append(session, loaded, request, actor, "finalized", payload)
    store(
        session,
        loaded,
        raw,
        is_final=True,
        finalized_at=now,
        provisional_until=until,
        seq=event.seq,
    )
    await move(session, loaded, "final", actor)
    return await finish(session, events, loaded, event)


async def correct(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    raw: dict[str, Any],
    reason: str,
    base_seq: int,
    idempotency_key: str | None,
) -> ResultState:
    body = {"raw": raw, "reason": reason, "base_seq": base_seq}
    request = Request("corrected", body, idempotency_key, base_seq)
    loaded, replay = await begin(session, tournament_id, start_id, request)
    if replay:
        return await finish(session, events, loaded, None)
    if loaded.start.status != "final":
        raise ConflictError(
            "Korrigieren geht nur bei einem abgeschlossenen Ergebnis; sonst die Rohwerte "
            "einfach neu erfassen."
        )
    check_raw(loaded, raw, partial=False)
    now = await server_now(session)
    until = provisional_until(loaded, now)
    payload = {"raw": raw, "provisional_until": until.isoformat() if until else None}
    event = append(session, loaded, request, actor, "corrected", payload, reason)
    store(
        session,
        loaded,
        raw,
        is_final=True,
        finalized_at=now,
        provisional_until=until,
        seq=event.seq,
    )
    return await finish(session, events, loaded, event)


async def reopen(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    reason: str,
    base_seq: int | None,
    idempotency_key: str | None,
) -> ResultState:
    request = Request(
        "reopened", {"reason": reason, "base_seq": base_seq}, idempotency_key, base_seq
    )
    loaded, replay = await begin(session, tournament_id, start_id, request)
    if replay:
        return await finish(session, events, loaded, None)
    if loaded.start.status != "final" or loaded.current is None:
        raise ConflictError("Wieder öffnen lässt sich nur ein abgeschlossenes Ergebnis.")
    event = append(session, loaded, request, actor, "reopened", {}, reason)
    store(session, loaded, loaded.current.raw, is_final=False, seq=event.seq)
    await move(session, loaded, "captured", actor, reason=reason)
    return await finish(session, events, loaded, event)


async def abort(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    abort_reason: AbortReason,
    reason: str | None,
    idempotency_key: str | None,
) -> ResultState:
    body = {"abort_reason": abort_reason, "reason": reason}
    request = Request("aborted", body, idempotency_key, None)
    loaded, replay = await begin(session, tournament_id, start_id, request)
    if replay:
        return await finish(session, events, loaded, None)
    # Prüft den Übergang (z. B. nicht aus „abgeschlossen“) und schreibt das Audit-Protokoll.
    await move(session, loaded, "aborted", actor, abort_reason=abort_reason)
    event = append(
        session, loaded, request, actor, "aborted", {"abort_reason": abort_reason}, reason
    )
    raw = loaded.current.raw if loaded.current is not None else {}
    # Vorhandene Rohwerte bleiben erhalten; der Stand gilt als offen.
    store(session, loaded, raw, is_final=False, seq=event.seq)
    return await finish(session, events, loaded, event)


# --- Anmeldung bei `starts.hooks` ---------------------------------------------------------


async def abort_from_starts(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    abort_reason: AbortReason,
) -> None:
    """Abbruch-Handler: `POST …/starts/{id}/abort` führt zum selben Ergebnis wie
    `POST …/starts/{id}/result/abort` (Ereignis `aborted` im Protokoll und Statuswechsel)."""
    await abort(session, events, actor, tournament_id, start_id, abort_reason, None, None)


async def starts_with_events(
    session: AsyncSession, start_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Ergebnisprüfer: Starts mit mindestens einem Ereignis im Protokoll."""
    rows = await session.scalars(
        select(ResultEvent.start_id).where(ResultEvent.start_id.in_(start_ids)).distinct()
    )
    return set(rows)
