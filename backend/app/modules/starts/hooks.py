"""Serverinterne Anmeldestellen des Moduls `starts` für Module, die auf ihm aufbauen.

So hängt `starts` nicht von `ergebnisse` ab (Muster wie `app.modules.turnier.hooks`):

- **Ergebnisprüfer** bekommen eine Liste von Start-IDs und liefern die, zu denen es Ergebnis-Daten
  gibt (etwa Einträge im Ergebnisprotokoll, auch einen Abbruch „nicht angetreten“). Solche Starts
  lassen sich weder stornieren noch mit ihrer Anmeldung löschen.
- **Abbruch-Handler** (höchstens einer): Ist er angemeldet, übernimmt er
  `POST …/starts/{start_id}/abort` vollständig – Statuswechsel über `lifecycle.transition`,
  eigener Protokolleintrag, Commit und Ereignisse. So steht ein Abbruch immer im
  Ergebnisprotokoll, egal über welchen Endpunkt er kam. Ohne Handler wechselt `starts` nur den
  Status.

Beide melden sich üblicherweise im `on_startup` ihres Moduls an und im `on_shutdown` ab.
"""

import uuid
from collections.abc import Awaitable, Callable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import EventHub
from app.core.security import Actor
from app.modules.starts.rules import AbortReason

ResultCheck = Callable[[AsyncSession, Sequence[uuid.UUID]], Awaitable[set[uuid.UUID]]]
# (session, events, actor, tournament_id, start_id, abort_reason); committet selbst.
AbortHandler = Callable[
    [AsyncSession, EventHub, Actor, uuid.UUID, uuid.UUID, AbortReason], Awaitable[None]
]

_result_checks: list[ResultCheck] = []
_abort_handler: list[AbortHandler] = []


def register_result_check(check: ResultCheck) -> None:
    if check not in _result_checks:
        _result_checks.append(check)


def unregister_result_check(check: ResultCheck) -> None:
    if check in _result_checks:
        _result_checks.remove(check)


async def starts_with_results(
    session: AsyncSession, start_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    """Die Starts aus `start_ids`, zu denen ein angemeldetes Modul Ergebnis-Daten hat."""
    found: set[uuid.UUID] = set()
    if not start_ids:
        return found
    for check in list(_result_checks):
        found |= await check(session, start_ids)
    return found


def register_abort_handler(handler: AbortHandler) -> None:
    """Meldet den Abbruch-Handler an; ein zuvor angemeldeter wird ersetzt."""
    _abort_handler[:] = [handler]


def unregister_abort_handler(handler: AbortHandler) -> None:
    if handler in _abort_handler:
        _abort_handler.remove(handler)


def abort_handler() -> AbortHandler | None:
    return _abort_handler[0] if _abort_handler else None
