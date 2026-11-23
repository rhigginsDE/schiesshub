"""Antwortformate des Moduls `system`."""

from typing import Literal

from pydantic import BaseModel

from app.core.begriffe import Begriffe
from app.modules.katalog.schemas import KatalogStatusOut


class TermsOut(BaseModel):
    """Formelle Begriffe: Standardsatz und je Verband der vollständige Satz."""

    # Ohne Verband (eigene Disziplin) und für Verbände ohne eigenen Satz.
    default: Begriffe
    # Schlüssel = `catalog_federation` in Kleinbuchstaben, z. B. `bds`, `dsb`.
    federations: dict[str, Begriffe]


class HealthOut(BaseModel):
    # ok: alles in Ordnung · eingeschraenkt: läuft, aber der Katalog hat Fehler ·
    # fehler: Datenbank nicht erreichbar (HTTP 503)
    status: Literal["ok", "eingeschraenkt", "fehler"]
    version: str
    db: Literal["ok", "fehler"]
    katalog: KatalogStatusOut | None
