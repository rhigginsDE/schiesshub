"""Modul `ergebnisse`: Erfassung, unveränderliches Ereignisprotokoll, Wertung, Ranglisten.

Öffentliche Schnittstelle für andere Module: `recompute_competition(session, competition_id,
actor)` (rechnet alle Ergebnisse eines Wettbewerbs aus den Ereignissen neu, ohne zu bestätigen)
und `abort_remarks(session, start_ids)` (Bemerkung zum Abbruch je Start, nur für die Bedienung).
Bei einer neuen Revision der Wertung läuft sie automatisch über `turnier.hooks`.

Bei `starts.hooks` meldet sich das Modul dreimal an: als Ergebnisprüfer (Starts mit Ereignissen
lassen sich nicht stornieren oder mit ihrer Anmeldung löschen), als Abbruch-Handler (auch
`POST …/starts/{id}/abort` schreibt das Ereignis `aborted`) und als Fortschritt-Lieferant (die
Sichten am Stand zeigen je Bahn, wie weit erfasst ist).
"""

from fastapi import FastAPI

from app.core.events import register_event_names
from app.core.module import ModuleManifest
from app.modules.ergebnisse import models  # noqa: F401  (registriert die Tabellen)
from app.modules.ergebnisse.progress import lane_progress
from app.modules.ergebnisse.recompute import on_definition_changed, recompute_competition
from app.modules.ergebnisse.router import (
    PERMISSION_CAPTURE,
    PERMISSION_CORRECT,
    PERMISSION_READ,
    router,
)
from app.modules.ergebnisse.rules import EVENT_LABELS
from app.modules.ergebnisse.service import (
    EVENT_PREFIX,
    EVENT_RECOMPUTED,
    abort_from_starts,
    abort_remarks,
    starts_with_events,
)
from app.modules.starts import hooks as start_hooks
from app.modules.turnier.hooks import register_definition_changed, unregister_definition_changed

__all__ = ["abort_remarks", "manifest", "recompute_competition"]

register_event_names(*(f"{EVENT_PREFIX}{kind}" for kind in EVENT_LABELS), EVENT_RECOMPUTED)


async def on_startup(app: FastAPI) -> None:
    register_definition_changed(on_definition_changed)
    start_hooks.register_result_check(starts_with_events)
    start_hooks.register_abort_handler(abort_from_starts)
    start_hooks.register_progress_provider(lane_progress)


async def on_shutdown(app: FastAPI) -> None:
    unregister_definition_changed(on_definition_changed)
    start_hooks.unregister_result_check(starts_with_events)
    start_hooks.unregister_abort_handler(abort_from_starts)
    start_hooks.unregister_progress_provider(lane_progress)


manifest = ModuleManifest(
    name="ergebnisse",
    title="Ergebnisse",
    router=router,
    permissions=(PERMISSION_READ, PERMISSION_CAPTURE, PERMISSION_CORRECT),
    on_startup=on_startup,
    on_shutdown=on_shutdown,
)
