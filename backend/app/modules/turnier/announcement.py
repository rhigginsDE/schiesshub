"""Turnierausschreibung: gespeicherte Gliederung und die zusammengesetzte Druckfassung.

Das PDF entsteht im Frontend als Druckansicht. Das Backend hält die Texte und setzt daraus mit den
aktuellen Turnierdaten ein Dokument zusammen. Teilnehmerdaten kommen darin nicht vor.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import EventHub
from app.modules.turnier import service
from app.modules.turnier.announcement_outline import default_announcement
from app.modules.turnier.models import Competition, Tournament
from app.modules.turnier.schemas import (
    Announcement,
    AnnouncementDocument,
    CompetitionDefinition,
    DocumentBlock,
    DocumentClass,
    DocumentCompetition,
    DocumentDates,
    DocumentFee,
    DocumentFees,
    DocumentRange,
    DocumentSection,
    DocumentTournament,
    TournamentSettings,
)

MULTI_START_RULES = {
    "best": "Bestes Ergebnis zählt",
    "first": "Erstes Ergebnis zählt",
    "all": "Alle Ergebnisse werden gewertet",
}


def stored_announcement(tournament: Tournament) -> Announcement:
    if tournament.announcement is None:
        return default_announcement(tournament.template)
    return Announcement.model_validate(tournament.announcement)


async def get_announcement(session: AsyncSession, tournament_id: uuid.UUID) -> Announcement:
    return stored_announcement(await service.get_tournament(session, tournament_id))


async def put_announcement(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, data: Announcement
) -> Announcement:
    tournament = await service.editable_tournament(session, tournament_id)
    tournament.announcement = data.model_dump(mode="json")
    await session.commit()
    events.publish("tournament.announcement_changed", {"tournament_id": str(tournament_id)})
    return data


# --- Druckfassung ------------------------------------------------------------------


def _number(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).replace(".", ",")


def _sections(definition: CompetitionDefinition) -> list[DocumentSection]:
    result = []
    for abschnitt in definition.variant.abschnitte:
        parts = [f"{abschnitt.serien} Serien"]
        if abschnitt.schuss_je_serie is not None:
            parts[0] += f" à {abschnitt.schuss_je_serie} Schuss"
        if abschnitt.zeit_je_serie_s is not None:
            parts.append(f"je {_number(abschnitt.zeit_je_serie_s)} s")
        elif abschnitt.zeiten_s is not None:
            parts.append("Zeiten " + ", ".join(_number(t) for t in abschnitt.zeiten_s) + " s")
        if abschnitt.sollzeit_s is not None:
            parts.append(f"Sollzeit {_number(abschnitt.sollzeit_s)} s")
        counted = abschnitt.serien_gewertet
        if counted is not None and counted < abschnitt.serien:
            parts.append(f"gewertet werden die ersten {counted}")
        result.append(
            DocumentSection(
                name=abschnitt.name,
                serien=abschnitt.serien,
                schuss_je_serie=abschnitt.schuss_je_serie,
                serien_gewertet=counted,
                summary=f"{abschnitt.name}: {', '.join(parts)}",
            )
        )
    return result


def _multi_start_text(item: Competition) -> str:
    if not item.multi_start:
        return "Ein Start je Teilnehmer"
    return f"{MULTI_START_RULES[item.multi_start_rule]} (bis zu {item.max_starts} Starts)"


async def _competitions(
    session: AsyncSession, competitions: list[Competition], range_names: dict[uuid.UUID, str]
) -> list[DocumentCompetition]:
    result = []
    for item in competitions:
        definition = CompetitionDefinition.model_validate(item.definition)
        diff = await service.catalog_diff_of(session, item)
        result.append(
            DocumentCompetition(
                id=item.id,
                name=item.name,
                catalog_federation=item.catalog_federation,
                catalog_code=item.catalog_code,
                group=definition.source.group if definition.source else None,
                range_name=range_names.get(item.range_id) if item.range_id else None,
                procedure=definition.ablauf_beschreibung,
                sections=_sections(definition),
                multi_start=item.multi_start,
                max_starts=item.max_starts,
                multi_start_rule=item.multi_start_rule,  # type: ignore[arg-type]
                multi_start_text=_multi_start_text(item),
                deviates_from_catalog=diff.deviates,
                deviations=[entry.text for entry in diff.differences],
            )
        )
    return result


async def build_document(session: AsyncSession, tournament_id: uuid.UUID) -> AnnouncementDocument:
    tournament, ranges, classes, competitions = await service.get_overview(session, tournament_id)
    announcement = stored_announcement(tournament)
    currency = TournamentSettings.model_validate(tournament.settings).currency
    range_names = {item.id: item.name for item in ranges}

    blocks: list[DocumentBlock] = []
    for block in announcement.blocks:
        if not block.visible:
            continue
        entry = DocumentBlock(id=block.id, kind=block.kind, heading=block.heading, body=block.body)
        match block.kind:
            case "competitions":
                entry.competitions = await _competitions(session, competitions, range_names)
            case "classes":
                entry.classes = [DocumentClass(name=c.name, short=c.short) for c in classes]
            case "fees":
                entry.fees = DocumentFees(
                    currency=currency,
                    items=[
                        DocumentFee(
                            competition_id=item.id,
                            name=item.name,
                            fee_first_cents=item.fee_first_cents,
                            fee_repeat_cents=item.fee_repeat_cents if item.multi_start else None,
                        )
                        for item in competitions
                    ],
                )
            case "dates":
                entry.dates = DocumentDates(
                    date_from=tournament.date_from,
                    date_to=tournament.date_to,
                    registration_deadline=announcement.facts.registration_deadline,
                )
            case "ranges":
                entry.ranges = [
                    DocumentRange(name=item.name, lane_count=item.lane_count) for item in ranges
                ]
        blocks.append(entry)

    return AnnouncementDocument(
        title=announcement.title or f"Ausschreibung {tournament.name}",
        tournament=DocumentTournament(
            id=tournament.id,
            name=tournament.name,
            organizer=tournament.organizer,
            date_from=tournament.date_from,
            date_to=tournament.date_to,
            status=tournament.status,  # type: ignore[arg-type]
            currency=currency,
        ),
        facts=announcement.facts,
        blocks=blocks,
    )
