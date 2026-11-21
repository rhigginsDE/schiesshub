"""Fixtures der Sicherungstests.

Datenverzeichnis und Stick sind temporäre Verzeichnisse; das echte ./.dev/usb bleibt unberührt.
Der Zeitplan der Sicherung läuft standardmäßig nicht, damit die Tests die Schritte selbst
auslösen und nicht mit dem Hintergrund-Task um den Stick konkurrieren.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from app.modules.backup import service as backup_service
from tests.conftest import REAL_CATALOG_DIR, running

PASSPHRASE = "korrektes Pferd Batterie Heftklammer"


@dataclass
class BackupEnv:
    data_dir: Path
    usb_dir: Path
    marker: str

    @property
    def marker_path(self) -> Path:
        return self.usb_dir / self.marker

    def plug_in(self) -> None:
        self.marker_path.write_text("{}", encoding="utf-8")

    def pull_out(self) -> None:
        self.marker_path.unlink()

    def usb_files(self) -> list[Path]:
        return sorted(
            path for path in self.usb_dir.rglob("*") if path.is_file() and path != self.marker_path
        )

    def local_snapshots(self) -> list[Path]:
        return sorted((self.data_dir / "backups" / "snapshots").glob("*.dump"))


@dataclass
class BackupApp:
    app: FastAPI
    client: httpx.AsyncClient
    env: BackupEnv

    @property
    def service(self) -> backup_service.BackupService:
        return self.app.state.backup


@pytest.fixture
def backup_env(tmp_path: Path) -> BackupEnv:
    usb_dir = tmp_path / "usb"
    usb_dir.mkdir()
    return BackupEnv(data_dir=tmp_path / "data", usb_dir=usb_dir, marker=".schiesshub-backup")


@pytest.fixture
def backup_settings(test_database_url: str, backup_env: BackupEnv) -> Settings:
    return Settings(
        database_url=test_database_url,
        catalog_dir=REAL_CATALOG_DIR,
        sse_heartbeat_seconds=0.05,
        data_dir=backup_env.data_dir,
        backup_usb_dir=backup_env.usb_dir,
        backup_usb_marker=backup_env.marker,
    )


async def _idle(self: backup_service.BackupService) -> None:
    await asyncio.Event().wait()


@pytest.fixture
def idle_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backup_service.BackupService, "_loop", _idle)


StartBackup = Callable[[], AbstractAsyncContextManager[BackupApp]]


@pytest.fixture
def start_backup(clean_db: None, backup_settings: Settings, backup_env: BackupEnv) -> StartBackup:
    """Startet die Anwendung mit den Test-Verzeichnissen; mehrfach aufrufbar (Neustart)."""

    @asynccontextmanager
    async def start() -> AsyncIterator[BackupApp]:
        app = create_app(backup_settings)
        async with running(app) as client:
            yield BackupApp(app=app, client=client, env=backup_env)

    return start


@pytest.fixture
async def backup(idle_scheduler: None, start_backup: StartBackup) -> AsyncIterator[BackupApp]:
    async with start_backup() as started:
        yield started
