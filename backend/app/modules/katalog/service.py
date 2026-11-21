"""Abfragen auf den importierten Katalog und der Import beim Start."""

import logging

from fastapi import FastAPI
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import SessionFactory
from app.core.events import EventHub
from app.modules.katalog import importer
from app.modules.katalog.loader import CatalogError
from app.modules.katalog.models import (
    CompetitionClass,
    Discipline,
    Federation,
    Group,
    ImportState,
)
from app.modules.katalog.schemas import (
    AblaufOut,
    DisziplinDetailOut,
    DisziplinOut,
    GruppeOut,
    KatalogFehlerOut,
    KatalogStatusOut,
    KlasseOut,
    RegelwerkOut,
    VerbandOut,
)

logger = logging.getLogger("schiesshub.katalog")

EVENT_IMPORTED = "katalog.importiert"


class NotFoundError(Exception):
    """Der gesuchte Katalogeintrag ist nicht vorhanden. Die Meldung ist für Anwender gedacht."""


# --- Import -----------------------------------------------------------------


async def run_import(
    session_factory: SessionFactory, settings: Settings, events: EventHub
) -> KatalogStatusOut | None:
    """Importiert den Katalog und meldet das Ergebnis.

    Wirft nie: Der Server soll auch mit fehlerhaftem Katalog starten.
    """
    try:
        await importer.import_catalog(session_factory, settings.catalog_dir)
    except Exception as exc:
        logger.exception("Katalog-Import abgebrochen; der alte Stand bleibt bestehen.")
        await _record_failure(session_factory, exc)
    try:
        async with session_factory() as session:
            status = await get_status(session)
    except Exception:
        logger.exception("Katalog-Status nicht lesbar.")
        return None
    events.publish(EVENT_IMPORTED, status.model_dump(mode="json"))
    return status


async def _record_failure(session_factory: SessionFactory, exc: Exception) -> None:
    error = CatalogError(None, None, None, f"Import abgebrochen: {type(exc).__name__}: {exc}")
    try:
        async with session_factory() as session, session.begin():
            await importer.save_import_state(session, [error])
    except Exception:
        logger.exception("Importfehler konnte nicht gespeichert werden.")


async def on_startup(app: FastAPI) -> None:
    await run_import(app.state.session_factory, app.state.settings, app.state.events)


# --- Abfragen ---------------------------------------------------------------


async def get_status(session: AsyncSession) -> KatalogStatusOut:
    async def count(model: type) -> int:
        statement = select(func.count()).select_from(model).where(model.active.is_(True))
        return (await session.scalar(statement)) or 0

    state = await session.get(ImportState, 1)
    return KatalogStatusOut(
        verbaende=await count(Federation),
        gruppen=await count(Group),
        disziplinen=await count(Discipline),
        klassen=await count(CompetitionClass),
        importiert_am=await session.scalar(select(func.max(Federation.imported_at))),
        fehler=[KatalogFehlerOut(**error) for error in (state.errors if state else [])],
    )


async def _require_federation(session: AsyncSession, key: str) -> None:
    exists = await session.scalar(
        select(Federation.id).where(Federation.key == key, Federation.active.is_(True))
    )
    if exists is None:
        raise NotFoundError(f"Der Verband „{key}“ ist im Katalog nicht vorhanden.")


async def list_federations(session: AsyncSession) -> list[VerbandOut]:
    group_count = (
        select(func.count())
        .select_from(Group)
        .where(Group.federation_id == Federation.id, Group.active.is_(True))
        .scalar_subquery()
    )
    discipline_count = (
        select(func.count())
        .select_from(Discipline)
        .where(Discipline.federation_id == Federation.id, Discipline.active.is_(True))
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Federation, group_count, discipline_count)
        .where(Federation.active.is_(True))
        .order_by(Federation.key)
    )
    return [
        VerbandOut(
            id=federation.key,
            kuerzel=federation.short_name,
            name=federation.name,
            regelwerk=RegelwerkOut(name=federation.rulebook_name, stand=federation.rulebook_date),
            status=federation.status,
            anzahl_gruppen=groups,
            anzahl_disziplinen=disciplines,
        )
        for federation, groups, disciplines in rows
    ]


async def list_groups(session: AsyncSession, federation_key: str | None) -> list[GruppeOut]:
    discipline_count = (
        select(func.count())
        .select_from(Discipline)
        .where(Discipline.group_id == Group.id, Discipline.active.is_(True))
        .scalar_subquery()
    )
    statement = (
        select(Group, Federation.key, discipline_count)
        .join(Federation, Federation.id == Group.federation_id)
        .where(Group.active.is_(True))
        .order_by(Federation.key, Group.key)
    )
    if federation_key is not None:
        await _require_federation(session, federation_key)
        statement = statement.where(Federation.key == federation_key)
    rows = await session.execute(statement)
    return [
        GruppeOut(
            verband=key,
            id=group.key,
            name=group.name,
            waffenart=group.weapon_type,
            distanz_m=group.distance_m,
            art=group.kind,
            anzahl=count,
            wertung_modell=group.scoring["modell"],
            geprueft=group.verified,
        )
        for group, key, count in rows
    ]


def _discipline_query() -> Select[tuple[Discipline, Group, str]]:
    return (
        select(Discipline, Group, Federation.key)
        .join(Group, Group.id == Discipline.group_id)
        .join(Federation, Federation.id == Discipline.federation_id)
        .where(Discipline.active.is_(True))
    )


def _discipline_fields(discipline: Discipline, group: Group, federation_key: str) -> dict:
    return {
        "verband": federation_key,
        "kennziffer": discipline.code,
        "name": discipline.name,
        "gruppe_id": group.key,
        "gruppe_name": group.name,
        "waffe": discipline.weapon,
        "munition": discipline.ammunition,
        "visierung": discipline.sights,
        "anschlag": discipline.position,
        "scheibe": discipline.target,
        "optional": discipline.optional,
        "hinweis": discipline.note,
    }


def _like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def list_disciplines(
    session: AsyncSession,
    federation_key: str | None,
    group_key: str | None,
    search: str | None,
) -> list[DisziplinOut]:
    statement = _discipline_query().order_by(Federation.key, Discipline.code)
    if federation_key is not None:
        await _require_federation(session, federation_key)
        statement = statement.where(Federation.key == federation_key)
    if group_key is not None:
        statement = statement.where(Group.key == group_key)
    if search and search.strip():
        pattern = _like_pattern(search.strip())
        statement = statement.where(
            or_(
                Discipline.code.ilike(pattern, escape="\\"),
                Discipline.name.ilike(pattern, escape="\\"),
            )
        )
    rows = await session.execute(statement)
    return [DisziplinOut(**_discipline_fields(*row)) for row in rows]


async def get_discipline(
    session: AsyncSession, federation_key: str, code: str
) -> DisziplinDetailOut:
    await _require_federation(session, federation_key)
    row = (
        await session.execute(
            _discipline_query().where(Federation.key == federation_key, Discipline.code == code)
        )
    ).first()
    if row is None:
        raise NotFoundError(
            f"Die Disziplin mit der Kennziffer „{code}“ gibt es im Katalog "
            f"des Verbands „{federation_key}“ nicht."
        )
    discipline, group, key = row
    procedure = group.procedures[discipline.procedure_key]
    return DisziplinDetailOut.model_validate(
        {
            **_discipline_fields(discipline, group, key),
            "pruefen": discipline.to_check,
            "fruehere_kennziffer": discipline.former_code,
            "ablauf": AblaufOut.model_validate(
                {"schluessel": discipline.procedure_key, **procedure}
            ),
            "wertung": group.scoring,
        }
    )


async def list_classes(session: AsyncSession, federation_key: str | None) -> list[KlasseOut]:
    statement = (
        select(CompetitionClass, Federation.key)
        .join(Federation, Federation.id == CompetitionClass.federation_id)
        .where(CompetitionClass.active.is_(True))
        .order_by(Federation.key, CompetitionClass.sort_order)
    )
    if federation_key is not None:
        await _require_federation(session, federation_key)
        statement = statement.where(Federation.key == federation_key)
    rows = await session.execute(statement)
    return [
        KlasseOut(
            verband=key,
            id=klass.key,
            name=klass.name,
            kurz=klass.short_name,
            geschlecht=klass.gender,
            alter_hilfe=klass.age_hint,
            mindeststarter_dm=klass.min_starters_dm,
            zusammenlegen_in=klass.merge_into,
            zusammenlegen_nach_alter=klass.merge_by_age,
            hinweis=klass.note,
        )
        for klass, key in rows
    ]
