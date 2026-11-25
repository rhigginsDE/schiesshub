"""Startrecht für Starts und die Vorab-Auskunft: liest Tabelle und Klassen aus dem Katalog.

Ein Turnier-Wettbewerb aus dem Katalog trägt Verband und Kennziffer (`catalog_federation`,
`catalog_code`); die Kennziffer ist der Schlüssel der `startrecht.yaml` (bzw. deren
`kennziffer`). Eine Turnier-Klasse aus dem Katalog trägt dessen Klassen-ID als `code`
(„damen-4“); darüber kommen Klassennummer und Klassensatz. Eigene Wettbewerbe, eigene Klassen und
Verbände ohne Startrecht-Datei (BDS) ergeben keine Angabe.

Nur für Anmeldung/Kasse und Turnierverwaltung: Sichten für Schießstand, Erfassung und Anzeige
bekommen nichts davon.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.katalog import service as katalog_service
from app.modules.katalog.models import Federation
from app.modules.starts.start_rights import (
    NO_STATEMENT,
    CatalogClass,
    StartRightResult,
    StartRightsTable,
    assess,
)
from app.modules.turnier.models import Competition, TournamentClass


class StartRightsLookup:
    """Wertet Startrecht für (Wettbewerb, Klasse) aus; Tabellen werden je Verband nur einmal
    gelesen."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        # Verband -> (Tabelle oder None, Klassen-ID -> Klasse)
        self._federations: dict[str, tuple[StartRightsTable | None, dict[str, CatalogClass]]] = {}

    async def _federation(
        self, key: str
    ) -> tuple[StartRightsTable | None, dict[str, CatalogClass]]:
        if key not in self._federations:
            self._federations[key] = await self._load(key)
        return self._federations[key]

    async def _load(self, key: str) -> tuple[StartRightsTable | None, dict[str, CatalogClass]]:
        try:
            content = await katalog_service.get_start_rights(self._session, key)
            catalog_classes = await katalog_service.list_classes(self._session, key)
        except katalog_service.NotFoundError:
            return None, {}
        by_id = {
            klasse.id: CatalogClass(nummer=klasse.nummer, satz=klasse.satz, name=klasse.name)
            for klasse in catalog_classes
            if klasse.nummer is not None and klasse.satz is not None
        }
        short_name = await self._session.scalar(
            select(Federation.short_name).where(Federation.key == key)
        )
        table = StartRightsTable(
            federation=short_name or key.upper(),
            stand=content.stand_tabelle,
            entries=content.startrecht,
            classes={(klasse.satz, klasse.nummer): klasse for klasse in by_id.values()},
        )
        return table, by_id

    async def check(self, competition: Competition, klass: TournamentClass) -> StartRightResult:
        if competition.catalog_federation is None or competition.catalog_code is None:
            return NO_STATEMENT
        table, classes = await self._federation(competition.catalog_federation)
        return assess(table, competition.catalog_code, classes.get(klass.code))
