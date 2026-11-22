"""Turniere mit Ständen, Klassen und Wettbewerben.

Nach jeder Änderung geht ein Ereignis an die Clients (`<bereich>.<was>`, Nutzlast: betroffene IDs),
damit sie die Daten neu laden. Ein abgeschlossenes Turnier lässt sich erst nach dem Wiederöffnen
ändern.

Wertungsrelevante Felder eines Wettbewerbs (`SCORING_FIELDS`) sind versioniert: Jede Änderung legt
eine `CompetitionRevision` an, schreibt einen Audit-Eintrag und meldet
`competition.definition_changed`, damit vorhandene Ergebnisse neu berechnet werden. Das geht auch
im laufenden Turnier, dann aber nur mit Grund.
"""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InputError, translate_errors
from app.core.events import EventHub
from app.core.security import Actor
from app.modules.auth.audit import record_audit
from app.modules.katalog import service as katalog_service
from app.modules.katalog.fileformat import Variante
from app.modules.katalog.models import Federation
from app.modules.turnier import catalog_diff, hooks
from app.modules.turnier.announcement_outline import default_announcement
from app.modules.turnier.models import (
    Competition,
    CompetitionRevision,
    Range,
    Tournament,
    TournamentClass,
)
from app.modules.turnier.planning import derive_planning
from app.modules.turnier.schemas import (
    CatalogDiffOut,
    ClassCreate,
    ClassUpdate,
    CompetitionCreate,
    CompetitionDefinition,
    CompetitionUpdate,
    DefinitionSource,
    DeviationOut,
    RangeCreate,
    RangeUpdate,
    TournamentCreate,
    TournamentSettings,
    TournamentSettingsUpdate,
    TournamentStatus,
    TournamentUpdate,
    check_multi_start,
)

# Standardwerte je Vorlage. Sie landen beim Anlegen in `settings` und sind danach frei änderbar.
TEMPLATE_SETTINGS: dict[str, dict[str, Any]] = {
    "open": {"default_multi_start": True, "default_max_starts": 3},
    "club_championship": {"default_multi_start": False, "default_max_starts": 1},
    "custom": {},
}

STATUS_FLOW: tuple[TournamentStatus, ...] = ("draft", "active", "closed")
STATUS_LABELS = {"draft": "Entwurf", "active": "aktiv", "closed": "abgeschlossen"}

# Felder, die das Ergebnis beeinflussen. Eine Änderung daran ergibt eine neue Revision.
SCORING_FIELDS = (
    "definition",
    "capture_mode",
    "multi_start",
    "max_starts",
    "multi_start_rule",
    "combined_ranking",
)


# --- Fehler ------------------------------------------------------------------


class NotFoundError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class ConflictError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail)


class InvalidError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def _invalid_input(exc: ValidationError, prefix: str) -> InputError:
    """Schemafehler beim Zusammenführen, mit Pfad ab der Wurzel der Anfrage."""
    errors = translate_errors([{**error, "loc": (prefix, *error["loc"])} for error in exc.errors()])
    return InputError(errors)


def _reject_nulls(changes: dict[str, Any], nullable: set[str], prefix: str = "") -> None:
    for key, value in changes.items():
        if value is None and key not in nullable:
            raise InputError.single(f"{prefix}{key}", f"Das Feld „{key}“ darf nicht leer sein.")


def _ids(**ids: uuid.UUID) -> dict[str, str]:
    return {key: str(value) for key, value in ids.items()}


async def _check_deletable(
    session: AsyncSession, target: hooks.DeletionTarget, item_id: uuid.UUID
) -> None:
    """Fragt die Löschprüfer anderer Module (z. B. `starts`)."""
    if reasons := await hooks.deletion_blockers(session, target, item_id):
        raise ConflictError(" ".join(reasons))


async def _delete(session: AsyncSession, item: object, what: str) -> None:
    """Löscht und bestätigt. Verweist noch etwas darauf, gibt es 409 statt eines Serverfehlers."""
    await session.delete(item)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            f"{what} kann nicht gelöscht werden, weil noch Daten darauf verweisen "
            "(zum Beispiel Anmeldungen oder Starts)."
        ) from exc


# --- Gemeinsame Bausteine ----------------------------------------------------


async def get_tournament(session: AsyncSession, tournament_id: uuid.UUID) -> Tournament:
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise NotFoundError("Das Turnier wurde nicht gefunden.")
    return tournament


async def editable_tournament(session: AsyncSession, tournament_id: uuid.UUID) -> Tournament:
    """Das Turnier, sofern es noch geändert werden darf (nicht abgeschlossen)."""
    tournament = await get_tournament(session, tournament_id)
    if tournament.status == "closed":
        raise ConflictError(
            "Das Turnier ist abgeschlossen. Zum Ändern muss es erst wieder geöffnet werden."
        )
    return tournament


async def _next_sort(
    session: AsyncSession,
    model: type[Range | TournamentClass | Competition],
    tournament_id: uuid.UUID,
) -> int:
    highest = await session.scalar(
        select(func.max(model.sort)).where(model.tournament_id == tournament_id)
    )
    return 0 if highest is None else highest + 1


async def _list[T: (Range, TournamentClass, Competition)](
    session: AsyncSession, model: type[T], tournament_id: uuid.UUID
) -> list[T]:
    rows = await session.scalars(
        select(model)
        .where(model.tournament_id == tournament_id)
        .order_by(model.sort, model.name, model.id)
    )
    return list(rows)


async def _get_child[T: (Range, TournamentClass, Competition)](
    session: AsyncSession, model: type[T], tournament_id: uuid.UUID, item_id: uuid.UUID, what: str
) -> T:
    item = await session.get(model, item_id)
    if item is None or item.tournament_id != tournament_id:
        raise NotFoundError(f"{what} wurde in diesem Turnier nicht gefunden.")
    return item


async def _reorder[T: (Range, TournamentClass, Competition)](
    session: AsyncSession, model: type[T], tournament_id: uuid.UUID, ids: Sequence[uuid.UUID]
) -> list[T]:
    items = {item.id: item for item in await _list(session, model, tournament_id)}
    if len(ids) != len(set(ids)) or set(ids) != set(items):
        raise InvalidError(
            "Die neue Reihenfolge muss jeden Eintrag des Turniers genau einmal enthalten."
        )
    for position, item_id in enumerate(ids):
        items[item_id].sort = position
    await session.commit()
    return [items[item_id] for item_id in ids]


# --- Turnier -----------------------------------------------------------------


def _merge_settings(base: dict[str, Any], changes: TournamentSettingsUpdate | None) -> dict:
    values = changes.model_dump(exclude_unset=True) if changes is not None else {}
    _reject_nulls(values, nullable={"protest_minutes"}, prefix="settings.")
    try:
        return TournamentSettings.model_validate({**base, **values}).model_dump(mode="json")
    except ValidationError as exc:
        raise _invalid_input(exc, "settings") from exc


def template_settings(template: str) -> dict[str, Any]:
    """Einstellungen einer Vorlage: allgemeine Standardwerte plus die Werte der Vorlage."""
    return {**TournamentSettings().model_dump(mode="json"), **TEMPLATE_SETTINGS[template]}


async def list_tournaments(session: AsyncSession) -> list[Tournament]:
    rows = await session.scalars(
        select(Tournament).order_by(Tournament.date_from.desc(), Tournament.name)
    )
    return list(rows)


async def create_tournament(
    session: AsyncSession, events: EventHub, data: TournamentCreate
) -> Tournament:
    date_to = data.date_to or data.date_from
    if date_to < data.date_from:
        raise InvalidError("Das Enddatum liegt vor dem Anfangsdatum.")
    tournament = Tournament(
        name=data.name,
        organizer=data.organizer,
        date_from=data.date_from,
        date_to=date_to,
        status="draft",
        template=data.template,
        settings=_merge_settings(template_settings(data.template), data.settings),
        announcement=default_announcement(data.template).model_dump(mode="json"),
    )
    session.add(tournament)
    await session.commit()
    await session.refresh(tournament)
    events.publish("tournament.created", _ids(tournament_id=tournament.id))
    return tournament


async def update_tournament(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, data: TournamentUpdate
) -> Tournament:
    tournament = await editable_tournament(session, tournament_id)
    changes = data.model_dump(exclude_unset=True, exclude={"settings"})
    _reject_nulls(changes, nullable={"organizer"})
    for key, value in changes.items():
        setattr(tournament, key, value)
    if tournament.date_to < tournament.date_from:
        raise InvalidError("Das Enddatum liegt vor dem Anfangsdatum.")
    if "settings" in data.model_fields_set:
        if data.settings is None:
            raise InputError.single("settings", "Das Feld „settings“ darf nicht leer sein.")
        tournament.settings = _merge_settings(tournament.settings, data.settings)
    await session.commit()
    await session.refresh(tournament)
    events.publish("tournament.updated", _ids(tournament_id=tournament.id))
    return tournament


async def change_status(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    new_status: TournamentStatus,
    authorize_reopen: Callable[[], Awaitable[object]],
) -> Tournament:
    """Statuswechsel nur schrittweise. Zurück (Wiederöffnen) verlangt eine eigene Berechtigung."""
    tournament = await get_tournament(session, tournament_id)
    current = STATUS_FLOW.index(tournament.status)
    target = STATUS_FLOW.index(new_status)
    if current == target:
        raise ConflictError(f"Das Turnier hat bereits den Status „{STATUS_LABELS[new_status]}“.")
    if abs(current - target) != 1:
        raise ConflictError(
            "Der Status wechselt nur schrittweise: Entwurf, aktiv, abgeschlossen. "
            f"Von „{STATUS_LABELS[tournament.status]}“ geht es nicht direkt zu "
            f"„{STATUS_LABELS[new_status]}“."
        )
    if target < current:
        await authorize_reopen()
    previous = tournament.status
    tournament.status = new_status
    await session.commit()
    await session.refresh(tournament)
    events.publish(
        "tournament.status_changed",
        {**_ids(tournament_id=tournament.id), "from": previous, "to": new_status},
    )
    return tournament


async def delete_tournament(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID
) -> None:
    tournament = await get_tournament(session, tournament_id)
    if tournament.status != "draft":
        raise ConflictError(
            "Nur ein Turnier im Entwurf lässt sich löschen. Dieses Turnier ist "
            f"„{STATUS_LABELS[tournament.status]}“."
        )
    await _check_deletable(session, "tournament", tournament_id)
    # Stände, Klassen und Wettbewerbe löscht die Datenbank mit (ON DELETE CASCADE).
    await _delete(session, tournament, "Das Turnier")
    events.publish("tournament.deleted", _ids(tournament_id=tournament_id))


# --- Stand -------------------------------------------------------------------

RANGE = "Der Stand"


async def list_ranges(session: AsyncSession, tournament_id: uuid.UUID) -> list[Range]:
    await get_tournament(session, tournament_id)
    return await _list(session, Range, tournament_id)


async def get_range(session: AsyncSession, tournament_id: uuid.UUID, range_id: uuid.UUID) -> Range:
    return await _get_child(session, Range, tournament_id, range_id, RANGE)


async def create_range(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, data: RangeCreate
) -> Range:
    await editable_tournament(session, tournament_id)
    sort = data.sort if data.sort is not None else await _next_sort(session, Range, tournament_id)
    item = Range(tournament_id=tournament_id, name=data.name, lane_count=data.lane_count, sort=sort)
    session.add(item)
    await session.commit()
    events.publish("range.created", _ids(tournament_id=tournament_id, range_id=item.id))
    return item


async def update_range(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    range_id: uuid.UUID,
    data: RangeUpdate,
) -> Range:
    await editable_tournament(session, tournament_id)
    item = await get_range(session, tournament_id, range_id)
    changes = data.model_dump(exclude_unset=True)
    _reject_nulls(changes, nullable=set())
    for key, value in changes.items():
        setattr(item, key, value)
    await session.commit()
    events.publish("range.updated", _ids(tournament_id=tournament_id, range_id=item.id))
    return item


async def delete_range(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, range_id: uuid.UUID
) -> None:
    await editable_tournament(session, tournament_id)
    item = await get_range(session, tournament_id, range_id)
    await _check_deletable(session, "range", range_id)
    # Wettbewerbe auf diesem Stand verlieren die Zuordnung (ON DELETE SET NULL).
    await _delete(session, item, RANGE)
    events.publish("range.deleted", _ids(tournament_id=tournament_id, range_id=range_id))


async def reorder_ranges(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[Range]:
    await editable_tournament(session, tournament_id)
    items = await _reorder(session, Range, tournament_id, ids)
    events.publish("range.reordered", _ids(tournament_id=tournament_id))
    return items


# --- Klasse ------------------------------------------------------------------

CLASS = "Die Klasse"


async def list_classes(session: AsyncSession, tournament_id: uuid.UUID) -> list[TournamentClass]:
    await get_tournament(session, tournament_id)
    return await _list(session, TournamentClass, tournament_id)


async def get_class(
    session: AsyncSession, tournament_id: uuid.UUID, class_id: uuid.UUID
) -> TournamentClass:
    return await _get_child(session, TournamentClass, tournament_id, class_id, CLASS)


async def _check_code_free(
    session: AsyncSession, tournament_id: uuid.UUID, code: str, own_id: uuid.UUID | None = None
) -> None:
    existing = await session.scalar(
        select(TournamentClass.id).where(
            TournamentClass.tournament_id == tournament_id, TournamentClass.code == code
        )
    )
    if existing is not None and existing != own_id:
        raise ConflictError(f"Eine Klasse mit dem Kürzel „{code}“ gibt es in diesem Turnier schon.")


async def _check_merge_target(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    own_id: uuid.UUID | None,
    target_id: uuid.UUID,
) -> None:
    """Das Ziel muss zum Turnier gehören, und die Zusammenlegung darf keinen Kreis bilden."""
    if target_id == own_id:
        raise InvalidError("Eine Klasse kann nicht in sich selbst zusammengelegt werden.")
    rows = await session.execute(
        select(TournamentClass.id, TournamentClass.merge_into_id).where(
            TournamentClass.tournament_id == tournament_id
        )
    )
    # Klasse -> Zielklasse ihrer Zusammenlegung.
    targets: dict[uuid.UUID, uuid.UUID | None] = dict(rows.all())
    if target_id not in targets:
        raise InvalidError("Die Zielklasse der Zusammenlegung gehört nicht zu diesem Turnier.")
    seen: set[uuid.UUID] = set()
    current: uuid.UUID | None = target_id
    while current is not None and current not in seen:
        if current == own_id:
            raise InvalidError(
                "Diese Zusammenlegung ergäbe einen Kreis: Die Zielklasse wird selbst "
                "(direkt oder über andere Klassen) in diese Klasse zusammengelegt."
            )
        seen.add(current)
        current = targets.get(current)


async def create_class(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, data: ClassCreate
) -> TournamentClass:
    await editable_tournament(session, tournament_id)
    await _check_code_free(session, tournament_id, data.code)
    if data.merge_into_id is not None:
        await _check_merge_target(session, tournament_id, None, data.merge_into_id)
    sort = (
        data.sort
        if data.sort is not None
        else await _next_sort(session, TournamentClass, tournament_id)
    )
    item = TournamentClass(
        tournament_id=tournament_id,
        code=data.code,
        name=data.name,
        short=data.short,
        sort=sort,
        merge_into_id=data.merge_into_id,
    )
    session.add(item)
    await session.commit()
    events.publish("class.created", _ids(tournament_id=tournament_id, class_id=item.id))
    return item


async def update_class(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    class_id: uuid.UUID,
    data: ClassUpdate,
) -> TournamentClass:
    await editable_tournament(session, tournament_id)
    item = await get_class(session, tournament_id, class_id)
    changes = data.model_dump(exclude_unset=True)
    _reject_nulls(changes, nullable={"merge_into_id"})
    if "code" in changes:
        await _check_code_free(session, tournament_id, changes["code"], own_id=item.id)
    if changes.get("merge_into_id") is not None:
        await _check_merge_target(session, tournament_id, item.id, changes["merge_into_id"])
    for key, value in changes.items():
        setattr(item, key, value)
    await session.commit()
    events.publish("class.updated", _ids(tournament_id=tournament_id, class_id=item.id))
    return item


async def delete_class(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, class_id: uuid.UUID
) -> None:
    await editable_tournament(session, tournament_id)
    item = await get_class(session, tournament_id, class_id)
    await _check_deletable(session, "class", class_id)
    # Verweise anderer Klassen löscht die Datenbank (ON DELETE SET NULL); die Zulassung in den
    # Wettbewerben ist eine Liste und wird hier bereinigt.
    await session.execute(
        update(Competition)
        .where(
            Competition.tournament_id == tournament_id,
            Competition.class_ids.contains([class_id]),
        )
        .values(class_ids=func.array_remove(Competition.class_ids, class_id))
    )
    await _delete(session, item, CLASS)
    events.publish("class.deleted", _ids(tournament_id=tournament_id, class_id=class_id))


async def reorder_classes(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[TournamentClass]:
    await editable_tournament(session, tournament_id)
    items = await _reorder(session, TournamentClass, tournament_id, ids)
    events.publish("class.reordered", _ids(tournament_id=tournament_id))
    return items


async def import_classes(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, federation: str
) -> list[TournamentClass]:
    """Kopiert die Klassen eines Verbands aus dem Katalog. Vorhandene Kürzel bleiben unberührt.

    Die Zusammenlegung wird übernommen, wenn der Katalog genau eine Zielklasse nennt und sie nicht
    vom Alter abhängt. Bei mehreren möglichen Zielen entscheidet die Turnierleitung.
    """
    await editable_tournament(session, tournament_id)
    try:
        catalog_classes = await katalog_service.list_classes(session, federation)
    except katalog_service.NotFoundError as exc:
        raise InvalidError(str(exc)) from exc

    by_code = {item.code: item for item in await _list(session, TournamentClass, tournament_id)}
    sort = await _next_sort(session, TournamentClass, tournament_id)
    created: list[tuple[TournamentClass, list[str], bool]] = []
    for klasse in catalog_classes:
        if klasse.id in by_code:
            continue
        item = TournamentClass(
            tournament_id=tournament_id,
            code=klasse.id,
            name=klasse.name,
            short=klasse.kurz,
            sort=sort,
        )
        sort += 1
        session.add(item)
        by_code[klasse.id] = item
        created.append((item, klasse.zusammenlegen_in, klasse.zusammenlegen_nach_alter))
    # Erst einfügen, dann verweisen: Die Ziele bekommen so sicher vorher ihre Zeile.
    await session.flush()
    for item, targets, by_age in created:
        if len(targets) == 1 and not by_age and targets[0] in by_code:
            item.merge_into_id = by_code[targets[0]].id
    await session.commit()
    events.publish(
        "class.imported",
        {**_ids(tournament_id=tournament_id), "class_ids": [str(c[0].id) for c in created]},
    )
    return [item for item, _, _ in created]


# --- Wettbewerb --------------------------------------------------------------

COMPETITION = "Der Wettbewerb"


def _pick_variant(varianten: list[Variante], variant_id: str | None, code: str) -> Variante:
    if variant_id is None:
        return varianten[0]
    for variante in varianten:
        if variante.id == variant_id:
            return variante
    available = ", ".join(f"„{variante.id}“" for variante in varianten)
    raise InvalidError(
        f"Die Variante „{variant_id}“ gibt es für die Kennziffer „{code}“ nicht. "
        f"Vorhanden: {available}."
    )


async def _catalog_definition(
    session: AsyncSession, federation: str, code: str, variant_id: str | None
) -> tuple[CompetitionDefinition, str]:
    """Kopie von Variante und Wertung aus dem Katalog, dazu der Name der Disziplin."""
    try:
        discipline = await katalog_service.get_discipline(session, federation, code)
    except katalog_service.NotFoundError as exc:
        raise InvalidError(str(exc)) from exc
    catalog_stand = await session.scalar(
        select(Federation.rulebook_date).where(Federation.key == federation)
    )
    variant = _pick_variant(discipline.ablauf.varianten, variant_id, code)
    definition = CompetitionDefinition(
        source=DefinitionSource(
            federation=federation,
            code=code,
            group=discipline.gruppe_id,
            variant_id=variant.id,
            catalog_stand=catalog_stand,
        ),
        variant=variant,
        scoring=discipline.wertung,
        ablauf_beschreibung=discipline.ablauf.beschreibung,
    )
    return definition, discipline.name


def _store(definition: CompetitionDefinition) -> dict[str, Any]:
    # Nicht gesetzte Katalogfelder fehlen, wie in den Katalogdateien.
    return definition.model_dump(mode="json", exclude_none=True)


async def _check_competition(
    session: AsyncSession, tournament_id: uuid.UUID, item: Competition
) -> None:
    """Prüft den fertigen Stand eines Wettbewerbs, egal ob neu oder geändert."""
    try:
        check_multi_start(item.multi_start, item.max_starts)
    except ValueError as exc:
        raise InvalidError(str(exc)) from exc
    if item.planning == "schedule" and item.heat_minutes is None:
        raise InvalidError(
            "Für einen Zeitplan wird die Dauer eines Durchgangs (heat_minutes) benötigt."
        )
    if item.range_id is not None:
        owner = await session.scalar(select(Range.tournament_id).where(Range.id == item.range_id))
        if owner != tournament_id:
            raise InvalidError("Der angegebene Stand gehört nicht zu diesem Turnier.")
    if item.class_ids:
        found = await session.scalar(
            select(func.count())
            .select_from(TournamentClass)
            .where(
                TournamentClass.tournament_id == tournament_id,
                TournamentClass.id.in_(item.class_ids),
            )
        )
        if found != len(item.class_ids):
            raise InvalidError("Mindestens eine der angegebenen Klassen gehört nicht zum Turnier.")


async def list_competitions(session: AsyncSession, tournament_id: uuid.UUID) -> list[Competition]:
    await get_tournament(session, tournament_id)
    return await _list(session, Competition, tournament_id)


async def get_competition(
    session: AsyncSession, tournament_id: uuid.UUID, competition_id: uuid.UUID
) -> Competition:
    return await _get_child(session, Competition, tournament_id, competition_id, COMPETITION)


# --- Revisionen ----------------------------------------------------------------

REASON_REQUIRED = (
    "Das Turnier läuft bereits. Für eine Änderung an der Wertung bitte einen Grund angeben."
)


def _scoring_state(item: Competition) -> dict[str, Any]:
    return {field: getattr(item, field) for field in SCORING_FIELDS}


def _add_revision(
    session: AsyncSession, item: Competition, actor: Actor, reason: str | None
) -> CompetitionRevision:
    revision = CompetitionRevision(
        competition_id=item.id,
        revision=item.definition_revision,
        changed_by=actor.user_id,
        device_id=actor.device_id,
        reason=reason,
        **_scoring_state(item),
    )
    session.add(revision)
    return revision


async def _record_scoring_change(
    session: AsyncSession,
    tournament: Tournament,
    item: Competition,
    actor: Actor,
    before: dict[str, Any],
    reason: str | None,
) -> int | None:
    """Legt eine neue Revision an, wenn sich wertungsrelevante Felder geändert haben.

    Liefert die neue Revisionsnummer oder None, wenn sich nichts geändert hat. Im laufenden
    Turnier ist ein Grund Pflicht; jede Änderung kommt ins Audit-Protokoll.
    """
    after = _scoring_state(item)
    changed = [field for field in SCORING_FIELDS if before[field] != after[field]]
    if not changed:
        return None
    reason = (reason or "").strip() or None
    if tournament.status == "active" and reason is None:
        raise InputError.single("reason", REASON_REQUIRED)
    item.definition_revision += 1
    _add_revision(session, item, actor, reason)
    record_audit(
        session,
        actor,
        "competition.definition_changed",
        "competition",
        item.id,
        {
            "tournament_id": str(tournament.id),
            "revision": item.definition_revision,
            "fields": changed,
            "reason": reason,
            "tournament_status": tournament.status,
        },
    )
    # Andere Module (Ergebnisse) rechnen in derselben Transaktion nach.
    await session.flush()
    await hooks.notify_definition_changed(session, item.id, item.definition_revision, actor)
    return item.definition_revision


def _publish_change(
    events: EventHub, tournament_id: uuid.UUID, item: Competition, revision: int | None
) -> None:
    ids = _ids(tournament_id=tournament_id, competition_id=item.id)
    events.publish("competition.updated", ids)
    if revision is not None:
        events.publish("competition.definition_changed", {**ids, "revision": revision})


async def list_revisions(
    session: AsyncSession, tournament_id: uuid.UUID, competition_id: uuid.UUID
) -> list[CompetitionRevision]:
    await get_competition(session, tournament_id, competition_id)
    rows = await session.scalars(
        select(CompetitionRevision)
        .where(CompetitionRevision.competition_id == competition_id)
        .order_by(CompetitionRevision.revision)
    )
    return list(rows)


async def get_revision(
    session: AsyncSession, tournament_id: uuid.UUID, competition_id: uuid.UUID, revision: int
) -> CompetitionRevision:
    await get_competition(session, tournament_id, competition_id)
    item = await session.scalar(
        select(CompetitionRevision).where(
            CompetitionRevision.competition_id == competition_id,
            CompetitionRevision.revision == revision,
        )
    )
    if item is None:
        raise NotFoundError(f"Die Revision {revision} gibt es für diesen Wettbewerb nicht.")
    return item


# --- Anlegen, Ändern, Zurücksetzen ---------------------------------------------


async def create_competition(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    data: CompetitionCreate,
    actor: Actor,
) -> Competition:
    tournament = await editable_tournament(session, tournament_id)
    defaults = TournamentSettings.model_validate(tournament.settings)

    if data.definition is not None:
        definition, name = data.definition, data.name
    else:
        # Das Eingabeschema stellt sicher, dass dann beide Katalogfelder gesetzt sind.
        assert data.catalog_federation is not None
        assert data.catalog_code is not None
        definition, discipline_name = await _catalog_definition(
            session, data.catalog_federation, data.catalog_code, data.variant_id
        )
        name = data.name or discipline_name

    multi_start = data.multi_start if data.multi_start is not None else defaults.default_multi_start
    if data.max_starts is not None:
        max_starts = data.max_starts
    else:
        max_starts = defaults.default_max_starts if multi_start else 1
    changeover = (
        data.changeover_minutes
        if data.changeover_minutes is not None
        else defaults.default_changeover_minutes
    )
    derived = derive_planning(definition.variant, changeover)

    item = Competition(
        id=uuid.uuid4(),
        tournament_id=tournament_id,
        range_id=data.range_id,
        sort=(
            data.sort
            if data.sort is not None
            else await _next_sort(session, Competition, tournament_id)
        ),
        catalog_federation=data.catalog_federation,
        catalog_code=data.catalog_code,
        name=name,
        definition=_store(definition),
        capture_mode=data.capture_mode or defaults.default_capture_mode,
        multi_start=multi_start,
        max_starts=max_starts,
        multi_start_rule=data.multi_start_rule or defaults.default_multi_start_rule,
        fee_first_cents=(
            data.fee_first_cents
            if data.fee_first_cents is not None
            else defaults.default_fee_first_cents
        ),
        fee_repeat_cents=(
            data.fee_repeat_cents
            if data.fee_repeat_cents is not None
            else defaults.default_fee_repeat_cents
        ),
        class_ids=data.class_ids or [],
        combined_ranking=bool(data.combined_ranking),
        planning=data.planning or derived.planning,
        heat_minutes=data.heat_minutes if data.heat_minutes is not None else derived.heat_minutes,
        changeover_minutes=changeover,
        definition_revision=1,
    )
    await _check_competition(session, tournament_id, item)
    session.add(item)
    # Erst den Wettbewerb schreiben, dann seine erste Revision (Fremdschlüssel).
    await session.flush()
    _add_revision(session, item, actor, reason=None)
    await session.commit()
    events.publish("competition.created", _ids(tournament_id=tournament_id, competition_id=item.id))
    return item


async def update_competition(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    competition_id: uuid.UUID,
    data: CompetitionUpdate,
    actor: Actor,
) -> Competition:
    tournament = await editable_tournament(session, tournament_id)
    item = await get_competition(session, tournament_id, competition_id)
    before = _scoring_state(item)
    changes = data.model_dump(exclude_unset=True, exclude={"definition", "reason"})
    _reject_nulls(changes, nullable={"range_id", "heat_minutes"})
    # Wer den Mehrfachstart abschaltet, meint genau einen Start.
    if changes.get("multi_start") is False and "max_starts" not in changes:
        changes["max_starts"] = 1
    for key, value in changes.items():
        setattr(item, key, value)

    if "definition" in data.model_fields_set:
        if data.definition is None:
            raise InputError.single("definition", "Das Feld „definition“ darf nicht leer sein.")
        stored_source = CompetitionDefinition.model_validate(item.definition).source
        definition = data.definition
        if definition.source is None:
            definition = definition.model_copy(update={"source": stored_source})
        elif definition.source != stored_source:
            raise InputError.single(
                "definition.source",
                "Die Herkunft (source) einer Definition lässt sich nicht ändern; "
                "das Feld weglassen oder unverändert mitschicken.",
            )
        item.definition = _store(definition)

    # Erst prüfen, dann schreiben: ein unbekannter Stand soll eine Meldung ergeben, keinen
    # Fehler der Datenbank.
    with session.no_autoflush:
        await _check_competition(session, tournament_id, item)
        revision = await _record_scoring_change(
            session, tournament, item, actor, before, data.reason
        )
    await session.commit()
    _publish_change(events, tournament_id, item, revision)
    return item


async def reset_definition(
    session: AsyncSession,
    events: EventHub,
    tournament_id: uuid.UUID,
    competition_id: uuid.UUID,
    variant_id: str | None,
    actor: Actor,
    reason: str | None = None,
) -> Competition:
    """Holt Variante und Wertung neu aus dem aktuellen Katalog; übrige Felder bleiben."""
    tournament = await editable_tournament(session, tournament_id)
    item = await get_competition(session, tournament_id, competition_id)
    if item.catalog_federation is None or item.catalog_code is None:
        raise ConflictError(
            "Dieser Wettbewerb stammt nicht aus dem Katalog und hat deshalb keinen Katalogwert."
        )
    if variant_id is None:
        variant_id = _source_variant_id(CompetitionDefinition.model_validate(item.definition))
    definition, _ = await _catalog_definition(
        session, item.catalog_federation, item.catalog_code, variant_id
    )
    before = _scoring_state(item)
    item.definition = _store(definition)
    revision = await _record_scoring_change(session, tournament, item, actor, before, reason)
    await session.commit()
    _publish_change(events, tournament_id, item, revision)
    return item


# --- Vergleich mit dem Katalog ---------------------------------------------------


def _source_variant_id(definition: CompetitionDefinition) -> str:
    """Die Katalog-Variante, aus der die Definition stammt."""
    if definition.source is not None and definition.source.variant_id is not None:
        return definition.source.variant_id
    return definition.variant.id


async def get_catalog_diff(
    session: AsyncSession, tournament_id: uuid.UUID, competition_id: uuid.UUID
) -> CatalogDiffOut:
    """Abweichungen der aktuellen Definition vom aktuellen Katalog; leer ohne Katalogherkunft."""
    return await catalog_diff_of(
        session, await get_competition(session, tournament_id, competition_id)
    )


async def catalog_diff_of(session: AsyncSession, item: Competition) -> CatalogDiffOut:
    if item.catalog_federation is None or item.catalog_code is None:
        return CatalogDiffOut(deviates=False)
    definition = CompetitionDefinition.model_validate(item.definition)
    variant_id = _source_variant_id(definition)
    origin = {"federation": item.catalog_federation, "code": item.catalog_code}
    try:
        catalog, _ = await _catalog_definition(
            session, item.catalog_federation, item.catalog_code, variant_id
        )
    except InvalidError:
        # Disziplin oder Variante gibt es im Katalog nicht mehr: kein Vergleich möglich.
        return CatalogDiffOut(deviates=False, variant_id=variant_id, **origin)
    deviations = catalog_diff.compare(
        catalog.variant, catalog.scoring, definition.variant, definition.scoring
    )
    return CatalogDiffOut(
        deviates=bool(deviations),
        variant_id=variant_id,
        catalog_stand=catalog.source.catalog_stand if catalog.source else None,
        catalog_available=True,
        differences=[
            DeviationOut(
                path=deviation.path,
                catalog_value=deviation.catalog_value,
                tournament_value=deviation.tournament_value,
                text=deviation.text,
                section_id=deviation.section_id,
            )
            for deviation in deviations
        ],
        **origin,
    )


async def delete_competition(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, competition_id: uuid.UUID
) -> None:
    await editable_tournament(session, tournament_id)
    item = await get_competition(session, tournament_id, competition_id)
    await _check_deletable(session, "competition", competition_id)
    await _delete(session, item, COMPETITION)
    events.publish(
        "competition.deleted", _ids(tournament_id=tournament_id, competition_id=competition_id)
    )


async def reorder_competitions(
    session: AsyncSession, events: EventHub, tournament_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[Competition]:
    await editable_tournament(session, tournament_id)
    items = await _reorder(session, Competition, tournament_id, ids)
    events.publish("competition.reordered", _ids(tournament_id=tournament_id))
    return items


# --- Übersicht ---------------------------------------------------------------


async def get_overview(
    session: AsyncSession, tournament_id: uuid.UUID
) -> tuple[Tournament, list[Range], list[TournamentClass], list[Competition]]:
    tournament = await get_tournament(session, tournament_id)
    return (
        tournament,
        await _list(session, Range, tournament_id),
        await _list(session, TournamentClass, tournament_id),
        await _list(session, Competition, tournament_id),
    )
