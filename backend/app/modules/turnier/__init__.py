"""Modul `turnier`: Turnier, Stände, Klassen, Wettbewerbe und ihre Einstellungen."""

from app.core.module import ModuleManifest
from app.modules.turnier import models  # noqa: F401  (registriert die Tabellen)
from app.modules.turnier.router import (
    PERMISSION_EDIT,
    PERMISSION_READ,
    PERMISSION_REOPEN,
    module_router,
)

manifest = ModuleManifest(
    name="turnier",
    title="Turnier",
    router=module_router,
    permissions=(PERMISSION_READ, PERMISSION_EDIT, PERMISSION_REOPEN),
)
