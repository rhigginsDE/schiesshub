"""Modul `auth`: Geräte, Personen, Rollen, Berechtigungen und Audit-Protokoll."""

from app.core.module import ModuleManifest
from app.modules.auth import models  # noqa: F401  (registriert die Tabellen)
from app.modules.auth.router import router
from app.modules.auth.service import on_startup

manifest = ModuleManifest(
    name="auth",
    title="Anmeldung und Rechte",
    router=router,
    permissions=("role.manage", "user.manage", "device.manage", "system.manage"),
    on_startup=on_startup,
)
