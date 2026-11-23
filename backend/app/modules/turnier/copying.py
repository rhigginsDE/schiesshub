"""Turnier kopieren („wie letztes Jahr“).

Kopiert werden Einstellungen, Ausschreibung, Stände, Klassen (samt Zusammenlegung) und
Wettbewerbe mit ihrer Definition, also auch bewusste Abweichungen vom Katalog, Startgeld und
Mehrfachstart. Nicht kopiert werden Anmeldungen, Starts, Durchgänge, Ergebnisse und die
Revisionsgeschichte: Jeder Wettbewerb beginnt mit Revision 1. Die Kopie ist ein Entwurf und nie
ein Übungsturnier.

Termine: Der Meldeschluss der Ausschreibung wird um denselben Abstand verschoben wie der
Turnierbeginn (vorher 14 Tage vor dem Turnier, danach auch). Ohne neues Enddatum dauert die Kopie
so viele Tage wie das Original.

Zu jedem Wettbewerb aus dem Katalog meldet die Antwort, ob sich der Katalog geändert hat, seit
der Wettbewerb im Original aus ihm angelegt wurde. Grundlage ist Revision 1 des Originals (die
Kopie aus dem Katalog beim Anlegen). Wurde das Original später auf den Katalog zurückgesetzt,
kann der Hinweis auch dann erscheinen, wenn das Original den neuen Stand schon hatte; die Liste
`catalog_diff` zeigt in jedem Fall, was ein Zurücksetzen ändern würde.
"""

import copy
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import EventHub
from app.core.security import Actor
from app.modules.turnier import catalog_diff, service
from app.modules.turnier.models import (
    Competition,
    CompetitionRevision,
    Range,
    Tournament,
    TournamentClass,
)
from app.modules.turnier.schemas import (
    Announcement,
    CatalogDiffOut,
    CompetitionDefinition,
    TournamentCopy,
)


@dataclass(frozen=True, slots=True)
class CopiedCompetition:
    competition: Competition
    source_id: uuid.UUID
    catalog_changed: bool
    catalog_stand_then: date | None
    catalog_stand_now: date | None
    catalog_diff: CatalogDiffOut


def _shift_announcement(announcement: dict | None, days: int) -> dict | None:
    if announcement is None:
        return None
    parsed = Announcement.model_validate(announcement)
    deadline = parsed.facts.registration_deadline
    if deadline is not None:
        facts = parsed.facts.model_copy(
            update={"registration_deadline": date.fromordinal(deadline.toordinal() + days)}
        )
        parsed = parsed.model_copy(update={"facts": facts})
    return parsed.model_dump(mode="json")


async def _catalog_status(
    session: AsyncSession, original: Competition
) -> tuple[bool, date | None, date | None]:
    """Hat sich der Katalog seit dem Anlegen des Originals geändert? Dazu beide Stände."""
    if original.catalog_federation is None or original.catalog_code is None:
        return False, None, None
    first = await session.scalar(
        select(CompetitionRevision.definition).where(
            CompetitionRevision.competition_id == original.id, CompetitionRevision.revision == 1
        )
    )
    base = CompetitionDefinition.model_validate(first or original.definition)
    then = base.source.catalog_stand if base.source is not None else None
    try:
        catalog, _ = await service._catalog_definition(
            session,
            original.catalog_federation,
            original.catalog_code,
            service._source_variant_id(base),
        )
    except service.InvalidError:
        # Disziplin oder Variante gibt es nicht mehr: Das ist auch eine Änderung des Katalogs.
        return True, then, None
    now = catalog.source.catalog_stand if catalog.source is not None else None
    changed = bool(
        catalog_diff.compare(catalog.variant, catalog.scoring, base.variant, base.scoring)
    )
    return changed, then, now


async def copy_tournament(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    source_id: uuid.UUID,
    data: TournamentCopy,
) -> tuple[Tournament, list[CopiedCompetition]]:
    source = await service.get_tournament(session, source_id)
    date_to = data.date_to or date.fromordinal(
        data.date_from.toordinal() + (source.date_to - source.date_from).days
    )
    if date_to < data.date_from:
        raise service.InvalidError("Das Enddatum liegt vor dem Anfangsdatum.")
    shift = (data.date_from - source.date_from).days
    organizer = data.organizer if "organizer" in data.model_fields_set else source.organizer

    tournament = Tournament(
        id=uuid.uuid4(),
        name=data.name,
        organizer=organizer,
        date_from=data.date_from,
        date_to=date_to,
        status="draft",
        template=source.template,
        settings=copy.deepcopy(source.settings),
        announcement=_shift_announcement(source.announcement, shift),
        is_practice=False,
    )
    session.add(tournament)

    range_ids: dict[uuid.UUID, uuid.UUID] = {}
    for item in await service._list(session, Range, source_id):
        copy_range = Range(
            id=uuid.uuid4(),
            tournament_id=tournament.id,
            name=item.name,
            lane_count=item.lane_count,
            sort=item.sort,
        )
        range_ids[item.id] = copy_range.id
        session.add(copy_range)

    class_ids: dict[uuid.UUID, uuid.UUID] = {}
    classes = await service._list(session, TournamentClass, source_id)
    for item in classes:
        class_ids[item.id] = uuid.uuid4()
        session.add(
            TournamentClass(
                id=class_ids[item.id],
                tournament_id=tournament.id,
                code=item.code,
                name=item.name,
                short=item.short,
                sort=item.sort,
            )
        )
    # Erst alle Klassen schreiben, dann die Zusammenlegungen darauf verweisen lassen.
    await session.flush()
    for item in classes:
        if item.merge_into_id is not None and item.merge_into_id in class_ids:
            copy_class = await session.get(TournamentClass, class_ids[item.id])
            assert copy_class is not None
            copy_class.merge_into_id = class_ids[item.merge_into_id]

    originals = await service._list(session, Competition, source_id)
    copies: list[tuple[Competition, Competition]] = []
    for item in originals:
        copy_competition = Competition(
            id=uuid.uuid4(),
            tournament_id=tournament.id,
            range_id=range_ids.get(item.range_id) if item.range_id is not None else None,
            sort=item.sort,
            catalog_federation=item.catalog_federation,
            catalog_code=item.catalog_code,
            name=item.name,
            definition=copy.deepcopy(item.definition),
            capture_mode=item.capture_mode,
            multi_start=item.multi_start,
            max_starts=item.max_starts,
            multi_start_rule=item.multi_start_rule,
            fee_first_cents=item.fee_first_cents,
            fee_repeat_cents=item.fee_repeat_cents,
            class_ids=[class_ids[class_id] for class_id in item.class_ids if class_id in class_ids],
            combined_ranking=item.combined_ranking,
            planning=item.planning,
            heat_minutes=item.heat_minutes,
            changeover_minutes=item.changeover_minutes,
            definition_revision=1,
        )
        session.add(copy_competition)
        copies.append((item, copy_competition))
    await session.flush()
    for _, copy_competition in copies:
        service._add_revision(
            session, copy_competition, actor, reason=f"Kopiert aus dem Turnier „{source.name}“."
        )
    await session.commit()
    await session.refresh(tournament)
    events.publish(
        "tournament.created",
        {"tournament_id": str(tournament.id), "copied_from": str(source_id)},
    )

    result = []
    for original, copy_competition in copies:
        changed, then, now = await _catalog_status(session, original)
        result.append(
            CopiedCompetition(
                competition=copy_competition,
                source_id=original.id,
                catalog_changed=changed,
                catalog_stand_then=then,
                catalog_stand_now=now,
                catalog_diff=await service.catalog_diff_of(session, copy_competition),
            )
        )
    return tournament, result
