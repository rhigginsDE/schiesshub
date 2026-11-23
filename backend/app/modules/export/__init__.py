"""Modul `export`: Startliste und Ergebnisliste als PDF und CSV, Rohexport der Ergebnisse.

Aufbau: `service` holt die Daten über die Sichten der Module `starts` und `ergebnisse`,
`tables` bereitet sie zu neutralen Tabellen auf (rein, ohne Datenbank), `csvout` und `pdfout`
schreiben die Dateien. Keine eigenen Tabellen.
"""

from app.core.module import ModuleManifest
from app.modules.export.router import PERMISSION_FULL_NAMES, PERMISSION_READ, router

manifest = ModuleManifest(
    name="export",
    title="Export",
    router=router,
    permissions=(PERMISSION_READ, PERMISSION_FULL_NAMES),
)
