"""Gemeinsame Fixtures.

Die API-Tests laufen gegen eine echte PostgreSQL-Datenbank: dieselbe Instanz wie in der
Entwicklung (Dienst `db`), aber eine eigene Datenbank mit dem Zusatz `_test`. Das Schema entsteht
über die Alembic-Migrationen, die damit gleich mitgetestet werden.
"""

import asyncio
import os
import shutil
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi import FastAPI
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings, get_settings
from app.core.db import Base
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent
REAL_CATALOG_DIR = get_settings().catalog_dir

ClientFactory = Callable[[Path], AbstractAsyncContextManager[httpx.AsyncClient]]


# --- Datenbank ---------------------------------------------------------------


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
async def _test_database(test_database_url: str) -> None:
    """Legt die Testdatenbank frisch an und spielt die Migrationen ein."""
    name = make_url(test_database_url).database
    admin = create_async_engine(
        make_url(test_database_url).set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    async with admin.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    await admin.dispose()

    migration = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "upgrade",
        "head",
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": test_database_url},
    )
    assert await migration.wait() == 0, "alembic upgrade head ist fehlgeschlagen"


@pytest.fixture(scope="session")
async def engine(test_database_url: str, _test_database: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_db(engine: AsyncEngine) -> None:
    """Leert alle Tabellen, damit jeder Test bei null beginnt."""
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


# --- Anwendung ---------------------------------------------------------------


@pytest.fixture
def settings_for(test_database_url: str) -> Callable[[Path], Settings]:
    def build(catalog_dir: Path) -> Settings:
        return Settings(
            database_url=test_database_url,
            catalog_dir=catalog_dir,
            cors_origins="http://localhost:5180",
            sse_heartbeat_seconds=0.05,
        )

    return build


@asynccontextmanager
async def running(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Startet die Anwendung (inklusive Katalog-Import) und liefert einen HTTP-Client dafür."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def start_app(clean_db: None, settings_for: Callable[[Path], Settings]) -> ClientFactory:
    """Startet die Anwendung mit einem bestimmten Katalog-Verzeichnis.

    Mehrfach aufrufbar: Jeder Aufruf entspricht einem Neustart des Servers auf derselben Datenbank.
    """

    def start(catalog_dir: Path) -> AbstractAsyncContextManager[httpx.AsyncClient]:
        return running(create_app(settings_for(catalog_dir)))

    return start


@pytest.fixture
async def client(start_app: ClientFactory) -> AsyncIterator[httpx.AsyncClient]:
    """Client gegen die Anwendung mit dem echten Katalog."""
    async with start_app(REAL_CATALOG_DIR) as client:
        yield client


# --- Katalog -----------------------------------------------------------------


@pytest.fixture
def catalog_copy(tmp_path: Path) -> Path:
    """Veränderbare Kopie des echten Katalogs."""
    target = tmp_path / "catalog"
    shutil.copytree(REAL_CATALOG_DIR, target)
    return target


def edit_yaml(path: Path, change: Callable[[dict], None]) -> None:
    """Lädt eine YAML-Datei, wendet `change` an und schreibt sie zurück."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


@pytest.fixture
def real_catalog_counts() -> dict[str, int]:
    """Zahlen direkt aus den Dateien gezählt, unabhängig vom Code unter Test."""
    groups = sorted((REAL_CATALOG_DIR / "bds" / "gruppen").glob("*.yaml"))
    disciplines = sum(
        len(yaml.safe_load(path.read_text(encoding="utf-8"))["disziplinen"]) for path in groups
    )
    classes = yaml.safe_load(
        (REAL_CATALOG_DIR / "bds" / "klassen.yaml").read_text(encoding="utf-8")
    )
    return {"gruppen": len(groups), "disziplinen": disciplines, "klassen": len(classes["klassen"])}


@pytest.fixture
def minimal_catalog(tmp_path: Path) -> Path:
    """Kleinster gültiger Katalog: ein Verband, eine Gruppe, zwei Disziplinen, zwei Klassen."""
    root = tmp_path / "minimal"
    groups = root / "tst" / "gruppen"
    groups.mkdir(parents=True)
    (root / "README.md").write_text("wird ignoriert", encoding="utf-8")
    (root / "tst" / "katalog.yaml").write_text(
        """
schema: 1
id: "tst"
verband: { kuerzel: "TST", name: "Testverband" }
regelwerk: { name: "Testregeln", stand: "2026-01-01" }
status: "entwurf"
""",
        encoding="utf-8",
    )
    (root / "tst" / "klassen.yaml").write_text(
        """
schema: 1
verband: "tst"
klassen:
  - { id: "offen", name: "Offene Klasse", kurz: "O", geschlecht: "alle", zusammenlegen_in: [] }
  - id: "damen"
    name: "Damenklasse"
    kurz: "D"
    geschlecht: "weiblich"
    zusammenlegen_in: ["offen"]
""",
        encoding="utf-8",
    )
    (groups / "kw-25m-praezision.yaml").write_text(
        """
schema: 1
verband: "tst"
gruppe:
  id: "kw-25m-praezision"
  name: "KW 25 m Präzision"
  waffenart: "kurzwaffe"
  distanz_m: 25
  art: "praezision"
wertung:
  modell: "ringe"
  rangfolge: "absteigend"
  geprueft: false
ablaeufe:
  praezision-2x10:
    beschreibung: "20 Schuss"
    varianten:
      - id: "standard"
        name: "Standard"
        abschnitte:
          - id: "praezision"
            name: "Präzision"
            serien: 2
            schuss_je_serie: 10
            zeit_je_serie_s: 300
disziplinen:
  - kennziffer: "1001"
    name: "Pistole bis 9 mm"
    waffe: "Pistole"
    munition: "bis 9 mm"
    visierung: "offen"
    anschlag: "stehend"
    scheibe: "Kurzwaffenscheibe"
    ablauf: "praezision-2x10"
  - kennziffer: "1002"
    name: "Pistole über 9 mm"
    waffe: "Pistole"
    munition: "über 9 mm"
    visierung: "offen"
    anschlag: "stehend"
    scheibe: "Kurzwaffenscheibe"
    ablauf: "praezision-2x10"
""",
        encoding="utf-8",
    )
    return root
