"""Modul `anzeige`: Inhalt und Einstellungen der öffentlichen Anzeigen.

Es gibt beliebig viele Anzeigen (Fernseher im Aufenthaltsraum, Bildschirm am Stand). Jede hat
eine geordnete Liste von Szenen; was sie zeigt, wird von den Stationen aus eingestellt. Ein
gekoppeltes Gerät kann einer Anzeige zugewiesen werden und zeigt sie dann automatisch.
"""

from app.core.module import ModuleManifest
from app.modules.anzeige import models  # noqa: F401  (registriert die Tabellen)
from app.modules.anzeige.router import PERMISSION_CONTROL, PERMISSION_READ, router
from app.modules.anzeige.service import on_shutdown, on_startup

manifest = ModuleManifest(
    name="anzeige",
    title="Anzeige",
    router=router,
    permissions=(PERMISSION_READ, PERMISSION_CONTROL),
    on_startup=on_startup,
    on_shutdown=on_shutdown,
)
