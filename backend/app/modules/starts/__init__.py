"""Modul `starts`: Anmeldung, Starts, Reihenfolge und Zeitplan am Stand.

Öffentliche Schnittstelle für andere Module (z. B. `ergebnisse`) ist `lifecycle`:
`load_start`, `transition`, `publish_status` (siehe dort). Über `hooks` melden sich Module an,
die Ergebnis-Daten zu Starts führen (Lösch- und Stornoschutz) oder den Abbruch übernehmen.
"""

from app.core.events import register_event_names
from app.core.module import ModuleManifest
from app.modules.starts import (
    lifecycle,
    models,  # noqa: F401  (registriert die Tabellen)
    queue,
    schedule,
    service,
)
from app.modules.starts.router import (
    PERMISSION_ENTRY_EDIT,
    PERMISSION_ENTRY_READ,
    PERMISSION_START_CALL,
    PERMISSION_START_EDIT,
    PERMISSION_START_READ,
    router,
)
from app.modules.starts.service import on_startup

register_event_names(
    service.EVENT_ENTRY_CREATED,
    service.EVENT_ENTRY_UPDATED,
    service.EVENT_ENTRY_DELETED,
    service.EVENT_START_BOOKED,
    service.EVENT_START_CANCELLED,
    lifecycle.EVENT_STATUS_CHANGED,
    queue.EVENT_START_MOVED,
    queue.EVENT_LANE_RELEASED,
    schedule.EVENT_HEAT_CREATED,
    schedule.EVENT_HEAT_UPDATED,
    schedule.EVENT_HEAT_DELETED,
    schedule.EVENT_START_SCHEDULED,
)

manifest = ModuleManifest(
    name="starts",
    title="Anmeldung und Starts",
    router=router,
    permissions=(
        PERMISSION_ENTRY_READ,
        PERMISSION_ENTRY_EDIT,
        PERMISSION_START_READ,
        PERMISSION_START_EDIT,
        PERMISSION_START_CALL,
    ),
    on_startup=on_startup,
)
