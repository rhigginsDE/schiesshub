"""Berechtigungsprüfung für Endpunkte.

Jeder schreibende oder schützenswerte Endpunkt hängt `Depends(require("bereich.aktion"))` an.
Solange das Modul `auth` noch nicht eingebunden ist, lässt der Prüfer alles durch. Das Modul
`auth` ersetzt ihn beim Start über `set_permission_checker`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Request


@dataclass(frozen=True, slots=True)
class Actor:
    """Wer eine Anfrage stellt. Wird in Ereignis- und Audit-Protokollen festgehalten."""

    user_id: UUID | None = None
    device_id: UUID | None = None
    user_name: str | None = None
    permissions: frozenset[str] = frozenset()


PermissionChecker = Callable[[Request, str], Awaitable[Actor]]


async def _allow_all(request: Request, permission: str) -> Actor:
    return Actor()


_checker: PermissionChecker = _allow_all


def set_permission_checker(checker: PermissionChecker) -> None:
    global _checker
    _checker = checker


def reset_permission_checker() -> None:
    """Für Tests: zurück zum offenen Prüfer."""
    global _checker
    _checker = _allow_all


def require(permission: str) -> Callable[[Request], Awaitable[Actor]]:
    """FastAPI-Abhängigkeit: verlangt die Berechtigung und liefert den Handelnden."""

    async def dependency(request: Request) -> Actor:
        return await _checker(request, permission)

    return dependency
