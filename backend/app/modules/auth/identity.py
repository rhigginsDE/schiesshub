"""Wer fragt an? Cookies lesen und setzen, Gerät und Sitzung auflösen, Berechtigung prüfen.

Zwei Cookies, beide HttpOnly und SameSite=Lax:
- `schiesshub_device`: langlebiges Geräte-Token, gesetzt bei der Kopplung.
- `schiesshub_session`: Sitzung einer Person auf diesem Gerät, gesetzt bei der Anmeldung.

CSRF-Schutz: Schreibende Anfragen (alles außer GET, HEAD, OPTIONS) müssen den Header
`X-Schiesshub-Request` mitschicken. Ein fremder Browser-Tab kann diesen Header nur nach einer
CORS-Vorabprüfung setzen, und die lässt nur die eingestellten Herkünfte zu. Das funktioniert auch
im lokalen Netz ohne HTTPS und ohne Token-Austausch.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory
from app.core.security import Actor
from app.modules.auth import permissions
from app.modules.auth.credentials import token_hash
from app.modules.auth.errors import ForbiddenError, UnauthorizedError
from app.modules.auth.models import AuthSession, Device, Role, UserAccount
from app.modules.auth.settings import AuthSettings, get_auth_settings

DEVICE_COOKIE = "schiesshub_device"
SESSION_COOKIE = "schiesshub_session"
CSRF_HEADER = "X-Schiesshub-Request"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Das Geräte-Cookie gilt praktisch unbegrenzt; gesperrt wird über die Datenbank.
DEVICE_COOKIE_MAX_AGE = 10 * 365 * 24 * 3600
# last_seen_at und Sitzungsende werden höchstens so oft geschrieben.
TOUCH_INTERVAL = timedelta(minutes=1)


def now() -> datetime:
    return datetime.now(UTC)


# --- Cookies und CSRF --------------------------------------------------------


def _secure(request: Request, settings: AuthSettings) -> bool:
    if settings.cookie_secure == "always":
        return True
    if settings.cookie_secure == "never":
        return False
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def set_cookie(
    response: Response, request: Request, name: str, value: str, max_age: int | None
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_secure(request, get_auth_settings(request)),
    )


def clear_cookie(response: Response, request: Request, name: str) -> None:
    response.delete_cookie(
        name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_secure(request, get_auth_settings(request)),
    )


def check_csrf(request: Request) -> None:
    if request.method not in SAFE_METHODS and not request.headers.get(CSRF_HEADER):
        raise ForbiddenError(
            f"Die Anfrage wurde abgelehnt, weil der Header „{CSRF_HEADER}“ fehlt. "
            "Bitte die Seite neu laden."
        )


# --- Auflösen ----------------------------------------------------------------


@dataclass(slots=True)
class Identity:
    device: Device | None = None
    session: AuthSession | None = None
    user: UserAccount | None = None
    # Rolle der angemeldeten Person, sonst die Standardrolle des Geräts.
    role: Role | None = None
    permissions: list[str] = field(default_factory=list)

    def actor(self) -> Actor:
        return Actor(
            user_id=self.user.id if self.user else None,
            device_id=self.device.id if self.device else None,
            user_name=self.user.name if self.user else None,
            permissions=frozenset(self.permissions),
        )

    def grants(self, permission: str) -> bool:
        if self.role is None:
            return False
        return self.role.is_system or permissions.grants(self.role.permissions, permission)


async def resolve_request(
    session: AsyncSession, request: Request, settings: AuthSettings, *, touch: bool
) -> Identity:
    """Löst Gerät und Sitzung aus den Cookies der Anfrage auf."""
    return await resolve(
        session,
        settings,
        request.cookies.get(DEVICE_COOKIE),
        request.cookies.get(SESSION_COOKIE),
        touch=touch,
    )


async def resolve(
    session: AsyncSession,
    settings: AuthSettings,
    device_token: str | None,
    session_token: str | None,
    *,
    touch: bool,
) -> Identity:
    """Löst Gerät und Sitzung zu den Token auf. Mit `touch` werden Zeitstempel gepflegt."""
    identity = Identity()
    if not device_token:
        return identity
    device = await session.scalar(
        select(Device).where(
            Device.token_hash == token_hash(device_token), Device.blocked.is_(False)
        )
    )
    if device is None:
        return identity
    identity.device = device
    current = now()

    if session_token:
        row = (
            await session.execute(
                select(AuthSession, UserAccount, Role)
                .join(UserAccount, UserAccount.id == AuthSession.user_id)
                .join(Role, Role.id == UserAccount.role_id)
                .where(
                    AuthSession.token_hash == token_hash(session_token),
                    AuthSession.device_id == device.id,
                    AuthSession.expires_at > current,
                    UserAccount.active.is_(True),
                )
            )
        ).first()
        if row is not None:
            identity.session, identity.user, identity.role = row

    if identity.role is None and device.default_role_id is not None:
        identity.role = await session.get(Role, device.default_role_id)

    if identity.role is not None:
        identity.permissions = permissions.expand(
            identity.role.permissions, is_system=identity.role.is_system
        )

    if touch:
        changed = False
        if device.last_seen_at is None or current - device.last_seen_at >= TOUCH_INTERVAL:
            device.last_seen_at = current
            changed = True
        if identity.session is not None:
            renewed = current + timedelta(hours=settings.session_idle_hours)
            if renewed - identity.session.expires_at >= TOUCH_INTERVAL:
                identity.session.expires_at = renewed
                changed = True
        if changed:
            await session.commit()
    return identity


# --- Prüfer ------------------------------------------------------------------


async def check_permission(request: Request, permission: str) -> Actor:
    """Echter Prüfer für `app.core.security.require`. Wird nur bei AUTH_ENFORCED registriert."""
    check_csrf(request)
    settings = get_auth_settings(request)
    session_factory: SessionFactory = request.app.state.session_factory
    async with session_factory() as session:
        identity = await resolve_request(session, request, settings, touch=True)
    if identity.device is None:
        raise UnauthorizedError(
            "Dieses Gerät ist nicht gekoppelt oder wurde gesperrt. "
            "Bitte das Gerät über einen QR-Code neu koppeln."
        )
    if identity.role is None:
        raise UnauthorizedError("Bitte zuerst mit der PIN anmelden.")
    if not identity.grants(permission):
        raise ForbiddenError(f"Dafür fehlt die Berechtigung „{permission}“.")
    actor = identity.actor()
    # Auch eine Berechtigung, die kein Manifest führt, aber über ein Muster gewährt ist.
    return replace(actor, permissions=actor.permissions | {permission})
