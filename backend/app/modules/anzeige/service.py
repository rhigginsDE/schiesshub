"""Anzeigen verwalten: anlegen, ändern, Szenen ordnen, Geräte zuweisen, Löschprüfung.

Nach jeder Änderung geht `display.changed` mit `display_id` an die Clients; Bildschirme laden
dann ihren Feed neu. Änderungen landen im Audit-Protokoll.

Löschen im Turnier: Verweist eine Anzeige auf ein Turnier (fest gewählt) oder auf einen Stand,
einen Wettbewerb oder eine Klasse (in einer Szene), lehnt der Löschprüfer mit 409 ab und nennt
die Anzeige. Bewusst kein stilles Umstellen: Eine Anzeige wird von niemandem bedient, eine
unbemerkt geänderte Anzeige fiele erst im Turnier auf. Die Prüfer dürfen außerdem nichts ändern,
weil ein anderer Prüfer das Löschen noch ablehnen kann.
"""

import logging
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FieldError, InputError
from app.core.events import EventHub
from app.core.security import Actor
from app.core.settings_store import get_setting, put_setting
from app.modules.anzeige import defaults
from app.modules.anzeige.models import Display
from app.modules.anzeige.schemas import (
    DisplayConfig,
    DisplayCreate,
    DisplayUpdate,
    LiveRankingScene,
    RangeScene,
    StartlistScene,
    WinnersScene,
)
from app.modules.auth.audit import record_audit
from app.modules.auth.models import Device
from app.modules.turnier.hooks import (
    DeletionTarget,
    register_deletion_check,
    unregister_deletion_check,
)
from app.modules.turnier.models import Competition, Range, Tournament, TournamentClass

logger = logging.getLogger("schiesshub.anzeige")

EVENT_CHANGED = "display.changed"


class NotFoundError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class ConflictError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail)


class ModuleState(BaseModel):
    """Eintrag `anzeige` in der Tabelle `setting`."""

    defaults_created: bool = False


def default_config() -> DisplayConfig:
    return DisplayConfig.model_validate(defaults.DEFAULT_CONFIG)


def config_of(display: Display) -> DisplayConfig:
    return DisplayConfig.model_validate(display.config)


def _store(config: DisplayConfig) -> dict[str, Any]:
    return config.model_dump(mode="json")


def _publish(events: EventHub, display_id: uuid.UUID) -> None:
    events.publish(EVENT_CHANGED, {"display_id": str(display_id)})


# --- Nachschlagen ------------------------------------------------------------


async def list_displays(session: AsyncSession) -> list[Display]:
    return list(await session.scalars(select(Display).order_by(Display.sort, Display.name)))


async def get_display(session: AsyncSession, display_id: uuid.UUID) -> Display:
    display = await session.get(Display, display_id)
    if display is None:
        raise NotFoundError("Die Anzeige wurde nicht gefunden.")
    return display


async def display_of_device(session: AsyncSession, device_id: uuid.UUID | None) -> Display:
    display = None
    if device_id is not None:
        display = await session.scalar(select(Display).where(Display.device_id == device_id))
    if display is None:
        raise NotFoundError(
            "Diesem Gerät ist keine Anzeige zugewiesen. Bitte unter „Anzeige“ eine Anzeige "
            "wählen und dieses Gerät zuweisen."
        )
    return display


# --- Prüfung der Verweise ----------------------------------------------------


async def _check_references(
    session: AsyncSession, tournament_id: uuid.UUID | None, config: DisplayConfig, prefix: str
) -> list[FieldError]:
    """Turnier, Stände, Wettbewerbe und Klassen der Szenen müssen existieren.

    Bei fest gewähltem Turnier müssen sie zu diesem Turnier gehören. Im Modus „automatisch“
    genügt, dass es sie gibt; gehören sie nicht zum gerade aktiven Turnier, überspringt der Feed
    die Szene mit Grund.
    """
    errors: list[FieldError] = []
    if tournament_id is not None and await session.get(Tournament, tournament_id) is None:
        raise InputError.single("tournament_id", "Das Turnier wurde nicht gefunden.")

    async def owners(model: type, ids: set[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
        if not ids:
            return {}
        rows = await session.execute(
            select(model.id, model.tournament_id).where(model.id.in_(ids))  # type: ignore[attr-defined]
        )
        return dict(rows.all())

    wanted: dict[type, set[uuid.UUID]] = {Competition: set(), Range: set(), TournamentClass: set()}
    for scene in config.scenes:
        for model, ids in _scene_refs(scene).items():
            wanted[model] |= set(ids)
    found = {model: await owners(model, ids) for model, ids in wanted.items()}
    labels = {Competition: "Wettbewerb", Range: "Schießstand", TournamentClass: "Klasse"}
    for index, scene in enumerate(config.scenes):
        for model, ids in _scene_refs(scene).items():
            field = _REF_FIELDS[model]
            for position, item_id in enumerate(ids):
                path = f"{prefix}scenes[{index}].{field}[{position}]"
                owner = found[model].get(item_id)
                if owner is None:
                    errors.append(FieldError(field=path, message=f"{labels[model]} nicht gefunden"))
                elif tournament_id is not None and owner != tournament_id:
                    errors.append(
                        FieldError(
                            field=path,
                            message=f"{labels[model]} gehört nicht zum Turnier der Anzeige",
                        )
                    )
    return errors


_REF_FIELDS: dict[type, str] = {
    Competition: "competition_ids",
    TournamentClass: "class_ids",
    Range: "range_ids",
}


def _scene_refs(scene: Any) -> dict[type, list[uuid.UUID]]:
    """Verweise einer Szene je Tabelle. Bei der Standanzeige heißt das Feld `range_id`."""
    refs: dict[type, list[uuid.UUID]] = {}
    if isinstance(scene, LiveRankingScene | WinnersScene):
        refs[Competition] = scene.competition_ids
        refs[TournamentClass] = scene.class_ids
    elif isinstance(scene, StartlistScene):
        refs[Competition] = scene.competition_ids
        refs[Range] = scene.range_ids
    return refs


async def _check_range_scenes(
    session: AsyncSession, tournament_id: uuid.UUID | None, config: DisplayConfig, prefix: str
) -> list[FieldError]:
    errors = []
    for index, scene in enumerate(config.scenes):
        if not isinstance(scene, RangeScene):
            continue
        range_ = await session.get(Range, scene.range_id)
        path = f"{prefix}scenes[{index}].range_id"
        if range_ is None:
            errors.append(FieldError(field=path, message="Schießstand nicht gefunden"))
        elif tournament_id is not None and range_.tournament_id != tournament_id:
            errors.append(
                FieldError(field=path, message="Schießstand gehört nicht zum Turnier der Anzeige")
            )
    return errors


async def check_config(
    session: AsyncSession,
    tournament_id: uuid.UUID | None,
    config: DisplayConfig,
    prefix: str = "config.",
) -> None:
    """Prüft die Verweise; `prefix` ist der Pfad der config im Anfrage-Inhalt."""
    errors = await _check_references(session, tournament_id, config, prefix)
    errors += await _check_range_scenes(session, tournament_id, config, prefix)
    if errors:
        raise InputError(errors)


# --- Schreiben ---------------------------------------------------------------


async def _commit(session: AsyncSession, display: Display, conflict: str | None = None) -> None:
    """Bestätigt und lädt die Zeitstempel neu. Verletzt ein Unique-Index, gibt es 409."""
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(conflict or "Die Änderung widerspricht einer anderen Anzeige.") from exc
    await session.refresh(display)


def _name_taken(name: str) -> str:
    return f"Es gibt schon eine Anzeige mit dem Namen „{name}“."


async def _check_name_free(
    session: AsyncSession, name: str, own_id: uuid.UUID | None = None
) -> None:
    query = select(Display.id).where(Display.name == name)
    if own_id is not None:
        query = query.where(Display.id != own_id)
    if await session.scalar(query) is not None:
        raise ConflictError(_name_taken(name))


async def create_display(
    session: AsyncSession, events: EventHub, actor: Actor, data: DisplayCreate
) -> Display:
    config = data.config if data.config is not None else default_config()
    await _check_name_free(session, data.name)
    await check_config(session, data.tournament_id, config)
    sort = data.sort
    if sort is None:
        highest = await session.scalar(select(func.max(Display.sort)))
        sort = 0 if highest is None else highest + 1
    display = Display(
        name=data.name, tournament_id=data.tournament_id, config=_store(config), sort=sort
    )
    session.add(display)
    await session.flush()
    record_audit(session, actor, "display.created", "display", display.id, {"name": data.name})
    await _commit(session, display, _name_taken(data.name))
    _publish(events, display.id)
    return display


async def update_display(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    display_id: uuid.UUID,
    data: DisplayUpdate,
) -> Display:
    display = await get_display(session, display_id)
    changes = data.model_dump(exclude_unset=True, exclude={"config"})
    for key in ("name", "sort"):
        if key in changes and changes[key] is None:
            raise InputError.single(key, f"Das Feld „{key}“ darf nicht leer sein.")
    new_config: DisplayConfig | None = None
    if "config" in data.model_fields_set:
        if data.config is None:
            raise InputError.single("config", "Das Feld „config“ darf nicht leer sein.")
        new_config = data.config
    if "name" in changes:
        await _check_name_free(session, changes["name"], display.id)
    if "tournament_id" in changes or new_config is not None:
        # Szenen (neue oder gespeicherte) gegen das Turnier, das nach der Änderung gilt.
        tournament_id = changes.get("tournament_id", display.tournament_id)
        await check_config(session, tournament_id, new_config or config_of(display))
    for key, value in changes.items():
        setattr(display, key, value)
    details: dict[str, Any] = {
        key: str(value) if value is not None else None for key, value in changes.items()
    }
    if new_config is not None:
        display.config = _store(new_config)
        details["scenes"] = [scene.kind for scene in new_config.scenes]
    record_audit(session, actor, "display.updated", "display", display.id, details)
    await _commit(session, display, _name_taken(display.name))
    _publish(events, display.id)
    return display


async def put_config(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    display_id: uuid.UUID,
    config: DisplayConfig,
) -> Display:
    display = await get_display(session, display_id)
    await check_config(session, display.tournament_id, config, prefix="")
    display.config = _store(config)
    record_audit(
        session,
        actor,
        "display.config_changed",
        "display",
        display.id,
        {"scenes": [scene.kind for scene in config.scenes]},
    )
    await _commit(session, display)
    _publish(events, display.id)
    return display


async def reorder_scenes(
    session: AsyncSession, events: EventHub, actor: Actor, display_id: uuid.UUID, ids: list[str]
) -> Display:
    display = await get_display(session, display_id)
    config = config_of(display)
    current = [scene.id for scene in config.scenes]
    if sorted(ids) != sorted(current) or len(set(ids)) != len(ids):
        raise InputError.single(
            "ids", "Bitte jede Szene der Anzeige genau einmal angeben: " + ", ".join(current)
        )
    by_id = {scene.id: scene for scene in config.scenes}
    config = config.model_copy(update={"scenes": [by_id[scene_id] for scene_id in ids]})
    display.config = _store(config)
    record_audit(session, actor, "display.scenes_reordered", "display", display.id, {"ids": ids})
    await _commit(session, display)
    _publish(events, display.id)
    return display


async def assign_device(
    session: AsyncSession,
    events: EventHub,
    actor: Actor,
    display_id: uuid.UUID,
    device_id: uuid.UUID,
) -> Display:
    display = await get_display(session, display_id)
    device = await session.get(Device, device_id)
    if device is None:
        raise NotFoundError("Das Gerät wurde nicht gefunden.")
    if device.blocked:
        raise ConflictError("Das Gerät ist gesperrt und kann keine Anzeige zeigen.")
    other = await session.scalar(
        select(Display).where(Display.device_id == device_id, Display.id != display.id)
    )
    if other is not None:
        raise ConflictError(
            f"Das Gerät „{device.name}“ zeigt schon die Anzeige „{other.name}“. "
            "Bitte es dort zuerst lösen."
        )
    display.device_id = device_id
    record_audit(
        session,
        actor,
        "display.device_assigned",
        "display",
        display.id,
        {"device_id": str(device_id)},
    )
    await _commit(session, display, "Das Gerät zeigt schon eine andere Anzeige.")
    _publish(events, display.id)
    return display


async def release_device(
    session: AsyncSession, events: EventHub, actor: Actor, display_id: uuid.UUID
) -> Display:
    display = await get_display(session, display_id)
    if display.device_id is not None:
        record_audit(
            session,
            actor,
            "display.device_released",
            "display",
            display.id,
            {"device_id": str(display.device_id)},
        )
        display.device_id = None
        await _commit(session, display)
        _publish(events, display.id)
    return display


async def delete_display(
    session: AsyncSession, events: EventHub, actor: Actor, display_id: uuid.UUID
) -> None:
    display = await get_display(session, display_id)
    record_audit(session, actor, "display.deleted", "display", display.id, {"name": display.name})
    await session.delete(display)
    await session.commit()
    _publish(events, display_id)


async def create_defaults(session: AsyncSession, events: EventHub, actor: Actor) -> Display:
    """Legt die Hauptanzeige an, wenn es noch keine Anzeige gibt."""
    if await session.scalar(select(func.count()).select_from(Display)):
        raise ConflictError(
            "Es gibt schon Anzeigen. Die Standard-Anzeige wird nur angelegt, solange keine "
            "existiert."
        )
    display = await create_display(
        session, events, actor, DisplayCreate(name=defaults.DEFAULT_DISPLAY_NAME)
    )
    return display


# --- Löschprüfer für das Turnier-Modul ----------------------------------------


def _names(displays: list[Display]) -> str:
    names = [f"„{display.name}“" for display in displays]
    if len(names) == 1:
        return f"der Anzeige {names[0]}"
    return f"den Anzeigen {', '.join(names[:-1])} und {names[-1]}"


def _references(display: Display, target: DeletionTarget, ids: set[uuid.UUID]) -> bool:
    config = config_of(display)
    for scene in config.scenes:
        if target == "range" and isinstance(scene, RangeScene) and scene.range_id in ids:
            return True
        refs = _scene_refs(scene)
        model = {"range": Range, "competition": Competition, "class": TournamentClass}.get(target)
        if model is not None and ids & set(refs.get(model, [])):
            return True
    return False


async def turnier_deletion_check(
    session: AsyncSession, target: DeletionTarget, item_id: uuid.UUID
) -> str | None:
    displays = await list_displays(session)
    if not displays:
        return None
    if target == "tournament":
        pinned = [display for display in displays if display.tournament_id == item_id]
        child_ids: dict[DeletionTarget, set[uuid.UUID]] = {}
        for model, kind in (
            (Range, "range"),
            (Competition, "competition"),
            (TournamentClass, "class"),
        ):
            child_ids[kind] = set(  # type: ignore[index]
                await session.scalars(
                    select(model.id).where(model.tournament_id == item_id)  # type: ignore[attr-defined]
                )
            )
        used = [
            display
            for display in displays
            if display not in pinned
            and any(_references(display, kind, ids) for kind, ids in child_ids.items())
        ]
        if pinned or used:
            return (
                f"Das Turnier wird auf {_names(pinned + used)} gezeigt. Bitte dort zuerst ein "
                "anderes Turnier oder „automatisch“ wählen und die Szenen anpassen."
            )
        return None
    used = [display for display in displays if _references(display, target, {item_id})]
    if not used:
        return None
    what = {
        "range": "Der Schießstand",
        "competition": "Der Wettbewerb",
        "class": "Die Klasse",
    }[target]
    return f"{what} wird auf {_names(used)} gezeigt. Bitte die Szene dort zuerst anpassen."


# --- Start -------------------------------------------------------------------


async def ensure_defaults(session: AsyncSession) -> Display | None:
    """Einmalig beim ersten Start: die Hauptanzeige, wenn es noch keine Anzeige gibt."""
    state = await get_setting(session, defaults.SETTING_KEY, ModuleState)
    if state.defaults_created:
        return None
    created = None
    if not await session.scalar(select(func.count()).select_from(Display)):
        created = Display(
            name=defaults.DEFAULT_DISPLAY_NAME,
            tournament_id=None,
            config=_store(default_config()),
            sort=0,
        )
        session.add(created)
        logger.info("Standard-Anzeige „%s“ angelegt.", defaults.DEFAULT_DISPLAY_NAME)
    await put_setting(session, defaults.SETTING_KEY, ModuleState(defaults_created=True))
    return created


async def on_startup(app: FastAPI) -> None:
    register_deletion_check(turnier_deletion_check)
    async with app.state.session_factory() as session, session.begin():
        await ensure_defaults(session)


async def on_shutdown(app: FastAPI) -> None:
    unregister_deletion_check(turnier_deletion_check)
