"""Modul `backup`: Datenbank-Abzüge, laufende Mitschrift und verschlüsselte Kopie auf den Stick.

Andere Module schreiben Einträge der Mitschrift mit `append_journal(record)`.
"""

from app.core import settings_store  # noqa: F401  (Tabelle `setting`, Migration im Modul backup)
from app.core.module import ModuleManifest
from app.modules.backup import models  # noqa: F401  (registriert die Tabellen)
from app.modules.backup.router import router
from app.modules.backup.service import append_journal, on_shutdown, on_startup

__all__ = ["append_journal", "manifest"]

manifest = ModuleManifest(
    name="backup",
    title="Sicherung",
    router=router,
    permissions=("backup.read", "backup.manage"),
    on_startup=on_startup,
    on_shutdown=on_shutdown,
)
