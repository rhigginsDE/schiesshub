"""Modul `teilnehmer`: Personen und Vereine, Suche, Import und Export.

Andere Module, die auf Personen verweisen (z. B. Anmeldungen), melden über
`service.register_person_deletion_check` einen Prüfer an, der das endgültige Löschen einer
Person verhindern kann.
"""

from app.core.module import ModuleManifest
from app.modules.teilnehmer import models  # noqa: F401  (registriert die Tabellen)
from app.modules.teilnehmer.router import router
from app.modules.teilnehmer.service import on_startup

manifest = ModuleManifest(
    name="teilnehmer",
    title="Teilnehmer",
    router=router,
    permissions=("person.read", "person.edit", "person.delete", "person.export", "club.edit"),
    on_startup=on_startup,
)
