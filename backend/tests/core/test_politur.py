"""Gemeinsame Bausteine: 409 mit Feldbezug, bekannte Ereignisnamen, Ortszeit."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.core import events as events_module
from app.core.errors import ConflictError, install_error_handlers
from app.core.events import EventHub, match_names, register_event_names
from app.core.localtime import (
    DEFAULT_TIMEZONE,
    check_timezone,
    is_valid_timezone,
    local_iso,
    zone,
    zone_of,
)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/with-field")
    async def with_field() -> None:
        raise ConflictError("Bahn 2 ist schon belegt.", field="lane")

    @app.post("/without-field")
    async def without_field() -> None:
        raise ConflictError("Nur ein wartender Start lässt sich aufrufen.")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_conflict_with_field_has_errors(client: httpx.AsyncClient) -> None:
    response = await client.post("/with-field")
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Bahn 2 ist schon belegt.",
        "errors": [{"field": "lane", "message": "Bahn 2 ist schon belegt."}],
    }


async def test_conflict_without_field_is_plain(client: httpx.AsyncClient) -> None:
    response = await client.post("/without-field")
    assert response.status_code == 409
    assert response.json() == {"detail": "Nur ein wartender Start lässt sich aufrufen."}


def test_conflict_error_stays_an_http_exception() -> None:
    error = ConflictError("x", field="lane")
    assert isinstance(error, HTTPException)
    assert (error.status_code, error.detail, error.field) == (409, "x", "lane")
    assert ConflictError("y").errors is None


# --- Ereignisnamen -------------------------------------------------------------------


def test_match_names_resolves_patterns() -> None:
    known = ["start.called", "start.moved", "result.finalized", "startliste.x", "auth.login"]
    assert match_names(["start.*", "display.changed"], known) == [
        "display.changed",
        "start.called",
        "start.moved",
    ]
    # Ohne bekannte Namen bleibt ein Muster leer, ein genauer Name bleibt stehen.
    assert match_names(["result.*", "backup.status"], []) == ["backup.status"]


def test_hub_knows_registered_and_published_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events_module, "_registered_names", set())
    hub = EventHub()
    assert hub.known_names() == []
    register_event_names("b.registered", "a.registered")
    hub.publish("c.published")
    assert hub.known_names() == ["a.registered", "b.registered", "c.published"]
    # Andere Verteiler kennen nur die angemeldeten.
    assert EventHub().known_names() == ["a.registered", "b.registered"]
    with pytest.raises(ValueError, match="Ereignisname"):
        register_event_names("start.*")


# --- Ortszeit --------------------------------------------------------------------


def test_timezones() -> None:
    assert is_valid_timezone("Europe/Vienna")
    assert not is_valid_timezone("Europe")
    assert not is_valid_timezone("Mond/Basis")
    assert not is_valid_timezone("")
    assert check_timezone("UTC") == "UTC"
    with pytest.raises(ValueError, match="keine bekannte Zeitzone"):
        check_timezone("Mond/Basis")
    assert str(zone(None)) == DEFAULT_TIMEZONE
    assert str(zone("Mond/Basis")) == DEFAULT_TIMEZONE
    assert str(zone_of({"timezone": "Asia/Tokyo"})) == "Asia/Tokyo"
    assert str(zone_of({})) == DEFAULT_TIMEZONE
    assert str(zone_of({"timezone": 5})) == DEFAULT_TIMEZONE
    moment = datetime(2027, 7, 1, 10, 0, tzinfo=UTC)
    assert local_iso(moment, zone("Europe/Berlin")) == "2027-07-01T12:00:00+02:00"
    assert local_iso(None, zone(None)) is None
