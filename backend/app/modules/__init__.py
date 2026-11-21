"""Alle Module der Anwendung.

Ein Modul ist ein Paket mit `router`, `schemas`, `service`, bei Bedarf `models`, und einem
`manifest` in seiner `__init__.py`. Neue Module werden hier in die Liste eingetragen;
`app.main` registriert sie, und Alembic findet darüber ihre Tabellen.
"""

from app.core.module import ModuleManifest
from app.modules import katalog, system

MODULES: list[ModuleManifest] = [
    system.manifest,
    katalog.manifest,
]
