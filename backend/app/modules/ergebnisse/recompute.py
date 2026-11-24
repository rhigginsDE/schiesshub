"""Neuaufbau von `result_current` aus den Ereignissen und der aktuellen Definition.

`recompute_competition` ist die öffentliche Schnittstelle. Sie läuft

- automatisch bei jeder neuen Revision der Wertung: angemeldet über
  `app.modules.turnier.hooks.register_definition_changed`, in derselben Transaktion wie die
  Änderung (siehe `on_definition_changed`);
- von Hand über `POST /tournaments/{tid}/competitions/{cid}/recompute`;
- beim Lesen, wenn ein Stand noch mit einer älteren Revision gerechnet ist
  (`ensure_current`), etwa wenn eine Erfassung gleichzeitig mit einer Änderung lief;
- einmalig beim Start des Moduls für Wettbewerbe mit reiner Trefferzählung, deren gespeicherte
  Stände noch Zehner (0) tragen (`sync_hits_only_tens`; ältere Versionen der Wertung). Danach
  findet die Prüfung nichts mehr: idempotent.

Rohwerte gehen dabei nie verloren: Sie kommen aus den Ereignissen, gestrichene Serien bleiben in
`raw`. Abgeschlossene Ergebnisse, die nach der neuen Definition unvollständig sind oder sich
nicht werten lassen, bleiben abgeschlossen und werden als „prüfen“ markiert (`needs_review`).
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory
from app.core.security import Actor
from app.modules.auth.audit import record_audit
from app.modules.ergebnisse.models import ResultCurrent, ResultEvent
from app.modules.ergebnisse.rules import (
    EventRecord,
    evaluate,
    has_stale_tens,
    hits_only_of,
    replay,
    scoring_definition,
)
from app.modules.ergebnisse.service import apply_evaluation
from app.modules.starts.models import Start
from app.modules.turnier.models import Competition

logger = logging.getLogger("schiesshub.ergebnisse")
TRIGGER_HITS_ONLY = "hits_only_tens"


@dataclass(frozen=True, slots=True)
class RecomputeResult:
    competition_id: uuid.UUID
    definition_revision: int
    recomputed: int
    needs_review: int


async def recompute_competition(
    session: AsyncSession, competition_id: uuid.UUID, actor: Actor, *, trigger: str = "manual"
) -> RecomputeResult:
    """Rechnet alle Starts des Wettbewerbs mit Ereignissen neu, ohne zu bestätigen."""
    competition = await session.get(Competition, competition_id)
    if competition is None:
        raise LookupError(f"Wettbewerb {competition_id} nicht gefunden")
    rows = await session.scalars(
        select(ResultEvent)
        .join(Start, Start.id == ResultEvent.start_id)
        .where(Start.competition_id == competition_id)
        .order_by(ResultEvent.start_id, ResultEvent.seq)
    )
    by_start: dict[uuid.UUID, list[EventRecord]] = defaultdict(list)
    for event in rows:
        by_start[event.start_id].append(
            EventRecord(event.seq, event.type, event.payload, event.created_at)
        )
    existing = {
        current.start_id: current
        for current in await session.scalars(
            select(ResultCurrent)
            .where(ResultCurrent.start_id.in_(by_start.keys()))
            .with_for_update()
        )
    }

    definition = scoring_definition(competition.definition)
    review = 0
    for start_id, events in by_start.items():
        state = replay(events)
        current = existing.get(start_id)
        if current is None:
            current = ResultCurrent(start_id=start_id, competition_id=competition_id)
            session.add(current)
        evaluation = evaluate(
            definition, competition.capture_mode, state.raw, is_final=state.is_final
        )
        apply_evaluation(current, evaluation, competition.definition_revision)
        current.raw = state.raw
        current.is_final = state.is_final
        current.finalized_at = state.finalized_at
        current.provisional_until = state.provisional_until
        current.last_seq = state.last_seq
        review += current.needs_review

    result = RecomputeResult(
        competition_id=competition_id,
        definition_revision=competition.definition_revision,
        recomputed=len(by_start),
        needs_review=review,
    )
    record_audit(
        session,
        actor,
        "result.recomputed",
        "competition",
        competition_id,
        {
            "tournament_id": str(competition.tournament_id),
            "competition_code": competition.catalog_code,
            "competition_name": competition.name,
            "definition_revision": result.definition_revision,
            "recomputed": result.recomputed,
            "needs_review": result.needs_review,
            "trigger": trigger,
        },
    )
    return result


async def on_definition_changed(
    session: AsyncSession, competition_id: uuid.UUID, revision: int, actor: Actor
) -> None:
    """Anmeldung bei `turnier.hooks`: neue Revision → sofort neu rechnen (selbe Transaktion)."""
    await recompute_competition(session, competition_id, actor, trigger="definition_changed")


async def ensure_current(session: AsyncSession, competition: Competition) -> bool:
    """Zieht Stände nach, die mit einer älteren Revision gerechnet sind; True, wenn nötig war.

    Bestätigt selbst, damit lesende Sichten danach einen stimmigen Stand zeigen.
    """
    stale = await session.scalar(
        select(ResultCurrent.start_id)
        .where(
            ResultCurrent.competition_id == competition.id,
            ResultCurrent.definition_revision != competition.definition_revision,
        )
        .limit(1)
    )
    if stale is None:
        return False
    await recompute_competition(session, competition.id, Actor(), trigger="stale")
    await session.commit()
    return True


@dataclass(frozen=True, slots=True)
class HitsOnlySync:
    competition_ids: list[uuid.UUID]
    recomputed: int
    needs_review: int


async def sync_hits_only_tens(session: AsyncSession) -> HitsOnlySync | None:
    """Rechnet Wettbewerbe mit reiner Trefferzählung neu, deren gespeicherte Stände noch Zehner
    tragen (früher 0, heute null); bestätigt nicht. None, wenn nichts zu tun war."""
    rows = await session.execute(
        select(ResultCurrent.competition_id, ResultCurrent.computed).where(
            ResultCurrent.computed.is_not(None)
        )
    )
    # Nur die Gesamtzahl: Sie ist nach dem Neurechnen bei Trefferzählung immer null (idempotent).
    candidates = {cid for cid, computed in rows if has_stale_tens(computed, series=False)}
    competitions = [
        competition
        for competition in await session.scalars(
            select(Competition).where(Competition.id.in_(candidates))
        )
        if hits_only_of(competition.definition)
    ]
    if not competitions:
        return None
    recomputed = review = 0
    competitions.sort(key=lambda item: str(item.id))
    for competition in competitions:
        result = await recompute_competition(
            session, competition.id, Actor(), trigger=TRIGGER_HITS_ONLY
        )
        recomputed += result.recomputed
        review += result.needs_review
    return HitsOnlySync([c.id for c in competitions], recomputed, review)


async def sync_hits_only_tens_on_startup(session_factory: SessionFactory) -> None:
    """Einmaliger Abgleich beim Start (`sync_hits_only_tens`); ein Fehler hält den Start nicht
    auf (die Rangliste und `GET …/form` zeigen die Zehner ohnehin als null)."""
    try:
        async with session_factory() as session:
            result = await sync_hits_only_tens(session)
            await session.commit()
    except Exception:
        logger.exception("Abgleich der Trefferzählung (Zehner → null) fehlgeschlagen.")
        return
    if result is not None:
        logger.info(
            "Trefferzählung: %d Wettbewerb(e) neu gerechnet, %d Starts (gespeicherte Zehner "
            "0 → null), %d zum Prüfen.",
            len(result.competition_ids),
            result.recomputed,
            result.needs_review,
        )
