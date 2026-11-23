"""Turnierausschreibung: gespeicherte Gliederung und die zusammengesetzte Druckfassung.

Das PDF entsteht im Frontend als Druckansicht. Das Backend hält die Texte und setzt daraus mit den
aktuellen Turnierdaten ein Dokument zusammen. Teilnehmerdaten kommen darin nicht vor.

Formelle Wörter („Schützenstand“, „Protestgebühr“ …) kommen aus dem Begriffssatz des Verbands
(`app.core.begriffe`): je Wettbewerb der seines Verbands, für turnierweite Teile siehe
`document_terms`. Ob ein Wettbewerb vom Katalog abweicht, steht nicht in der Ausschreibung
(Entscheidung 23.11.2026), nur im Turnier-Editor.
"""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.begriffe import Begriffe, begriffe_fuer
from app.core.begriffe import standard as standard_terms
from app.core.events import EventHub
from app.modules.turnier import service
from app.modules.turnier.announcement_outline import default_announcement, missing_default_blocks
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


def announcement_json(announcement: Announcement) -> dict:
    """Zum Speichern: ohne das reine Ausgabefeld `missing_default_blocks`."""
    return announcement.model_dump(mode="json", exclude={"missing_default_blocks"})


def with_missing_blocks(announcement: Announcement, template: str) -> Announcement:
    return announcement.model_copy(
        update={"missing_default_blocks": missing_default_blocks(announcement, template)}
    )


async def get_announcement(session: AsyncSession, tournament_id: uuid.UUID) -> Announcement:
    tournament = await service.get_tournament(session, tournament_id)
    return with_missing_blocks(stored_announcement(tournament), tournament.template)


async def put_announcement(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, data: Announcement
) -> Announcement:
    tournament = await service.editable_tournament(session, tournament_id)
    tournament.announcement = announcement_json(data)
    template = tournament.template
    await session.commit()
    events.publish("tournament.announcement_changed", {"tournament_id": str(tournament_id)})
    return with_missing_blocks(data, template)


# --- Druckfassung ------------------------------------------------------------------


def duration_text(seconds: float | Decimal) -> str:
    """Zeit für Menschen: unter 60 s in Sekunden („45 s“, „7,5 s“), ab 60 s in Minuten
    („5 Min.“, „1 Min. 30 s“)."""
    value = Decimal(str(seconds))
    if value < 60:
        return f"{_number_text(value)} s"
    minutes = int(value // 60)
    rest = value - minutes * 60
    text = f"{minutes} Min."
    return f"{text} {_number_text(rest)} s" if rest else text


def _number_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        normalized = normalized.quantize(Decimal(1))
    return format(normalized, "f").replace(".", ",")


def _sections(
    definition: CompetitionDefinition, terms: Begriffe | None = None
) -> list[DocumentSection]:
    """Ablauf in Kurzform. „Serie“ kommt aus dem Begriffssatz des Verbands (`serie`, `serien`);
    BDS (SHB K 3.03) und DSB (SpO 0.12.1) sagen im Ablauf beide „Serie“."""
    terms = terms or standard_terms()
    result = []
    for abschnitt in definition.variant.abschnitte:
        word = terms.serie if abschnitt.serien == 1 else terms.serien
        parts = [f"{abschnitt.serien} {word}"]
        if abschnitt.schuss_je_serie is not None:
            parts[0] += f" à {abschnitt.schuss_je_serie} Schuss"
        if abschnitt.zeit_je_serie_s is not None:
            parts.append(f"je {duration_text(abschnitt.zeit_je_serie_s)}")
        elif abschnitt.zeiten_s is not None:
            parts.append("Zeiten " + ", ".join(duration_text(t) for t in abschnitt.zeiten_s))
        elif abschnitt.max_zeit_je_serie_s is not None:
            # Zeitlimit je Serie (Fallscheibe); nur ohne feste Zeit, sonst stünde es doppelt.
            limit = duration_text(abschnitt.max_zeit_je_serie_s)
            parts.append(f"höchstens {limit} je {terms.serie}")
        if abschnitt.zuschlag_je_stehender_scheibe_s is not None:
            penalty = duration_text(abschnitt.zuschlag_je_stehender_scheibe_s)
            parts.append(f"Zuschlag {penalty} je stehender Scheibe")
        if abschnitt.zeit_bei_abbruch_s is not None:
            fixed = duration_text(abschnitt.zeit_bei_abbruch_s)
            parts.append(f"Serienzeit bei Zeitlimit oder Abbruch {fixed}")
        if abschnitt.sollzeit_s is not None:
            parts.append(f"Sollzeit {duration_text(abschnitt.sollzeit_s)}")
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


def document_terms(competitions: list[Competition]) -> Begriffe:
    """Wörter für turnierweite Teile: der Satz des Verbands, wenn alle Katalog-Wettbewerbe aus
    einem Verband stammen; sonst (gemischt oder nur eigene Disziplinen) der Standardsatz."""
    federations = {
        item.catalog_federation.strip().lower() for item in competitions if item.catalog_federation
    }
    return begriffe_fuer(federations.pop() if len(federations) == 1 else None)


def lanes_text(count: int, terms: Begriffe) -> str:
    """„6 Schützenstände“, „1 Schützenstand“."""
    return f"{count} {terms.schuetzenstand if count == 1 else terms.schuetzenstaende}"


def _competitions(
    competitions: list[Competition], range_names: dict[uuid.UUID, str]
) -> list[DocumentCompetition]:
    result = []
    for item in competitions:
        definition = CompetitionDefinition.model_validate(item.definition)
        result.append(
            DocumentCompetition(
                id=item.id,
                name=item.name,
                catalog_federation=item.catalog_federation,
                catalog_code=item.catalog_code,
                group=definition.source.group if definition.source else None,
                range_name=range_names.get(item.range_id) if item.range_id else None,
                procedure=definition.ablauf_beschreibung,
                sections=_sections(definition, begriffe_fuer(item.catalog_federation)),
                multi_start=item.multi_start,
                max_starts=item.max_starts,
                multi_start_rule=item.multi_start_rule,  # type: ignore[arg-type]
                multi_start_text=_multi_start_text(item),
                terms=begriffe_fuer(item.catalog_federation),
            )
        )
    return result


async def build_document(session: AsyncSession, tournament_id: uuid.UUID) -> AnnouncementDocument:
    tournament, ranges, classes, competitions = await service.get_overview(session, tournament_id)
    announcement = stored_announcement(tournament)
    currency = TournamentSettings.model_validate(tournament.settings).currency
    range_names = {item.id: item.name for item in ranges}
    terms = document_terms(competitions)

    blocks: list[DocumentBlock] = []
    for block in announcement.blocks:
        if not block.visible:
            continue
        entry = DocumentBlock(id=block.id, kind=block.kind, heading=block.heading, body=block.body)
        match block.kind:
            case "competitions":
                entry.competitions = _competitions(competitions, range_names)
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
                    DocumentRange(
                        range_id=item.id,
                        name=item.name,
                        lane_count=item.lane_count,
                        lanes_text=lanes_text(item.lane_count, terms),
                    )
                    for item in ranges
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
        terms=terms,
    )
