"""Modul `katalog`: YAML-Katalog einlesen und bereitstellen."""

from app.core.module import ModuleManifest
from app.modules.katalog import models  # noqa: F401  (registriert die Tabellen)
from app.modules.katalog.router import router
from app.modules.katalog.service import on_startup

manifest = ModuleManifest(
    name="katalog",
    title="Disziplin-Katalog",
    router=router,
    on_startup=on_startup,
)
