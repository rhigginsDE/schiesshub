"""Lesende Sichten: Eingabemaske, Verlauf eines Starts, Liste „prüfen“."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Device, UserAccount
from app.modules.ergebnisse.abort_preview import abort_preview
from app.modules.ergebnisse.fields import change_label, derived_values
from app.modules.ergebnisse.models import ResultCurrent, ResultEvent
from app.modules.ergebnisse.recompute import ensure_current
from app.modules.ergebnisse.rules import EVENT_LABELS, raw_changes, scoring_definition
from app.modules.ergebnisse.schemas import (
    CaptureMode,
    EventOut,
    FormHeader,
    FormOut,
    RawChangeOut,
    ReviewItemOut,
)
from app.modules.ergebnisse.service import get_state
from app.modules.starts.common import ConflictError, get_start, get_tournament
from app.modules.starts.models import Entry, Start
from app.modules.teilnehmer.models import Club, Person
from app.modules.teilnehmer.names import clean_text, display_name
from app.modules.turnier.models import Competition, Range, TournamentClass
from app.scoring import Definition, DefinitionError, describe_form, load_definition


async def form(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    start_id: uuid.UUID,
    *,
    capture_mode: CaptureMode | None,
    full_name: bool,
) -> FormOut:
    """Maske für die aktuelle Definition, Kopf des Starts und aktueller Stand.

    `capture_mode` wählt nur die Darstellung (Einzelschuss oder Seriensumme); die Rohwerte
    dürfen beides enthalten, gewertet wird gleich. Ohne Angabe gilt die des Wettbewerbs.
    """
    loaded, state = await get_state(session, tournament_id, start_id)
    competition = loaded.competition
    mode = capture_mode or competition.capture_mode
    try:
        description = describe_form(loaded.definition, mode)
    except DefinitionError as exc:
        raise ConflictError(
            f"Die Definition des Wettbewerbs lässt sich nicht werten: {exc}. Bitte in der "
            "Turnierleitung prüfen."
        ) from exc
    person = await session.get(Person, loaded.entry.person_id)
    klass = await session.get(TournamentClass, loaded.entry.class_id)
    assert person is not None
    assert klass is not None
    club = (
        await session.scalar(select(Club.name).where(Club.id == person.club_id))
        if person.club_id is not None
        else None
    )
    range_ = (
        await session.get(Range, competition.range_id) if competition.range_id is not None else None
    )
    booked = await session.scalar(
        select(func.count()).where(
            Start.entry_id == loaded.entry.id, Start.competition_id == competition.id
        )
    )
    header = FormHeader(
        start_number=loaded.entry.start_number,
        display_name=(
            clean_text(person.name_enc)
            if full_name
            else display_name(person.name_enc, person.display_mode)
        ),
        full_name_shown=full_name,
        club=club if full_name or person.show_club else None,
        class_id=klass.id,
        class_name=klass.name,
        class_short=klass.short,
        competition_id=competition.id,
        competition_name=competition.name,
        competition_code=competition.catalog_code,
        range_id=range_.id if range_ is not None else None,
        range_name=range_.name if range_ is not None else None,
        attempt=loaded.start.attempt,
        attempts_booked=booked or 0,
        max_starts=competition.max_starts if competition.multi_start else 1,
        lane=loaded.start.lane,
    )
    return FormOut(
        header=header,
        competition_capture_mode=competition.capture_mode,
        form=description,
        current=state,
        abort_preview=abort_preview(competition, state.raw, state.status),
        derived_values=derived_values(description, state.raw, state.computed),
    )


async def event_list(
    session: AsyncSession, tournament_id: uuid.UUID, start_id: uuid.UUID
) -> list[EventOut]:
    context = await get_start(session, tournament_id, start_id)
    defn = _definition(context.competition)
    events = list(
        await session.scalars(
            select(ResultEvent).where(ResultEvent.start_id == start_id).order_by(ResultEvent.seq)
        )
    )
    user_ids = {e.user_id for e in events if e.user_id is not None}
    device_ids = {e.device_id for e in events if e.device_id is not None}
    users = dict(
        (
            await session.execute(
                select(UserAccount.id, UserAccount.name).where(UserAccount.id.in_(user_ids))
            )
        ).all()
    )
    devices = dict(
        (
            await session.execute(select(Device.id, Device.name).where(Device.id.in_(device_ids)))
        ).all()
    )
    previous: dict[str, Any] = {}
    result = []
    for event in events:
        raw = event.payload.get("raw")
        changes = []
        if raw is not None:
            changes = [
                RawChangeOut(
                    path=change.path,
                    label=change_label(defn, change.path),
                    before=change.before,
                    after=change.after,
                )
                for change in raw_changes(previous, raw)
            ]
            previous = raw
        until = event.payload.get("provisional_until")
        result.append(
            EventOut(
                seq=event.seq,
                type=event.type,
                type_label=EVENT_LABELS[event.type],
                created_at=event.created_at,
                user_id=event.user_id,
                user_name=users.get(event.user_id) if event.user_id else None,
                device_id=event.device_id,
                device_name=devices.get(event.device_id) if event.device_id else None,
                reason=event.reason,
                abort_reason=event.payload.get("abort_reason"),
                provisional_until=until,
                raw=raw,
                changes=changes,
            )
        )
    return result


def _definition(competition: Competition) -> Definition | None:
    try:
        return load_definition(scoring_definition(competition.definition))
    except DefinitionError, KeyError, TypeError:
        return None


async def review_list(session: AsyncSession, tournament_id: uuid.UUID) -> list[ReviewItemOut]:
    """Ergebnisse, die nach einer Änderung der Wertung zu prüfen sind (meist abgeschlossene,
    die nun unvollständig sind, oder Rohwerte, die nicht mehr zur Definition passen)."""
    await get_tournament(session, tournament_id)
    competitions = list(
        await session.scalars(select(Competition).where(Competition.tournament_id == tournament_id))
    )
    for competition in competitions:
        await ensure_current(session, competition)
    rows = await session.execute(
        select(ResultCurrent, Start, Entry.start_number, Person, Competition.name)
        .join(Start, Start.id == ResultCurrent.start_id)
        .join(Entry, Entry.id == Start.entry_id)
        .join(Person, Person.id == Entry.person_id)
        .join(Competition, Competition.id == Start.competition_id)
        .where(Entry.tournament_id == tournament_id, ResultCurrent.needs_review)
        .order_by(Competition.sort, Competition.name, Entry.start_number, Start.attempt)
    )
    return [
        ReviewItemOut(
            start_id=start.id,
            competition_id=start.competition_id,
            competition_name=competition_name,
            start_number=start_number,
            display_name=display_name(person.name_enc, person.display_mode),
            attempt=start.attempt,
            status=start.status,
            review_reason=current.review_reason or "",
            definition_revision=current.definition_revision,
        )
        for current, start, start_number, person, competition_name in rows
    ]
