"""Deutsche Eingabefehler: Übersetzung, Antwortform und OpenAPI-Beschreibung.

Eine kleine eigene Anwendung ohne Datenbank, damit jede Fehlerart gezielt auslösbar ist.
"""

from collections.abc import AsyncIterator
from typing import Annotated, Literal, Self

import httpx
import pytest
from fastapi import FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.errors import (
    InputError,
    describe_error,
    install_error_handlers,
    summarize,
    translate_errors,
)
from app.modules.katalog.fileformat import Abschnitt

Number = Annotated[int, Field(gt=0)] | Annotated[float, Field(gt=0)]


class Inner(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    serien: Annotated[int, Field(ge=1)]
    zeiten_s: list[int] | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.zeiten_s is not None and len(self.zeiten_s) != self.serien:
            raise ValueError(f"zeiten_s hat {len(self.zeiten_s)} Einträge, erwartet {self.serien}")
        return self


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: Annotated[str, Field(min_length=1, max_length=5)] = "x"
    lane_count: Annotated[int, Field(ge=1)] = 1
    planning: Literal["queue", "schedule"] = "queue"
    time_s: Number | None = None
    inner: list[Inner] = []
    multi_start: bool = False
    max_starts: int = 1

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.multi_start and self.max_starts != 1:
            raise ValueError("Ohne Mehrfachstart ist genau ein Start möglich.")
        return self


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/items")
    async def create(body: Body) -> dict[str, str]:
        return {"ok": "ja"}

    @app.get("/items")
    async def search(limit: Annotated[int, Query(ge=1, le=50)] = 10) -> dict[str, int]:
        return {"limit": limit}

    @app.post("/fachlich")
    async def domain() -> None:
        raise InputError.single("reason", "Bitte einen Grund angeben.")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def post(client: httpx.AsyncClient, body: object) -> dict:
    response = await client.post("/items", json=body)
    assert response.status_code == 422, response.text
    return response.json()


# --- Antwortform -------------------------------------------------------------


async def test_single_error_gives_sentence_and_field(client: httpx.AsyncClient) -> None:
    assert await post(client, {"lane_count": 0}) == {
        "detail": "Feld ‚lane_count‘: muss mindestens 1 sein.",
        "errors": [{"field": "lane_count", "message": "muss mindestens 1 sein"}],
    }


async def test_unknown_field(client: httpx.AsyncClient) -> None:
    assert await post(client, {"foo": 1}) == {
        "detail": "Unbekanntes Feld ‚foo‘.",
        "errors": [{"field": "foo", "message": "unbekanntes Feld"}],
    }


async def test_several_errors_are_summarized(client: httpx.AsyncClient) -> None:
    body = await post(client, {"name": "", "lane_count": "3", "planning": "irgendwann"})

    assert body["errors"] == [
        {"field": "name", "message": "darf nicht leer sein"},
        {"field": "lane_count", "message": "muss eine ganze Zahl sein"},
        {"field": "planning", "message": "muss einer dieser Werte sein: 'queue' oder 'schedule'"},
    ]
    assert body["detail"] == (
        "Die Eingabe enthält 3 Fehler: Feld ‚name‘: darf nicht leer sein; "
        "Feld ‚lane_count‘: muss eine ganze Zahl sein; "
        "Feld ‚planning‘: muss einer dieser Werte sein: 'queue' oder 'schedule'."
    )


async def test_union_branches_give_one_message(client: httpx.AsyncClient) -> None:
    wrong_type = await post(client, {"time_s": "zehn"})
    negative = await post(client, {"time_s": -1})

    assert wrong_type["errors"] == [{"field": "time_s", "message": "muss eine Zahl sein"}]
    assert negative["errors"] == [{"field": "time_s", "message": "muss größer als 0 sein"}]


async def test_nested_paths_and_validator_messages(client: httpx.AsyncClient) -> None:
    body = await post(client, {"inner": [{"serien": 1}, {"serien": 2, "zeiten_s": [30]}]})

    # Die Meldung des Modell-Validators nennt das Feld; der Pfad zeigt darauf.
    assert body["errors"] == [
        {"field": "inner[1].zeiten_s", "message": "zeiten_s hat 1 Einträge, erwartet 2"}
    ]
    assert body["detail"] == "Feld ‚inner[1].zeiten_s‘: zeiten_s hat 1 Einträge, erwartet 2."


async def test_whole_sentences_stand_alone(client: httpx.AsyncClient) -> None:
    body = await post(client, {"max_starts": 3})

    assert body == {
        "detail": "Ohne Mehrfachstart ist genau ein Start möglich.",
        "errors": [{"field": None, "message": "Ohne Mehrfachstart ist genau ein Start möglich."}],
    }


async def test_missing_and_broken_body(client: httpx.AsyncClient) -> None:
    missing = await client.post("/items")
    broken = await client.post(
        "/items", content=b"{nicht json", headers={"content-type": "application/json"}
    )

    assert missing.status_code == broken.status_code == 422
    assert missing.json()["detail"] == "Die Anfrage braucht einen Inhalt (JSON)."
    assert broken.json() == {
        "detail": "Die Anfrage ist kein gültiges JSON.",
        "errors": [{"field": None, "message": "Die Anfrage ist kein gültiges JSON."}],
    }


async def test_query_parameters(client: httpx.AsyncClient) -> None:
    response = await client.get("/items", params={"limit": 99})

    assert response.status_code == 422
    assert response.json()["errors"] == [{"field": "limit", "message": "darf höchstens 50 sein"}]


async def test_input_error_has_the_same_shape(client: httpx.AsyncClient) -> None:
    response = await client.post("/fachlich")

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Bitte einen Grund angeben.",
        "errors": [{"field": "reason", "message": "Bitte einen Grund angeben."}],
    }


# --- Bausteine -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "message"),
    [
        ({"type": "missing", "loc": ("x",), "msg": ""}, "Pflichtfeld fehlt"),
        (
            {"type": "less_than", "loc": ("x",), "msg": "", "ctx": {"lt": 3}},
            "muss kleiner als 3 sein",
        ),
        (
            {"type": "string_too_long", "loc": ("x",), "msg": "", "ctx": {"max_length": 5}},
            "darf höchstens 5 Zeichen lang sein",
        ),
        (
            {"type": "too_short", "loc": ("x",), "msg": "", "ctx": {"min_length": 2}},
            "braucht mindestens 2 Einträge",
        ),
        ({"type": "uuid_parsing", "loc": ("x",), "msg": ""}, "muss eine gültige ID (UUID) sein"),
        ({"type": "ganz_neu", "loc": ("x",), "msg": "Something new"}, "hat einen ungültigen Wert"),
    ],
)
def test_describe_error(error: dict, message: str) -> None:
    assert describe_error(error) == message


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"serien_gewertet": 7}, "serien_gewertet"),
        ({"trefferaufnahme_nach": [4, 2]}, "trefferaufnahme_nach"),
        ({"ringwerte": [7, 10]}, "ringwerte"),
        ({"zeiten_s": [30]}, "zeiten_s"),
        ({"kaliber": 9}, "kaliber"),
    ],
)
def test_catalog_section_errors_point_to_the_field(changes: dict, field: str) -> None:
    with pytest.raises(ValidationError) as caught:
        Abschnitt.model_validate({"id": "a", "name": "A", "serien": 6, **changes})

    errors = translate_errors(caught.value.errors())

    assert [error.field for error in errors] == [field]
    assert errors[0].message
    assert not errors[0].message.startswith(("Value error", "Input should"))


def test_summarize_without_errors() -> None:
    assert summarize([]) == "Die Eingabe ist ungültig."


# --- OpenAPI -------------------------------------------------------------------


async def test_openapi_describes_the_new_shape(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    components = schema["components"]["schemas"]

    assert set(components["HTTPValidationError"]["properties"]) == {"detail", "errors"}
    assert components["HTTPValidationError"]["properties"]["detail"]["type"] == "string"
    assert set(components["FieldError"]["properties"]) == {"field", "message"}
    assert "ValidationError" not in components
    response_422 = schema["paths"]["/items"]["post"]["responses"]["422"]
    assert response_422["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HTTPValidationError"
    }
