"""Modul `ergebnisse`: Erfassung, unveränderliches Ereignisprotokoll, Wertung, Ranglisten.

Öffentliche Schnittstelle für andere Module: `recompute_competition(session, competition_id,
actor)` (rechnet alle Ergebnisse eines Wettbewerbs aus den Ereignissen neu, ohne zu bestätigen).
Bei einer neuen Revision der Wertung läuft sie automatisch über `turnier.hooks`.
"""

from fastapi import FastAPI

from app.core.module import ModuleManifest
from app.modules.ergebnisse import models  # noqa: F401  (registriert die Tabellen)
from app.modules.ergebnisse.recompute import on_definition_changed, recompute_competition
from app.modules.ergebnisse.router import (
    PERMISSION_CAPTURE,
    PERMISSION_CORRECT,
    PERMISSION_READ,
    router,
)
from app.modules.turnier.hooks import register_definition_changed, unregister_definition_changed

__all__ = ["manifest", "recompute_competition"]


async def on_startup(app: FastAPI) -> None:
    register_definition_changed(on_definition_changed)


async def on_shutdown(app: FastAPI) -> None:
    unregister_definition_changed(on_definition_changed)


manifest = ModuleManifest(
    name="ergebnisse",
    title="Ergebnisse",
    router=router,
    permissions=(PERMISSION_READ, PERMISSION_CAPTURE, PERMISSION_CORRECT),
    on_startup=on_startup,
    on_shutdown=on_shutdown,
)
