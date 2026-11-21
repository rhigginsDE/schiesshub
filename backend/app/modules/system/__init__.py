"""Modul `system`: Status des Servers und Live-Ereignisse."""

from app.core.module import ModuleManifest
from app.modules.system.router import router

manifest = ModuleManifest(
    name="system",
    title="System",
    router=router,
)
