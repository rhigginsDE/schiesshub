"""HTTP-Schnittstelle: /auth, /devices, /roles, /users, /audit.

Alle schreibenden Anfragen brauchen den Header `X-Schiesshub-Request` (CSRF-Schutz, siehe
`identity.py`), unabhängig davon, ob AUTH_ENFORCED gesetzt ist.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.db import SessionDep
from app.core.events import EventHubDep
from app.core.security import Actor, require
from app.modules.auth import audit, service
from app.modules.auth.identity import (
    DEVICE_COOKIE,
    DEVICE_COOKIE_MAX_AGE,
    SESSION_COOKIE,
    Identity,
    check_csrf,
    clear_cookie,
    resolve,
    resolve_request,
    set_cookie,
)
from app.modules.auth.schemas import (
    AuditEntryOut,
    AuditPageOut,
    DeviceOut,
    DeviceUpdateIn,
    LoginIn,
    PairIn,
    PairingCodeIn,
    PairingCodeOut,
    PermissionOut,
    PinResetIn,
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
from app.modules.auth.settings import AuthSettings, get_auth_settings

SettingsDep = Annotated[AuthSettings, Depends(get_auth_settings)]


async def current_identity(
    request: Request, session: SessionDep, settings: SettingsDep
) -> Identity:
    return await resolve_request(session, request, settings, touch=True)


IdentityDep = Annotated[Identity, Depends(current_identity)]


def authorized(permission: str) -> Callable[..., Awaitable[Actor]]:
    """`require(...)` mit Rückfall für das Audit: Ist der offene Prüfer aktiv (AUTH_ENFORCED aus),
    wird der Handelnde trotzdem aus den Cookies bestimmt, soweit vorhanden."""

    async def dependency(
        identity: IdentityDep, actor: Annotated[Actor, Depends(require(permission))]
    ) -> Actor:
        return actor if actor.device_id is not None else identity.actor()

    return dependency


async def _issue(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: AuthSettings,
    issued: service.Issued,
) -> StatusOut:
    """Setzt die neuen Cookies und liefert den Status, wie er mit ihnen aussieht."""
    if issued.device_token is not None:
        set_cookie(response, request, DEVICE_COOKIE, issued.device_token, DEVICE_COOKIE_MAX_AGE)
    if issued.session_token is not None:
        # Ohne Ablaufdatum; das Ende bestimmt der Server (Inaktivität).
        set_cookie(response, request, SESSION_COOKIE, issued.session_token, None)
    identity = await resolve(
        session,
        settings,
        issued.device_token or request.cookies.get(DEVICE_COOKIE),
        issued.session_token or request.cookies.get(SESSION_COOKIE),
        touch=False,
    )
    return await service.get_status(session, identity, settings)


router = APIRouter(dependencies=[Depends(check_csrf)])

# --- /auth -------------------------------------------------------------------

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.get("/status", summary="Ersteinrichtung, Gerät, angemeldete Person, Rechte")
async def get_status(
    session: SessionDep, identity: IdentityDep, settings: SettingsDep
) -> StatusOut:
    return await service.get_status(session, identity, settings)


@auth_router.post(
    "/setup",
    summary="Ersten Administrator anlegen und dieses Gerät koppeln",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"description": "Ersteinrichtung bereits erfolgt"}},
)
async def setup(
    body: SetupIn,
    request: Request,
    response: Response,
    session: SessionDep,
    identity: IdentityDep,
    settings: SettingsDep,
    events: EventHubDep,
) -> StatusOut:
    issued = await service.setup(session, identity, settings, events, body)
    return await _issue(request, response, session, settings, issued)


@auth_router.post(
    "/pair",
    summary="Gerät mit einem Kopplungscode koppeln",
    status_code=status.HTTP_201_CREATED,
    responses={422: {"description": "Code ungültig, abgelaufen oder benutzt"}},
)
async def pair(
    body: PairIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    events: EventHubDep,
) -> StatusOut:
    issued = await service.pair(session, events, body)
    # Eine Sitzung eines früher gekoppelten Geräts gilt hier nicht mehr.
    clear_cookie(response, request, SESSION_COOKIE)
    return await _issue(request, response, session, settings, issued)


@auth_router.get(
    "/users",
    summary="Aktive Personen zur Auswahl bei der Anmeldung",
    responses={401: {"description": "Gerät nicht gekoppelt"}},
)
async def login_options(session: SessionDep, identity: IdentityDep) -> list[UserBrief]:
    return await service.login_options(session, identity)


@auth_router.post(
    "/login",
    summary="Mit PIN anmelden",
    responses={
        401: {"description": "Gerät nicht gekoppelt oder PIN falsch"},
        429: {"description": "Zu viele Fehlversuche, vorübergehend gesperrt"},
    },
)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    session: SessionDep,
    identity: IdentityDep,
    settings: SettingsDep,
    events: EventHubDep,
) -> StatusOut:
    issued = await service.login(session, identity, settings, events, body)
    return await _issue(request, response, session, settings, issued)


@auth_router.post("/logout", summary="Abmelden", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, session: SessionDep, identity: IdentityDep, events: EventHubDep
) -> Response:
    await service.logout(session, identity, events)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_cookie(response, request, SESSION_COOKIE)
    return response


@auth_router.get("/permissions", summary="Alle bekannten Berechtigungen aller Module")
async def list_permissions(
    _actor: Annotated[Actor, Depends(authorized("role.manage"))],
) -> list[PermissionOut]:
    return service.list_permissions()


# --- /devices ----------------------------------------------------------------

devices_router = APIRouter(prefix="/devices", tags=["devices"])
DeviceManager = Annotated[Actor, Depends(authorized("device.manage"))]


@devices_router.post(
    "/pairing-codes",
    summary="Einmaligen Kopplungscode für ein neues Gerät erzeugen",
    status_code=status.HTTP_201_CREATED,
)
async def create_pairing_code(
    body: PairingCodeIn,
    actor: DeviceManager,
    session: SessionDep,
    settings: SettingsDep,
    events: EventHubDep,
) -> PairingCodeOut:
    return await service.create_pairing_code(session, actor, settings, events, body)


@devices_router.get("", summary="Gekoppelte Geräte")
async def list_devices(
    _actor: DeviceManager, session: SessionDep, identity: IdentityDep
) -> list[DeviceOut]:
    return await service.list_devices(session, identity.device.id if identity.device else None)


@devices_router.patch("/{device_id}", summary="Gerät umbenennen, Standardrolle setzen, sperren")
async def update_device(
    device_id: UUID,
    body: DeviceUpdateIn,
    actor: DeviceManager,
    session: SessionDep,
    identity: IdentityDep,
    events: EventHubDep,
) -> DeviceOut:
    current = identity.device.id if identity.device else None
    return await service.update_device(session, actor, events, device_id, body, current)


@devices_router.delete(
    "/{device_id}", summary="Gerät entfernen", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_device(
    device_id: UUID, actor: DeviceManager, session: SessionDep, events: EventHubDep
) -> None:
    await service.delete_device(session, actor, events, device_id)


# --- /roles ------------------------------------------------------------------

roles_router = APIRouter(prefix="/roles", tags=["roles"])
RoleManager = Annotated[Actor, Depends(authorized("role.manage"))]


@roles_router.get("", summary="Rollen")
async def list_roles(_actor: RoleManager, session: SessionDep) -> list[RoleOut]:
    return await service.list_roles(session)


@roles_router.post("", summary="Rolle anlegen", status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleIn, actor: RoleManager, session: SessionDep, events: EventHubDep
) -> RoleOut:
    return await service.create_role(session, actor, events, body)


@roles_router.get("/{role_id}", summary="Rolle")
async def get_role(role_id: UUID, _actor: RoleManager, session: SessionDep) -> RoleOut:
    return await service.get_role(session, role_id)


@roles_router.patch("/{role_id}", summary="Rolle umbenennen oder Rechte ändern")
async def update_role(
    role_id: UUID, body: RoleUpdateIn, actor: RoleManager, session: SessionDep, events: EventHubDep
) -> RoleOut:
    return await service.update_role(session, actor, events, role_id, body)


@roles_router.delete("/{role_id}", summary="Rolle löschen", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID, actor: RoleManager, session: SessionDep, events: EventHubDep
) -> None:
    await service.delete_role(session, actor, events, role_id)


# --- /users ------------------------------------------------------------------

users_router = APIRouter(prefix="/users", tags=["users"])
UserManager = Annotated[Actor, Depends(authorized("user.manage"))]


@users_router.get("", summary="Personen mit Zugang")
async def list_users(_actor: UserManager, session: SessionDep) -> list[UserOut]:
    return await service.list_users(session)


@users_router.post("", summary="Person anlegen", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserIn,
    actor: UserManager,
    session: SessionDep,
    settings: SettingsDep,
    events: EventHubDep,
) -> UserOut:
    return await service.create_user(session, actor, settings, events, body)


@users_router.patch("/{user_id}", summary="Person umbenennen, Rolle ändern, (de)aktivieren")
async def update_user(
    user_id: UUID, body: UserUpdateIn, actor: UserManager, session: SessionDep, events: EventHubDep
) -> UserOut:
    return await service.update_user(session, actor, events, user_id, body)


@users_router.post("/{user_id}/pin", summary="PIN zurücksetzen (hebt auch eine Sperre auf)")
async def reset_pin(
    user_id: UUID,
    body: PinResetIn,
    actor: UserManager,
    session: SessionDep,
    settings: SettingsDep,
    events: EventHubDep,
) -> UserOut:
    return await service.reset_pin(session, actor, settings, events, user_id, body.pin)


# --- /audit ------------------------------------------------------------------

audit_router = APIRouter(prefix="/audit", tags=["audit"])


@audit_router.get("", summary="Audit-Protokoll, neueste zuerst")
async def list_audit(
    _actor: Annotated[Actor, Depends(authorized("system.manage"))],
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPageOut:
    total, entries = await audit.list_audit(session, limit, offset)
    return AuditPageOut(
        items=[AuditEntryOut.model_validate(entry, from_attributes=True) for entry in entries],
        total=total,
        limit=limit,
        offset=offset,
    )


for _sub in (auth_router, devices_router, roles_router, users_router, audit_router):
    router.include_router(_sub)
