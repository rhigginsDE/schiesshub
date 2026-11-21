"""Fixtures des Moduls `teilnehmer`: Anwendung mit temporärem Schlüsselverzeichnis."""

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.core import crypto
from app.core.config import Settings
from app.core.events import Event
from app.main import create_app
from tests.conftest import running

API = "/api/v1"

AppFactory = Callable[[], FastAPI]


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def make_app(
    clean_db: None,
    settings_for: Callable[[Path], Settings],
    minimal_catalog: Path,
    data_dir: Path,
) -> Iterator[AppFactory]:
    """Baut eine Anwendung auf der leeren Testdatenbank; Schlüssel liegen unter `data_dir`.

    Mehrfach aufrufbar: Jede neue Anwendung entspricht einem Neustart des Servers.
    """

    def build() -> FastAPI:
        settings = settings_for(minimal_catalog).model_copy(update={"data_dir": data_dir})
        return create_app(settings)

    yield build
    crypto.set_field_cipher(None)


@pytest.fixture
def app(make_app: AppFactory) -> FastAPI:
    return make_app()


@pytest.fixture
async def api(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with running(app) as client:
        yield client


class EventRecorder:
    """Sammelt alle Ereignisse, die die Anwendung verteilt."""

    def __init__(self, app: FastAPI) -> None:
        self._queue = app.state.events.subscribe()
        self.events: list[Event] = []

    def drain(self) -> list[Event]:
        while not self._queue.empty():
            self.events.append(self._queue.get_nowait())
        return self.events

    def names(self) -> list[str]:
        return [event.name for event in self.drain() if not event.name.startswith("katalog.")]


@pytest.fixture
def recorder(app: FastAPI) -> EventRecorder:
    return EventRecorder(app)
