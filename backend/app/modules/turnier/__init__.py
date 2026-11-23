"""Modul `turnier`: Turnier, Schießstände, Klassen, Wettbewerbe und ihre Einstellungen."""

from app.core.events import register_event_names
from app.core.module import ModuleManifest
from app.modules.turnier import models  # noqa: F401  (registriert die Tabellen)
from app.modules.turnier.router import (
    PERMISSION_EDIT,
    PERMISSION_READ,
    PERMISSION_REOPEN,
    module_router,
)

# Ereignisse dieses Moduls (Nutzlast: betroffene IDs). `tournament.deleted` kommt auch beim
# Entfernen des Übungsturniers; `tournament.created` nach einer Kopie zusätzlich mit
# `copied_from`.
EVENT_NAMES: tuple[str, ...] = (
    "tournament.created",
    "tournament.updated",
    "tournament.status_changed",
    "tournament.deleted",
    "tournament.announcement_changed",
    "range.created",
    "range.updated",
    "range.deleted",
    "range.reordered",
    "class.created",
    "class.updated",
    "class.deleted",
    "class.reordered",
    "class.imported",
    "competition.created",
    "competition.updated",
    "competition.definition_changed",
    "competition.deleted",
    "competition.reordered",
)

register_event_names(*EVENT_NAMES)

manifest = ModuleManifest(
    name="turnier",
    title="Turnier",
    router=module_router,
    permissions=(PERMISSION_READ, PERMISSION_EDIT, PERMISSION_REOPEN),
)
