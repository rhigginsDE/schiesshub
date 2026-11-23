"""Serverinterne Anmeldestellen des Turnier-Moduls für andere Module.

So hängt `turnier` nicht von Modulen ab, die auf ihm aufbauen (`starts`, `ergebnisse`):

- **Löschprüfer** werden gefragt, bevor ein Turnier, Schießstand, eine Klasse oder ein Wettbewerb
  gelöscht wird. Ein Prüfer liefert einen deutschen Satz, warum es nicht geht, oder None.
- **Definitionsänderung**: Nach jeder neuen Revision der wertungsrelevanten Felder werden die
  Callbacks in derselben Transaktion aufgerufen (die Revision ist dann schon geschrieben, aber
  noch nicht bestätigt). Wirft ein Callback, wird die ganze Änderung verworfen.

Beide melden sich üblicherweise im `on_startup` ihres Moduls an. Für Clients gibt es weiterhin
das Ereignis `competition.definition_changed` über den EventHub.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Actor

DeletionTarget = Literal["tournament", "range", "class", "competition"]
DeletionCheck = Callable[[AsyncSession, DeletionTarget, uuid.UUID], Awaitable[str | None]]
DefinitionChanged = Callable[[AsyncSession, uuid.UUID, int, Actor], Awaitable[None]]

_deletion_checks: list[DeletionCheck] = []
_definition_changed: list[DefinitionChanged] = []


def register_deletion_check(check: DeletionCheck) -> None:
    if check not in _deletion_checks:
        _deletion_checks.append(check)


def unregister_deletion_check(check: DeletionCheck) -> None:
    if check in _deletion_checks:
        _deletion_checks.remove(check)


async def deletion_blockers(
    session: AsyncSession, target: DeletionTarget, item_id: uuid.UUID
) -> list[str]:
    """Alle Gründe gegen das Löschen; leer heißt: darf gelöscht werden."""
    reasons: list[str] = []
    for check in _deletion_checks:
        reason = await check(session, target, item_id)
        if reason:
            reasons.append(reason)
    return reasons


def register_definition_changed(callback: DefinitionChanged) -> None:
    if callback not in _definition_changed:
        _definition_changed.append(callback)


def unregister_definition_changed(callback: DefinitionChanged) -> None:
    if callback in _definition_changed:
        _definition_changed.remove(callback)


async def notify_definition_changed(
    session: AsyncSession, competition_id: uuid.UUID, revision: int, actor: Actor
) -> None:
    for callback in list(_definition_changed):
        await callback(session, competition_id, revision, actor)
