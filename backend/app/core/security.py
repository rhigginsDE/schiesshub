"""Berechtigungsprüfung für Endpunkte.

Jeder schreibende oder schützenswerte Endpunkt hängt `Depends(require("bereich.aktion"))` an.
Solange das Modul `auth` noch nicht eingebunden ist, lässt der Prüfer alles durch. Das Modul
`auth` ersetzt ihn beim Start über `set_permission_checker`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request


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


# Name, mit dem `require_paired` beim Prüfer anfragt. Keine echte Berechtigung: Gewährt wird er
# nur über `*`; allen anderen fehlt er, und genau das zeigt, dass das Gerät erkannt wurde.
PAIRED_PROBE = "device.paired"
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# 401-Codes des Prüfers, bei denen das Gerät gekoppelt ist und nur niemand angemeldet ist.
_PAIRED_WITHOUT_LOGIN = frozenset({"login_required", "session_expired"})


def require_paired() -> Callable[[Request], Awaitable[Actor]]:
    """FastAPI-Abhängigkeit für lesende Endpunkte: jedes gekoppelte, nicht gesperrte Gerät.

    Kein bestimmtes Recht nötig – auch ein Gerät mit Standardrolle ohne angemeldete Person oder
    ohne jede Rolle kommt durch. Ohne Berechtigungsprüfung (offener Prüfer) ist alles offen.

    Der Prüfer kennt nur Berechtigungen; gefragt wird deshalb nach `PAIRED_PROBE`. Antwortet er
    mit 403 (Recht fehlt) oder mit 401 `login_required`/`session_expired`, hat er das Gerät
    erkannt – das genügt hier. Andere 401 (nicht gekoppelt, gesperrt) gehen unverändert durch.
    Schreibende Anfragen prüft er streng, denn dort steckt im 403 auch der CSRF-Schutz.
    """

    async def dependency(request: Request) -> Actor:
        if request.method not in _READ_METHODS:
            return await _checker(request, PAIRED_PROBE)
        try:
            return await _checker(request, PAIRED_PROBE)
        except HTTPException as exc:
            paired = exc.status_code == 403 or (
                exc.status_code == 401 and getattr(exc, "code", None) in _PAIRED_WITHOUT_LOGIN
            )
            if not paired:
                raise
            return Actor()

    return dependency
