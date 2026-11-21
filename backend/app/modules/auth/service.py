"""Fachlogik: Ersteinrichtung, Kopplung, Anmeldung, Geräte, Rollen und Personen.

Jede Funktion, die Daten ändert, schreibt einen Audit-Eintrag, committet und meldet danach ein
Ereignis über den EventHub (Nutzlast: nur IDs).
"""

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import EventHub
from app.core.security import Actor, reset_permission_checker, set_permission_checker
from app.modules.auth import credentials, permissions
from app.modules.auth.audit import record_audit
from app.modules.auth.errors import (
    ConflictError,
    InvalidError,
    LockedError,
    NotFoundError,
    UnauthorizedError,
)
from app.modules.auth.identity import Identity, check_permission, now
from app.modules.auth.models import AuthSession, Device, PairingCode, Role, UserAccount
from app.modules.auth.schemas import (
    DeviceBrief,
    DeviceOut,
    DeviceUpdateIn,
    LoginIn,
    PairIn,
    PairingCodeIn,
    PairingCodeOut,
    PermissionOut,
    RoleBrief,
    RoleIn,
    RoleOut,
    RoleUpdateIn,
    SetupIn,
    StatusOut,
    UserBrief,
    UserIn,
    UserOut,
    UserUpdateIn,
)
from app.modules.auth.settings import AuthSettings

logger = logging.getLogger("schiesshub.auth")

PAIR_PATH = "/pair?code={code}"
NOT_PAIRED = "Dieses Gerät ist nicht gekoppelt. Bitte zuerst über einen QR-Code koppeln."
WRONG_PIN = "Die Anmeldung ist fehlgeschlagen. Bitte Person und PIN prüfen."
LAST_ADMIN = "Es muss immer mindestens ein aktiver Administrator bleiben."


@dataclass(frozen=True, slots=True)
class Issued:
    """Ergebnis einer Anmeldung oder Kopplung: neue Token für die Cookies."""

    device_token: str | None
    session_token: str | None


# --- Start -------------------------------------------------------------------


async def seed_roles(session: AsyncSession) -> None:
    """Legt die Startrollen an, wenn es noch gar keine Rolle gibt."""
    if await session.scalar(select(func.count()).select_from(Role)):
        return
    for name, entries in permissions.STARTER_ROLES.items():
        session.add(
            Role(
                name=name,
                permissions=list(entries),
                is_system=name == permissions.ADMIN_ROLE_NAME,
            )
        )
    logger.info("Startrollen angelegt: %s", ", ".join(permissions.STARTER_ROLES))


async def remove_expired(session: AsyncSession) -> None:
    current = now()
    await session.execute(delete(AuthSession).where(AuthSession.expires_at <= current))
    await session.execute(
        delete(PairingCode).where(
            (PairingCode.expires_at <= current) | PairingCode.used_at.is_not(None)
        )
    )


async def on_startup(app: FastAPI) -> None:
    if not hasattr(app.state, "auth_settings"):
        app.state.auth_settings = AuthSettings()
    settings: AuthSettings = app.state.auth_settings
    async with app.state.session_factory() as session, session.begin():
        await seed_roles(session)
        await remove_expired(session)
    if settings.enforced:
        set_permission_checker(check_permission)
        logger.info("Berechtigungsprüfung aktiv (AUTH_ENFORCED).")
    else:
        reset_permission_checker()
        logger.warning("Berechtigungsprüfung aus: AUTH_ENFORCED ist nicht gesetzt.")


# --- Hilfen ------------------------------------------------------------------


def _check_pin(pin: str, settings: AuthSettings) -> None:
    if not pin.isascii() or not pin.isdigit() or len(pin) < settings.pin_min_length:
        raise InvalidError(
            f"Die PIN muss aus mindestens {settings.pin_min_length} Ziffern bestehen."
        )


async def _admin_role(session: AsyncSession, *, lock: bool = False) -> Role:
    """Die Systemrolle. Mit `lock` werden Änderungen an Administratoren nacheinander ausgeführt."""
    statement = select(Role).where(Role.is_system.is_(True))
    if lock:
        statement = statement.with_for_update()
    role = await session.scalar(statement)
    if role is None:
        raise RuntimeError("Die Systemrolle Administrator fehlt.")
    return role


async def _active_admin_count(session: AsyncSession, admin_role: Role) -> int:
    statement = select(func.count()).where(
        UserAccount.role_id == admin_role.id, UserAccount.active.is_(True)
    )
    return await session.scalar(statement) or 0


async def setup_required(session: AsyncSession) -> bool:
    return await _active_admin_count(session, await _admin_role(session)) == 0


async def _role_or_invalid(session: AsyncSession, role_id: uuid.UUID) -> Role:
    role = await session.get(Role, role_id)
    if role is None:
        raise InvalidError("Die angegebene Rolle gibt es nicht.")
    return role


async def _ensure_unique_user_name(
    session: AsyncSession, name: str, exclude: uuid.UUID | None = None
) -> None:
    statement = select(UserAccount.id).where(func.lower(UserAccount.name) == name.lower())
    if exclude is not None:
        statement = statement.where(UserAccount.id != exclude)
    if await session.scalar(statement) is not None:
        raise ConflictError(f"Eine Person mit dem Namen „{name}“ gibt es bereits.")


async def _ensure_unique_role_name(
    session: AsyncSession, name: str, exclude: uuid.UUID | None = None
) -> None:
    statement = select(Role.id).where(func.lower(Role.name) == name.lower())
    if exclude is not None:
        statement = statement.where(Role.id != exclude)
    if await session.scalar(statement) is not None:
        raise ConflictError(f"Eine Rolle mit dem Namen „{name}“ gibt es bereits.")


def _new_session(
    device: Device, user: UserAccount, settings: AuthSettings
) -> tuple[str, AuthSession]:
    token = credentials.new_token()
    auth_session = AuthSession(
        device_id=device.id,
        user_id=user.id,
        token_hash=credentials.token_hash(token),
        expires_at=now() + timedelta(hours=settings.session_idle_hours),
    )
    return token, auth_session


def _new_device(name: str, default_role_id: uuid.UUID | None) -> tuple[str, Device]:
    token = credentials.new_token()
    device = Device(
        id=uuid.uuid4(),
        name=name,
        token_hash=credentials.token_hash(token),
        paired_at=now(),
        default_role_id=default_role_id,
    )
    return token, device


# --- Status ------------------------------------------------------------------


async def get_status(
    session: AsyncSession, identity: Identity, settings: AuthSettings
) -> StatusOut:
    device = identity.device
    return StatusOut(
        setup_required=await setup_required(session),
        auth_enforced=settings.enforced,
        device=DeviceBrief(id=device.id, name=device.name, default_role_id=device.default_role_id)
        if device
        else None,
        user=UserBrief(id=identity.user.id, name=identity.user.name) if identity.user else None,
        role=RoleBrief(id=identity.role.id, name=identity.role.name) if identity.role else None,
        permissions=identity.permissions,
    )


# --- Ersteinrichtung ---------------------------------------------------------


async def setup(
    session: AsyncSession,
    identity: Identity,
    settings: AuthSettings,
    events: EventHub,
    body: SetupIn,
) -> Issued:
    admin_role = await _admin_role(session, lock=True)
    if await _active_admin_count(session, admin_role):
        raise ConflictError("Die Ersteinrichtung ist bereits abgeschlossen.")
    _check_pin(body.pin, settings)
    await _ensure_unique_user_name(session, body.name)

    user = UserAccount(
        id=uuid.uuid4(),
        name=body.name,
        pin_hash=await credentials.hash_pin(body.pin),
        role_id=admin_role.id,
    )
    session.add(user)
    device_token: str | None = None
    device = identity.device
    if device is None:
        device_token, device = _new_device(body.device_name, None)
        session.add(device)
    await session.flush()
    session_token, auth_session = _new_session(device, user, settings)
    session.add(auth_session)
    record_audit(
        session,
        Actor(user_id=user.id, device_id=device.id, user_name=user.name),
        "auth.setup",
        "user_account",
        user.id,
        {"device_name": device.name},
    )
    await session.commit()
    events.publish("auth.setup", {"user_id": str(user.id), "device_id": str(device.id)})
    return Issued(device_token=device_token, session_token=session_token)


# --- Kopplung ----------------------------------------------------------------


async def create_pairing_code(
    session: AsyncSession,
    actor: Actor,
    settings: AuthSettings,
    events: EventHub,
    body: PairingCodeIn,
) -> PairingCodeOut:
    if body.default_role_id is not None:
        await _role_or_invalid(session, body.default_role_id)
    code = credentials.new_pairing_code()
    pairing = PairingCode(
        id=uuid.uuid4(),
        code_hash=credentials.token_hash(code),
        name=body.name,
        default_role_id=body.default_role_id,
        expires_at=now() + timedelta(minutes=settings.pairing_code_minutes),
    )
    session.add(pairing)
    record_audit(
        session,
        actor,
        "device.pairing_code_created",
        "pairing_code",
        pairing.id,
        {"name": body.name, "default_role_id": _str(body.default_role_id)},
    )
    await session.commit()
    events.publish("device.pairing_code_created", {"pairing_code_id": str(pairing.id)})
    return PairingCodeOut(
        code=code,
        pair_path=PAIR_PATH.format(code=code),
        expires_at=pairing.expires_at,
        name=pairing.name,
        default_role_id=pairing.default_role_id,
    )


async def pair(session: AsyncSession, events: EventHub, body: PairIn) -> Issued:
    code_hash = credentials.token_hash(credentials.normalize_pairing_code(body.code))
    pairing = await session.scalar(
        select(PairingCode)
        .where(
            PairingCode.code_hash == code_hash,
            PairingCode.used_at.is_(None),
            PairingCode.expires_at > now(),
        )
        .with_for_update()
    )
    if pairing is None:
        raise InvalidError(
            "Der Kopplungscode ist ungültig, abgelaufen oder wurde schon benutzt. "
            "Bitte einen neuen QR-Code erzeugen."
        )
    name = body.device_name or pairing.name
    if not name:
        raise InvalidError("Bitte einen Namen für das Gerät angeben.")
    token, device = _new_device(name, pairing.default_role_id)
    session.add(device)
    pairing.used_at = now()
    record_audit(
        session,
        Actor(device_id=device.id),
        "device.paired",
        "device",
        device.id,
        {"name": name, "pairing_code_id": str(pairing.id)},
    )
    await session.commit()
    events.publish("device.paired", {"device_id": str(device.id)})
    return Issued(device_token=token, session_token=None)


# --- Anmeldung ---------------------------------------------------------------


async def login_options(session: AsyncSession, identity: Identity) -> list[UserBrief]:
    if identity.device is None:
        raise UnauthorizedError(NOT_PAIRED)
    users = await session.scalars(
        select(UserAccount).where(UserAccount.active.is_(True)).order_by(UserAccount.name)
    )
    return [UserBrief(id=user.id, name=user.name) for user in users]


async def login(
    session: AsyncSession,
    identity: Identity,
    settings: AuthSettings,
    events: EventHub,
    body: LoginIn,
) -> Issued:
    device = identity.device
    if device is None:
        raise UnauthorizedError(NOT_PAIRED)
    user = await session.scalar(
        select(UserAccount)
        .where(UserAccount.id == body.user_id, UserAccount.active.is_(True))
        .with_for_update()
    )
    if user is not None and user.locked_until is not None and user.locked_until > now():
        raise _locked_error(user.locked_until)

    if not await credentials.verify_pin(user.pin_hash if user else None, body.pin):
        if user is None:
            raise UnauthorizedError(WRONG_PIN)
        await _register_failure(session, user, device, settings, events)
        if user.locked_until is not None:
            raise _locked_error(user.locked_until)
        raise UnauthorizedError(WRONG_PIN)

    user.failed_login_count = 0
    user.locked_until = None
    if identity.session is not None:
        await session.delete(identity.session)
    token, auth_session = _new_session(device, user, settings)
    session.add(auth_session)
    actor = Actor(user_id=user.id, device_id=device.id, user_name=user.name)
    record_audit(session, actor, "auth.login", "user_account", user.id)
    await session.commit()
    events.publish("auth.login", {"user_id": str(user.id), "device_id": str(device.id)})
    return Issued(device_token=None, session_token=token)


async def _register_failure(
    session: AsyncSession,
    user: UserAccount,
    device: Device,
    settings: AuthSettings,
    events: EventHub,
) -> None:
    user.failed_login_count += 1
    actor = Actor(device_id=device.id)
    locked = user.failed_login_count >= settings.max_failed_logins
    if locked:
        user.locked_until = now() + timedelta(minutes=settings.lockout_minutes)
        user.failed_login_count = 0
        record_audit(
            session,
            actor,
            "auth.locked",
            "user_account",
            user.id,
            {"minutes": settings.lockout_minutes},
        )
    else:
        record_audit(
            session,
            actor,
            "auth.login_failed",
            "user_account",
            user.id,
            {"failed_count": user.failed_login_count},
        )
    await session.commit()
    if locked:
        events.publish("user.locked", {"user_id": str(user.id)})


def _locked_error(locked_until: datetime) -> LockedError:
    seconds = (locked_until - now()).total_seconds()
    minutes = max(math.ceil(seconds / 60), 1)
    unit = "Minute" if minutes == 1 else "Minuten"
    return LockedError(
        f"Zu viele Fehlversuche. Die Anmeldung ist für {minutes} {unit} gesperrt.",
        math.ceil(seconds),
    )


async def logout(session: AsyncSession, identity: Identity, events: EventHub) -> None:
    if identity.session is None:
        return
    user_id, device_id = identity.session.user_id, identity.session.device_id
    record_audit(session, identity.actor(), "auth.logout", "user_account", user_id)
    await session.delete(identity.session)
    await session.commit()
    events.publish("auth.logout", {"user_id": str(user_id), "device_id": str(device_id)})


# --- Geräte ------------------------------------------------------------------


def _device_out(device: Device, current_device_id: uuid.UUID | None) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        name=device.name,
        paired_at=device.paired_at,
        last_seen_at=device.last_seen_at,
        default_role_id=device.default_role_id,
        blocked=device.blocked,
        is_current=device.id == current_device_id,
    )


async def list_devices(
    session: AsyncSession, current_device_id: uuid.UUID | None
) -> list[DeviceOut]:
    devices = await session.scalars(select(Device).order_by(Device.name, Device.paired_at))
    return [_device_out(device, current_device_id) for device in devices]


async def _get_device(session: AsyncSession, device_id: uuid.UUID) -> Device:
    device = await session.get(Device, device_id)
    if device is None:
        raise NotFoundError("Das Gerät gibt es nicht.")
    return device


async def update_device(
    session: AsyncSession,
    actor: Actor,
    events: EventHub,
    device_id: uuid.UUID,
    body: DeviceUpdateIn,
    current_device_id: uuid.UUID | None,
) -> DeviceOut:
    device = await _get_device(session, device_id)
    changes: dict[str, str | bool | None] = {}
    if body.name is not None and body.name != device.name:
        changes["name"] = body.name
        device.name = body.name
    if (
        "default_role_id" in body.model_fields_set
        and body.default_role_id != device.default_role_id
    ):
        if body.default_role_id is not None:
            await _role_or_invalid(session, body.default_role_id)
        changes["default_role_id"] = _str(body.default_role_id)
        device.default_role_id = body.default_role_id
    if body.blocked is not None and body.blocked != device.blocked:
        changes["blocked"] = body.blocked
        device.blocked = body.blocked
        if body.blocked:
            await session.execute(delete(AuthSession).where(AuthSession.device_id == device.id))
    if changes:
        action = "device.blocked" if changes.get("blocked") is True else "device.updated"
        record_audit(session, actor, action, "device", device.id, changes)
        await session.commit()
        events.publish("device.updated", {"device_id": str(device.id)})
    return _device_out(device, current_device_id)


async def delete_device(
    session: AsyncSession, actor: Actor, events: EventHub, device_id: uuid.UUID
) -> None:
    device = await _get_device(session, device_id)
    record_audit(session, actor, "device.deleted", "device", device.id, {"name": device.name})
    await session.delete(device)
    await session.commit()
    events.publish("device.deleted", {"device_id": str(device_id)})


# --- Rollen ------------------------------------------------------------------


def _clean_permissions(entries: list[str]) -> list[str]:
    cleaned: list[str] = []
    for entry in entries:
        value = entry.strip()
        if not permissions.PERMISSION_PATTERN.fullmatch(value):
            raise InvalidError(
                f"„{entry}“ ist keine gültige Berechtigung. Erlaubt sind Namen wie "
                "„club.edit“ oder Muster wie „person.*“ und „*“."
            )
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


async def _role_out(session: AsyncSession, role: Role) -> RoleOut:
    user_count = await session.scalar(select(func.count()).where(UserAccount.role_id == role.id))
    return RoleOut(
        id=role.id,
        name=role.name,
        is_system=role.is_system,
        permissions=role.permissions,
        effective_permissions=permissions.expand(role.permissions, is_system=role.is_system),
        user_count=user_count or 0,
    )


def list_permissions() -> list[PermissionOut]:
    return [
        PermissionOut(
            permission=item.permission, module=item.module, module_title=item.module_title
        )
        for item in permissions.known_permissions()
    ]


async def list_roles(session: AsyncSession) -> list[RoleOut]:
    roles = await session.scalars(select(Role).order_by(Role.is_system.desc(), Role.name))
    return [await _role_out(session, role) for role in roles]


async def _get_role(session: AsyncSession, role_id: uuid.UUID) -> Role:
    role = await session.get(Role, role_id)
    if role is None:
        raise NotFoundError("Die Rolle gibt es nicht.")
    return role


async def get_role(session: AsyncSession, role_id: uuid.UUID) -> RoleOut:
    return await _role_out(session, await _get_role(session, role_id))


async def create_role(
    session: AsyncSession, actor: Actor, events: EventHub, body: RoleIn
) -> RoleOut:
    await _ensure_unique_role_name(session, body.name)
    role = Role(id=uuid.uuid4(), name=body.name, permissions=_clean_permissions(body.permissions))
    session.add(role)
    record_audit(
        session,
        actor,
        "role.created",
        "role",
        role.id,
        {"name": role.name, "permissions": role.permissions},
    )
    await session.commit()
    events.publish("role.created", {"role_id": str(role.id)})
    return await _role_out(session, role)


async def update_role(
    session: AsyncSession, actor: Actor, events: EventHub, role_id: uuid.UUID, body: RoleUpdateIn
) -> RoleOut:
    role = await _get_role(session, role_id)
    changes: dict[str, object] = {}
    if body.name is not None and body.name != role.name:
        await _ensure_unique_role_name(session, body.name, exclude=role.id)
        changes["name"] = {"before": role.name, "after": body.name}
        role.name = body.name
    if body.permissions is not None:
        cleaned = _clean_permissions(body.permissions)
        if cleaned != role.permissions:
            if role.is_system:
                raise ConflictError(
                    f"Die Rolle „{role.name}“ hat immer alle Rechte und lässt sich nicht "
                    "einschränken."
                )
            changes["permissions"] = {"before": role.permissions, "after": cleaned}
            role.permissions = cleaned
    if changes:
        record_audit(session, actor, "role.updated", "role", role.id, changes)
        await session.commit()
        events.publish("role.updated", {"role_id": str(role.id)})
    return await _role_out(session, role)


async def delete_role(
    session: AsyncSession, actor: Actor, events: EventHub, role_id: uuid.UUID
) -> None:
    role = await _get_role(session, role_id)
    if role.is_system:
        raise ConflictError(f"Die Systemrolle „{role.name}“ kann nicht gelöscht werden.")
    user_count = await session.scalar(select(func.count()).where(UserAccount.role_id == role.id))
    if user_count:
        people = "Person" if user_count == 1 else "Personen"
        raise ConflictError(
            f"Die Rolle „{role.name}“ ist noch {user_count} {people} zugewiesen. "
            "Bitte diesen Personen zuerst eine andere Rolle geben."
        )
    record_audit(session, actor, "role.deleted", "role", role.id, {"name": role.name})
    await session.delete(role)
    await session.commit()
    events.publish("role.deleted", {"role_id": str(role_id)})


# --- Personen ----------------------------------------------------------------


def _user_out(user: UserAccount) -> UserOut:
    locked = user.locked_until if user.locked_until and user.locked_until > now() else None
    return UserOut(
        id=user.id,
        name=user.name,
        role_id=user.role_id,
        active=user.active,
        locked_until=locked,
        created_at=user.created_at,
    )


async def list_users(session: AsyncSession) -> list[UserOut]:
    users = await session.scalars(select(UserAccount).order_by(UserAccount.name))
    return [_user_out(user) for user in users]


async def _get_user(
    session: AsyncSession, user_id: uuid.UUID, *, lock: bool = False
) -> UserAccount:
    statement = select(UserAccount).where(UserAccount.id == user_id)
    if lock:
        statement = statement.with_for_update()
    user = await session.scalar(statement)
    if user is None:
        raise NotFoundError("Die Person gibt es nicht.")
    return user


async def create_user(
    session: AsyncSession, actor: Actor, settings: AuthSettings, events: EventHub, body: UserIn
) -> UserOut:
    _check_pin(body.pin, settings)
    await _role_or_invalid(session, body.role_id)
    await _ensure_unique_user_name(session, body.name)
    user = UserAccount(
        id=uuid.uuid4(),
        name=body.name,
        pin_hash=await credentials.hash_pin(body.pin),
        role_id=body.role_id,
    )
    session.add(user)
    record_audit(
        session,
        actor,
        "user.created",
        "user_account",
        user.id,
        {"name": user.name, "role_id": str(user.role_id)},
    )
    await session.commit()
    await session.refresh(user)
    events.publish("user.created", {"user_id": str(user.id)})
    return _user_out(user)


async def update_user(
    session: AsyncSession, actor: Actor, events: EventHub, user_id: uuid.UUID, body: UserUpdateIn
) -> UserOut:
    admin_role = await _admin_role(session, lock=True)
    user = await _get_user(session, user_id, lock=True)
    changes: dict[str, object] = {}
    if body.name is not None and body.name != user.name:
        await _ensure_unique_user_name(session, body.name, exclude=user.id)
        changes["name"] = body.name
        user.name = body.name

    was_admin = user.active and user.role_id == admin_role.id
    if body.role_id is not None and body.role_id != user.role_id:
        await _role_or_invalid(session, body.role_id)
        changes["role_id"] = {"before": str(user.role_id), "after": str(body.role_id)}
        user.role_id = body.role_id
    if body.active is not None and body.active != user.active:
        changes["active"] = body.active
        user.active = body.active
    is_admin = user.active and user.role_id == admin_role.id
    if was_admin and not is_admin:
        await session.flush()
        if await _active_admin_count(session, admin_role) == 0:
            raise ConflictError(LAST_ADMIN)
    if body.active is False:
        await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))

    if changes:
        action = "user.role_changed" if "role_id" in changes else "user.updated"
        record_audit(session, actor, action, "user_account", user.id, changes)
        await session.commit()
        events.publish("user.updated", {"user_id": str(user.id)})
    return _user_out(user)


async def reset_pin(
    session: AsyncSession,
    actor: Actor,
    settings: AuthSettings,
    events: EventHub,
    user_id: uuid.UUID,
    pin: str,
) -> UserOut:
    _check_pin(pin, settings)
    user = await _get_user(session, user_id, lock=True)
    user.pin_hash = await credentials.hash_pin(pin)
    user.failed_login_count = 0
    user.locked_until = None
    # Wer mit der alten PIN angemeldet ist, wird abgemeldet.
    await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    record_audit(session, actor, "user.pin_reset", "user_account", user.id)
    await session.commit()
    events.publish("user.updated", {"user_id": str(user.id)})
    return _user_out(user)


def _str(value: uuid.UUID | None) -> str | None:
    return str(value) if value is not None else None
