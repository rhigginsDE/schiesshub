"""Schreibt den geprüften Katalog per Upsert in die Datenbank.

Regeln:
- Ein Verband wird nur übernommen, wenn er fehlerfrei ist. Sonst bleibt sein alter Stand stehen.
- Was nicht mehr in den Dateien steht, wird inaktiv gesetzt, nie gelöscht.
- Der Import darf beliebig oft laufen; er erzeugt keine Duplikate.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base, SessionFactory
from app.modules.katalog.loader import CatalogError, FederationCatalog, load_catalog
from app.modules.katalog.models import (
    CompetitionClass,
    Discipline,
    Federation,
    Group,
    ImportState,
)

logger = logging.getLogger("schiesshub.katalog")

# Schlüssel der Transaktionssperre: verhindert, dass zwei Prozesse gleichzeitig importieren.
_ADVISORY_LOCK_KEY = 7_203_001
_STATE_ID = 1


@dataclass(frozen=True, slots=True)
class ImportReport:
    imported: list[str]
    errors: list[CatalogError]


async def _upsert(
    session: AsyncSession,
    model: type[Base],
    rows: list[dict[str, Any]],
    key_columns: list[str],
) -> dict[str, int]:
    """Fügt Zeilen ein oder aktualisiert sie. Liefert {Wert der letzten Schlüsselspalte: id}."""
    if not rows:
        return {}
    statement = insert(model).values(rows)
    updates = {
        column: statement.excluded[column] for column in rows[0] if column not in key_columns
    }
    statement = statement.on_conflict_do_update(index_elements=key_columns, set_=updates).returning(
        model.__table__.c[key_columns[-1]], model.__table__.c.id
    )
    result = await session.execute(statement)
    return {row[0]: row[1] for row in result.all()}


async def _deactivate_missing(
    session: AsyncSession, model: type[Base], federation_id: int, key_column: str, keys: list[str]
) -> None:
    table = model.__table__
    await session.execute(
        update(table)
        .where(
            table.c.federation_id == federation_id,
            table.c[key_column].not_in(keys),
            table.c.active.is_(True),
        )
        .values(active=False)
    )


async def _import_federation(session: AsyncSession, catalog: FederationCatalog) -> None:
    head = catalog.head
    classes = catalog.classes
    details = head.model_dump(
        mode="json", exclude={"schema_", "id", "verband", "status"}, exclude_none=True
    )
    classes_meta = (
        classes.model_dump(
            mode="json", exclude={"schema_", "verband", "klassen"}, exclude_none=True
        )
        if classes is not None
        else None
    )
    federation_ids = await _upsert(
        session,
        Federation,
        [
            {
                "key": catalog.key,
                "short_name": head.verband.kuerzel,
                "name": head.verband.name,
                "rulebook_name": head.regelwerk.name,
                "rulebook_date": head.regelwerk.stand,
                "status": head.status,
                "details": details,
                "classes_meta": classes_meta,
                "active": True,
                "imported_at": func.now(),
            }
        ],
        ["key"],
    )
    federation_id = federation_ids[catalog.key]

    group_rows = [
        {
            "federation_id": federation_id,
            "key": source.content.gruppe.id,
            "name": source.content.gruppe.name,
            "weapon_type": source.content.gruppe.waffenart,
            "distance_m": source.content.gruppe.distanz_m,
            "kind": source.content.gruppe.art,
            "verified": source.content.wertung.geprueft,
            "scoring": source.content.wertung.model_dump(mode="json", exclude_none=True),
            "procedures": {
                key: ablauf.model_dump(mode="json", exclude_none=True)
                for key, ablauf in source.content.ablaeufe.items()
            },
            "source_file": source.file,
            "active": True,
        }
        for source in catalog.groups
    ]
    group_ids = await _upsert(session, Group, group_rows, ["federation_id", "key"])

    discipline_rows = [
        {
            "federation_id": federation_id,
            "group_id": group_ids[source.content.gruppe.id],
            "code": disziplin.kennziffer,
            "name": disziplin.name,
            "weapon": disziplin.waffe,
            "ammunition": disziplin.munition,
            "sights": disziplin.visierung,
            "position": disziplin.anschlag,
            "target": disziplin.scheibe,
            "procedure_key": disziplin.ablauf,
            "optional": disziplin.optional,
            "note": disziplin.hinweis,
            "to_check": disziplin.pruefen,
            "former_code": disziplin.fruehere_kennziffer,
            "active": True,
        }
        for source in catalog.groups
        for disziplin in source.content.disziplinen
    ]
    await _upsert(session, Discipline, discipline_rows, ["federation_id", "code"])

    class_rows = [
        {
            "federation_id": federation_id,
            "key": klasse.id,
            "name": klasse.name,
            "short_name": klasse.kurz,
            "gender": klasse.geschlecht,
            "age_hint": klasse.alter_hilfe,
            "min_starters_dm": klasse.mindeststarter_dm,
            "merge_into": klasse.zusammenlegen_in,
            "merge_by_age": klasse.zusammenlegen_nach_alter,
            "note": klasse.hinweis,
            "sort_order": index,
            "active": True,
        }
        for index, klasse in enumerate(classes.klassen if classes is not None else [])
    ]
    await _upsert(session, CompetitionClass, class_rows, ["federation_id", "key"])

    await _deactivate_missing(
        session, Group, federation_id, "key", [row["key"] for row in group_rows]
    )
    await _deactivate_missing(
        session, Discipline, federation_id, "code", [row["code"] for row in discipline_rows]
    )
    await _deactivate_missing(
        session, CompetitionClass, federation_id, "key", [row["key"] for row in class_rows]
    )


async def _deactivate_removed_federations(session: AsyncSession, present_keys: set[str]) -> None:
    """Verbände, deren Verzeichnis verschwunden ist, samt ihrer Einträge inaktiv setzen."""
    removed = (
        await session.scalars(
            select(Federation.id).where(
                Federation.key.not_in(present_keys), Federation.active.is_(True)
            )
        )
    ).all()
    if not removed:
        return
    await session.execute(update(Federation).where(Federation.id.in_(removed)).values(active=False))
    for model in (Group, Discipline, CompetitionClass):
        table = model.__table__
        await session.execute(
            update(table).where(table.c.federation_id.in_(removed)).values(active=False)
        )


async def save_import_state(session: AsyncSession, errors: list[CatalogError]) -> None:
    statement = insert(ImportState).values(
        id=_STATE_ID, attempted_at=func.now(), errors=[error.as_dict() for error in errors]
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "attempted_at": statement.excluded.attempted_at,
                "errors": statement.excluded.errors,
            },
        )
    )


async def import_catalog(session_factory: SessionFactory, catalog_dir: Path) -> ImportReport:
    """Liest `catalog_dir`, übernimmt fehlerfreie Verbände und vermerkt die Fehler."""
    result = await asyncio.to_thread(load_catalog, catalog_dir)

    async with session_factory() as session, session.begin():
        await session.execute(select(func.pg_advisory_xact_lock(_ADVISORY_LOCK_KEY)))
        for federation in result.federations:
            await _import_federation(session, federation)
        if result.present_keys is not None:
            await _deactivate_removed_federations(session, result.present_keys)
        await save_import_state(session, result.errors)

    for federation in result.federations:
        logger.info(
            "Katalog '%s' importiert: %d Gruppen, %d Disziplinen, %d Klassen",
            federation.key,
            len(federation.groups),
            federation.discipline_count,
            len(federation.classes.klassen) if federation.classes else 0,
        )
    for error in result.errors:
        logger.error("Katalogfehler: %s", error)
    if result.errors:
        logger.error(
            "Katalog hat %d Fehler; betroffene Verbände behalten ihren alten Stand.",
            len(result.errors),
        )
    return ImportReport(imported=[f.key for f in result.federations], errors=result.errors)
