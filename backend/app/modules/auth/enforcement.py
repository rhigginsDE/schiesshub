"""Schalter der Berechtigungsprüfung: Umgebung oder gespeicherte Einstellung.

Wirksam ist die Prüfung, wenn `AUTH_ENFORCED=true` in der Umgebung steht ODER der gespeicherte
Schalter (Tabelle `setting`, Schlüssel `auth_enforcement`) an ist. Einschalten geht in der App
(`POST /auth/enforcement/enable`), ausschalten nur auf der Server-Konsole
(`python -m app.modules.auth.cli enforcement off`).

Der Zustand liegt im Speicher (`app.state.auth_enforcement`), damit keine Anfrage dafür die
Datenbank fragt. Gelesen wird der gespeicherte Schalter beim Start und danach alle
`AUTH_ENFORCEMENT_POLL_SECONDS` Sekunden (Standard 5): So bekommt der laufende Server eine
Änderung über die Konsole mit, ohne Neustart. Das Backend läuft mit genau einem Prozess (siehe
`deploy/backend.Dockerfile`), deshalb genügt der Speicher dieses Prozesses; der Prüfer in
`app.core.security` ist ohnehin prozessweit.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import Literal

from fastapi import FastAPI, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import EventHub, register_event_names
from app.core.security import reset_permission_checker, set_permission_checker
from app.core.settings_store import get_setting, put_setting
from app.modules.auth import permissions
from app.modules.auth.identity import Identity, check_permission
from app.modules.auth.models import Role, UserAccount
from app.modules.auth.settings import AuthSettings

logger = logging.getLogger("schiesshub.auth")

SETTING_KEY = "auth_enforcement"
EVENT_CHANGED = "auth.enforcement_changed"
# Wer die Prüfung einschaltet, muss alles verwalten dürfen – sonst sperrt er sich womöglich aus.
FULL_ADMIN_PERMISSIONS: tuple[str, ...] = (
    "role.manage",
    "user.manage",
    "device.manage",
    "system.manage",
)

register_event_names(EVENT_CHANGED)

Source = Literal["env", "setting"]


class StoredEnforcement(BaseModel):
    enforced: bool = False


@dataclass(slots=True)
class EnforcementState:
    # `AUTH_ENFORCED` aus der Umgebung; ändert sich nur mit einem Neustart.
    env: bool
    # Gespeicherter Schalter, zuletzt gelesener Stand.
    setting: bool = False
    poll_seconds: float = 5.0
    task: asyncio.Task[None] | None = field(default=None, repr=False)

    @property
    def enforced(self) -> bool:
        return self.env or self.setting

    @property
    def source(self) -> Source | None:
        if self.env:
            return "env"
        if self.setting:
            return "setting"
        return None


def get_state(app: FastAPI) -> EnforcementState:
    return app.state.auth_enforcement


def is_enforced(request: Request) -> bool:
    return get_state(request.app).enforced


def apply(state: EnforcementState) -> None:
    """Registriert den echten Prüfer oder den offenen, je nach Zustand."""
    if state.enforced:
        set_permission_checker(check_permission)
    else:
        reset_permission_checker()


async def load(session: AsyncSession) -> bool:
    return (await get_setting(session, SETTING_KEY, StoredEnforcement)).enforced


async def store(session: AsyncSession, enforced: bool) -> None:
    """Schreibt den Schalter. Der Aufrufer bestätigt die Transaktion."""
    await put_setting(session, SETTING_KEY, StoredEnforcement(enforced=enforced))


def publish(events: EventHub, state: EnforcementState) -> None:
    events.publish(EVENT_CHANGED, {"enforced": state.enforced, "source": state.source})


# --- Voraussetzungen ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Blocker:
    code: str
    message_de: str


NO_ADMIN_WITH_PIN = Blocker(
    "no_admin_with_pin",
    "Es gibt noch keinen Administrator mit PIN. Bitte zuerst einen aktiven Benutzer mit "
    "Administrator-Rechten anlegen.",
)
DEVICE_NOT_PAIRED = Blocker(
    "device_not_paired",
    "Dieses Gerät ist nicht gekoppelt. Eingeschaltet werden kann die Prüfung nur an einem "
    "gekoppelten Gerät.",
)
NOT_LOGGED_IN = Blocker(
    "not_logged_in",
    "Du bist nicht angemeldet. Bitte als Administrator mit PIN anmelden.",
)
NOT_ADMIN = Blocker(
    "not_admin",
    "Du bist nicht als Administrator angemeldet. Einschalten darf nur, wer Rollen, Benutzer, "
    "Geräte und das System verwalten darf.",
)


def is_full_admin(role: Role) -> bool:
    """Darf die Rolle alles verwalten (`*` oder alle `FULL_ADMIN_PERMISSIONS`)?"""
    return role.is_system or all(
        permissions.grants(role.permissions, permission) for permission in FULL_ADMIN_PERMISSIONS
    )


async def full_admin_exists(session: AsyncSession) -> bool:
    """Gibt es einen aktiven Benutzer (jeder hat eine PIN) mit vollen Verwaltungsrechten?"""
    rows = await session.scalars(
        select(Role)
        .join(UserAccount, UserAccount.role_id == Role.id)
        .where(UserAccount.active.is_(True))
    )
    return any(is_full_admin(role) for role in rows.unique())


async def blockers(session: AsyncSession, identity: Identity) -> list[Blocker]:
    """Was fehlt, damit diese Anfrage die Prüfung einschalten darf (leer: nichts)."""
    found: list[Blocker] = []
    if not await full_admin_exists(session):
        found.append(NO_ADMIN_WITH_PIN)
    if identity.device is None:
        found.append(DEVICE_NOT_PAIRED)
    if identity.user is None:
        found.append(NOT_LOGGED_IN)
    elif identity.role is None or not is_full_admin(identity.role):
        found.append(NOT_ADMIN)
    return found


# --- Start, Neulesen, Ende ---------------------------------------------------


async def refresh(app: FastAPI) -> bool:
    """Liest den gespeicherten Schalter neu. Liefert, ob er sich geändert hat."""
    state = get_state(app)
    async with app.state.session_factory() as session:
        stored = await load(session)
    if stored == state.setting:
        return False
    was = state.enforced
    state.setting = stored
    if state.enforced != was:
        apply(state)
        publish(app.state.events, state)
    logger.warning(
        "Gespeicherter Schalter der Berechtigungsprüfung ist jetzt %s (wirksam: %s).",
        "an" if stored else "aus",
        "an" if state.enforced else "aus",
    )
    return True


async def _poll(app: FastAPI) -> None:
    state = get_state(app)
    while True:
        await asyncio.sleep(state.poll_seconds)
        try:
            await refresh(app)
        except Exception:
            # Datenbank kurz weg: beim nächsten Mal wieder versuchen, Zustand bleibt.
            logger.exception("Schalter der Berechtigungsprüfung konnte nicht gelesen werden.")


async def start(app: FastAPI, settings: AuthSettings) -> EnforcementState:
    state = EnforcementState(env=settings.enforced, poll_seconds=settings.enforcement_poll_seconds)
    async with app.state.session_factory() as session:
        state.setting = await load(session)
    app.state.auth_enforcement = state
    apply(state)
    state.task = asyncio.create_task(_poll(app), name="auth-enforcement-poll")
    if state.source == "env":
        logger.info("Berechtigungsprüfung aktiv (AUTH_ENFORCED).")
    elif state.source == "setting":
        logger.info("Berechtigungsprüfung aktiv (in der App eingeschaltet).")
    else:
        logger.warning(
            "Berechtigungsprüfung aus: weder AUTH_ENFORCED noch in der App eingeschaltet."
        )
    return state


async def stop(app: FastAPI) -> None:
    state: EnforcementState | None = getattr(app.state, "auth_enforcement", None)
    if state is None or state.task is None:
        return
    state.task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await state.task
    state.task = None
