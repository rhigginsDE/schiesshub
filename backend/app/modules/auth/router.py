"""HTTP-Schnittstelle: /auth, /devices, /roles, /users, /audit.

Alle schreibenden Anfragen brauchen den Header `X-Schiesshub-Request` (CSRF-Schutz, siehe
`identity.py`), unabhängig davon, ob AUTH_ENFORCED gesetzt ist.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.core.db import SessionDep
from app.core.errors import CodedErrorOut
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
    unpaired,
)
from app.modules.auth.schemas import (
    AuditActionOut,
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


def authorized_any(*permissions: str) -> Callable[..., Awaitable[Actor]]:
    """Wie `authorized`, aber eine der Berechtigungen genügt (die erste passende gilt)."""

    async def dependency(request: Request, identity: IdentityDep) -> Actor:
        refused: HTTPException | None = None
        for permission in permissions:
            try:
                actor = await require(permission)(request)
            except HTTPException as exc:
                refused = refused or exc
                continue
            return actor if actor.device_id is not None else identity.actor()
        assert refused is not None
        raise refused

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
    responses={401: {"model": CodedErrorOut, "description": "Gerät nicht gekoppelt oder gesperrt"}},
)
async def login_options(session: SessionDep, identity: IdentityDep) -> list[UserBrief]:
    return await service.login_options(session, identity)


@auth_router.post(
    "/login",
    summary="Mit PIN anmelden",
    responses={
        401: {
            "model": CodedErrorOut,
            "description": "Gerät nicht gekoppelt oder gesperrt, oder PIN falsch",
        },
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


@auth_router.get(
    "/permissions",
    summary="Alle bekannten Berechtigungen aller Module",
    description=(
        "Für jedes gekoppelte Gerät lesbar, auch ohne angemeldete Person: Die Namen sind nicht "
        "geheim, die Oberfläche braucht sie, um Stationen freizugeben. `requires` nennt je "
        "Berechtigung die, ohne die sie an ihrer Station praktisch nichts nützt."
    ),
    responses={401: {"model": CodedErrorOut, "description": "Gerät nicht gekoppelt oder gesperrt"}},
)
async def list_permissions(identity: IdentityDep, settings: SettingsDep) -> list[PermissionOut]:
    if settings.enforced and identity.device is None:
        raise unpaired(identity)
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
    request: Request,
    actor: DeviceManager,
    session: SessionDep,
    settings: SettingsDep,
    events: EventHubDep,
) -> PairingCodeOut:
    created = await service.create_pairing_code(session, actor, settings, events, body)
    configured = getattr(request.app.state.settings, "public_base_url", "")
    created.server_urls = server_urls(configured, request)
    return created


def server_urls(configured: str, request: Request) -> list[str]:
    """Adressen für den Kopplungs-QR-Code: die eingestellten (`PUBLIC_BASE_URL`, mit Komma
    getrennt) oder die Herkunft der Anfrage, wie der Proxy sie weiterreicht. Keine
    Netzwerk-Erkundung."""
    urls = [url.strip().rstrip("/") for url in configured.split(",") if url.strip()]
    if urls:
        return urls
    headers = request.headers
    host = (headers.get("x-forwarded-host") or headers.get("host") or "").split(",")[0].strip()
    if not host:
        return []
    proto = (headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    return [f"{proto}://{host}"]


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
# Die Rollenliste braucht auch, wer Personen verwaltet (Auswahl der Rolle).
RoleReader = Annotated[Actor, Depends(authorized_any("role.manage", "user.manage"))]


@roles_router.get(
    "",
    summary="Rollen",
    description="Lesen mit `role.manage` oder `user.manage`; ändern nur mit `role.manage`.",
)
async def list_roles(_actor: RoleReader, session: SessionDep) -> list[RoleOut]:
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


AuditReader = Annotated[Actor, Depends(authorized("system.manage"))]


@audit_router.get(
    "",
    summary="Audit-Protokoll, neueste zuerst",
    description=(
        "Mit den heutigen Namen von Person und Gerät (gelöscht: null) und einem deutschen "
        "Kurztext je Aktion. Filter: Zeitraum `since` (einschließlich) bis `until` "
        "(ausschließlich), Person `user_id`, Gerät `device_id`, Aktion `action` als Name "
        "(`role.updated`) oder Bereich (`role.*`)."
    ),
)
async def list_audit(
    _actor: AuditReader,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    since: datetime | None = None,
    until: datetime | None = None,
    user_id: UUID | None = None,
    device_id: UUID | None = None,
    action: Annotated[str | None, Query(max_length=80)] = None,
) -> AuditPageOut:
    filters = audit.AuditFilter(
        since=since, until=until, user_id=user_id, device_id=device_id, action=action
    )
    total, rows = await audit.list_audit(session, limit, offset, filters)
    return AuditPageOut(
        items=[
            AuditEntryOut(
                id=row.entry.id,
                at=row.entry.at,
                user_id=row.entry.user_id,
                user_name=row.user_name,
                device_id=row.entry.device_id,
                device_name=row.device_name,
                action=row.entry.action,
                action_text=audit.action_text(row.entry.action),
                entity=row.entry.entity,
                entity_id=row.entry.entity_id,
                details=row.entry.details,
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@audit_router.get("/actions", summary="Aktionen mit Kurztext (für den Filter)")
async def list_audit_actions(_actor: AuditReader, session: SessionDep) -> list[AuditActionOut]:
    return [
        AuditActionOut(action=action, action_text=text)
        for action, text in await audit.known_actions(session)
    ]


for _sub in (auth_router, devices_router, roles_router, users_router, audit_router):
    router.include_router(_sub)
