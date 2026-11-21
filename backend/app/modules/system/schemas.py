"""Antwortformate des Moduls `system`."""

from typing import Literal

from pydantic import BaseModel

from app.modules.katalog.schemas import KatalogStatusOut


class HealthOut(BaseModel):
    # ok: alles in Ordnung · eingeschraenkt: läuft, aber der Katalog hat Fehler ·
    # fehler: Datenbank nicht erreichbar (HTTP 503)
    status: Literal["ok", "eingeschraenkt", "fehler"]
    version: str
    db: Literal["ok", "fehler"]
    katalog: KatalogStatusOut | None
