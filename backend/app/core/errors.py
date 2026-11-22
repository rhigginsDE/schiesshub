"""Verständliche deutsche Meldungen für Eingabefehler.

Pydantic und FastAPI melden Fehler englisch („Input should be greater than or equal to 1“). Hier
werden sie in kurze deutsche Sätze übersetzt. Dieselbe Übersetzung nutzt der Katalog-Import für
Fehler in den YAML-Dateien.

Antwort bei einem Eingabefehler (HTTP 422):

    {
      "detail": "Feld ‚lane_count‘: muss mindestens 1 sein.",
      "errors": [{"field": "lane_count", "message": "muss mindestens 1 sein"}]
    }

`detail` ist ein zusammenfassender Satz zum Anzeigen, `errors` die Liste für Formulare. `field` ist
der Pfad im Anfrage-Inhalt (`definition.variant.abschnitte[0].serien`) oder `null`, wenn der
Fehler die Anfrage als Ganzes betrifft.

Fachliche Konflikte (HTTP 409, „im aktuellen Zustand nicht möglich“) meldet `ConflictError`.
Bezieht sich der Konflikt auf ein Eingabefeld (z. B. Startnummer schon vergeben), steht es wie
bei 422 zusätzlich in `errors`:

    {"detail": "Bahn 2 ist schon belegt.", "errors": [{"field": "lane", "message": "…"}]}

Ohne Feld bleibt die Antwort ein gewöhnliches 409 mit `detail`.

Muss die Oberfläche einen Fehler unterscheiden, ohne den Text zu lesen (etwa „Gerät gesperrt“
gegen „Sitzung abgelaufen“, beides HTTP 401), meldet `CodedError` zusätzlich `code`:

    {"detail": "Dieses Gerät wurde gesperrt. …", "code": "device_revoked"}
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Teilsätze je Fehlertyp. Platzhalter kommen aus `ctx` des Fehlers.
MESSAGES: dict[str, str] = {
    "extra_forbidden": "unbekanntes Feld",
    "missing": "Pflichtfeld fehlt",
    "string_type": "muss Text sein (in Anführungszeichen setzen)",
    "string_too_long": "darf höchstens {max_length} Zeichen lang sein",
    "string_pattern_mismatch": "hat nicht das erwartete Format",
    "int_type": "muss eine ganze Zahl sein",
    "int_parsing": "muss eine ganze Zahl sein",
    "int_from_float": "muss eine ganze Zahl sein",
    "float_type": "muss eine Zahl sein",
    "float_parsing": "muss eine Zahl sein",
    "finite_number": "muss eine endliche Zahl sein",
    "bool_type": "muss true oder false sein",
    "bool_parsing": "muss true oder false sein",
    "list_type": "muss eine Liste sein",
    "tuple_type": "muss eine Liste sein",
    "set_type": "muss eine Liste sein",
    "dict_type": "muss eine Zuordnung (Schlüssel: Wert) sein",
    "model_type": "muss eine Zuordnung (Schlüssel: Wert) sein",
    "model_attributes_type": "muss eine Zuordnung (Schlüssel: Wert) sein",
    "greater_than": "muss größer als {gt} sein",
    "greater_than_equal": "muss mindestens {ge} sein",
    "less_than": "muss kleiner als {lt} sein",
    "less_than_equal": "darf höchstens {le} sein",
    "multiple_of": "muss ein Vielfaches von {multiple_of} sein",
    "literal_error": "muss einer dieser Werte sein: {expected}",
    "enum": "muss einer dieser Werte sein: {expected}",
    "uuid_type": "muss eine gültige ID (UUID) sein",
    "uuid_parsing": "muss eine gültige ID (UUID) sein",
    "date_type": "muss ein Datum im Format JJJJ-MM-TT sein",
    "date_parsing": "muss ein Datum im Format JJJJ-MM-TT sein",
    "date_from_datetime_parsing": "muss ein Datum im Format JJJJ-MM-TT sein",
    "date_from_datetime_inexact": "muss ein Datum ohne Uhrzeit sein",
    "datetime_type": "muss ein Zeitpunkt im Format JJJJ-MM-TTThh:mm:ss sein",
    "datetime_parsing": "muss ein Zeitpunkt im Format JJJJ-MM-TTThh:mm:ss sein",
    "datetime_from_date_parsing": "muss ein Zeitpunkt im Format JJJJ-MM-TTThh:mm:ss sein",
    "time_type": "muss eine Uhrzeit im Format hh:mm sein",
    "time_parsing": "muss eine Uhrzeit im Format hh:mm sein",
    "none_required": "muss leer (null) sein",
    "union_tag_invalid": "hat eine unbekannte Art: {tag}",
    "union_tag_not_found": "braucht die Angabe {discriminator}",
    "json_invalid": "ist kein gültiges JSON",
    "json_type": "ist kein gültiges JSON",
}
FALLBACK = "hat einen ungültigen Wert"

# Teile von `loc`, die keine Felder sind, sondern Zweige einer Union (`int | float`).
_UNION_BRANCH = re.compile(r"^(constrained-\w+|int|float|str|bool|bytes|none|.*\[.*\])$")
# Eine Meldung aus einem Modell-Validator, die mit einem Feldnamen beginnt („zeiten_s hat …“).
_LEADING_FIELD = re.compile(r"^([a-z_][a-z0-9_]*)((?:\[\d+\])*(?:\.[a-z_][a-z0-9_]*)*)\b")
# Diese Wurzeln von `loc` nennt FastAPI für die Quelle des Werts; sie gehören nicht zum Feld.
_SOURCES = frozenset({"body", "query", "path", "header", "cookie"})


def format_location(loc: Iterable[int | str]) -> str:
    """`("abschnitte", 0, "serien")` → `abschnitte[0].serien`."""
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path


def _ctx_value(key: str, value: Any) -> Any:
    if key == "expected":
        # Pydantic liefert „'a', 'b' or 'c'“.
        return str(value).replace(" or ", " oder ")
    if isinstance(value, float):
        # 0.0 → „0“, 1.5 → „1,5“
        return str(int(value)) if value.is_integer() else str(value).replace(".", ",")
    return value


def describe_error(error: Mapping[str, Any]) -> str:
    """Teilsatz zu einem Pydantic-Fehler, ohne Feldnamen („muss mindestens 1 sein“)."""
    kind = error["type"]
    ctx = error.get("ctx") or {}
    if kind in {"value_error", "assertion_error"}:
        return str(ctx["error"]) if "error" in ctx else str(error["msg"])
    if kind == "string_too_short":
        minimum = ctx.get("min_length", 1)
        return (
            "darf nicht leer sein" if minimum == 1 else f"muss mindestens {minimum} Zeichen haben"
        )
    if kind == "too_short":
        minimum = ctx.get("min_length", 1)
        return "darf nicht leer sein" if minimum == 1 else f"braucht mindestens {minimum} Einträge"
    if kind == "too_long":
        return f"darf höchstens {ctx.get('max_length')} Einträge haben"
    template = MESSAGES.get(kind)
    if template is None:
        return FALLBACK
    values = {key: _ctx_value(key, value) for key, value in ctx.items()}
    try:
        return template.format(**values)
    except KeyError, IndexError:
        return FALLBACK


def _field_parts(error: Mapping[str, Any]) -> list[int | str]:
    loc = list(error.get("loc", ()))
    if loc and loc[0] in _SOURCES:
        loc = loc[1:]
    if error["type"] == "json_invalid":
        return []
    parts = [part for part in loc if not (isinstance(part, str) and _UNION_BRANCH.match(part))]
    # Modell-Validatoren melden auf Ebene des Modells. Nennt die Meldung vorn ein Feld dieses
    # Modells, zeigt der Pfad genauer auf dieses Feld.
    if error["type"] == "value_error" and isinstance(error.get("input"), Mapping):
        match = _LEADING_FIELD.match(describe_error(error))
        if match and match.group(1) in error["input"]:
            nested = re.findall(r"\[(\d+)\]|\.([a-z_][a-z0-9_]*)", match.group(2))
            parts.append(match.group(1))
            parts.extend(int(index) if index else name for index, name in nested)
    return parts


class FieldError(BaseModel):
    """Ein Fehler für ein Formular: Pfad des Felds und deutscher Teilsatz."""

    field: str | None
    message: str


class ValidationErrorOut(BaseModel):
    """Antwort bei ungültiger Eingabe (HTTP 422)."""

    detail: str
    errors: list[FieldError]


def translate_errors(errors: Sequence[Mapping[str, Any]]) -> list[FieldError]:
    """Übersetzt Pydantic-Fehler, ohne doppelte Einträge (Union-Zweige melden mehrfach)."""
    result: list[FieldError] = []
    seen: set[tuple[str | None, str]] = set()
    types: dict[str | None, set[str]] = {}
    for error in errors:
        field = format_location(_field_parts(error)) or None
        types.setdefault(field, set()).add(error["type"])
    for error in errors:
        field = format_location(_field_parts(error)) or None
        # `int | float`: „muss eine Zahl sein“ genügt, „ganze Zahl“ wäre irreführend.
        if error["type"] == "int_type" and "float_type" in types[field]:
            continue
        message = describe_error(error)
        if error["type"] == "missing" and field is None:
            message = "Die Anfrage braucht einen Inhalt (JSON)."
        if error["type"] == "json_invalid":
            message = "Die Anfrage ist kein gültiges JSON."
        if (field, message) not in seen:
            seen.add((field, message))
            result.append(FieldError(field=field, message=message))
    return result


def _sentence(error: FieldError) -> str:
    message = error.message.rstrip(".")
    if error.field is None:
        return message[:1].upper() + message[1:]
    if message == MESSAGES["extra_forbidden"]:
        return f"Unbekanntes Feld ‚{error.field}‘"
    # Ganze Sätze (aus den Schemas) stehen für sich, Teilsätze bekommen das Feld davor.
    if message[:1].isupper():
        return message
    return f"Feld ‚{error.field}‘: {message}"


def summarize(errors: Sequence[FieldError]) -> str:
    """Ein deutscher Satz über alle Fehler."""
    if not errors:
        return "Die Eingabe ist ungültig."
    if len(errors) == 1:
        return f"{_sentence(errors[0])}."
    return f"Die Eingabe enthält {len(errors)} Fehler: " + "; ".join(map(_sentence, errors)) + "."


def error_body(errors: Sequence[FieldError]) -> dict[str, Any]:
    return ValidationErrorOut(detail=summarize(errors), errors=list(errors)).model_dump()


class InputError(Exception):
    """Fachliche Eingabefehler mit Feldbezug, beantwortet wie ein Schemafehler (HTTP 422)."""

    def __init__(self, errors: Sequence[FieldError]) -> None:
        super().__init__(summarize(errors))
        self.errors = list(errors)

    @classmethod
    def single(cls, field: str | None, message: str) -> InputError:
        return cls([FieldError(field=field, message=message)])


class ConflictOut(BaseModel):
    """HTTP 409. Bezieht sich der Konflikt auf ein Eingabefeld, nennt `errors` es (wie bei 422)."""

    detail: str
    errors: list[FieldError] | None = None


class ConflictError(HTTPException):
    """Fachlicher Konflikt (HTTP 409), wahlweise mit Bezug auf ein Eingabefeld.

    `ConflictError("Bahn 2 ist schon belegt.", field="lane")` ergibt
    `{"detail": "…", "errors": [{"field": "lane", "message": "…"}]}`; ohne `field` nur `detail`.
    Als `HTTPException` bleibt es auch dort ein 409, wo der Handler nicht greift.
    """

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(status.HTTP_409_CONFLICT, message)
        self.field = field

    @property
    def errors(self) -> list[FieldError] | None:
        if self.field is None:
            return None
        return [FieldError(field=self.field, message=str(self.detail))]


def conflict_body(exc: ConflictError) -> dict[str, Any]:
    body: dict[str, Any] = {"detail": str(exc.detail)}
    errors = exc.errors
    if errors is not None:
        body["errors"] = [error.model_dump() for error in errors]
    return body


class CodedErrorOut(BaseModel):
    """Fehler mit maschinenlesbarem Grund (`code`), z. B. HTTP 401 mit `device_revoked`."""

    detail: str
    code: str


class CodedError(HTTPException):
    """HTTP-Fehler, der neben `detail` einen festen `code` mitgibt, an dem die Oberfläche den Fall
    unterscheidet (der Text darf sich ändern, der Code nicht)."""

    def __init__(
        self, status_code: int, detail: str, code: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(status_code, detail, headers=headers)
        self.code = code


async def _coded_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, CodedError)
    return JSONResponse(
        status_code=exc.status_code,
        content=CodedErrorOut(detail=str(exc.detail), code=exc.code).model_dump(),
        headers=exc.headers,
    )


def validation_response(errors: Sequence[FieldError]) -> JSONResponse:
    return JSONResponse(status_code=422, content=jsonable_encoder(error_body(errors)))


async def _conflict_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ConflictError)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=jsonable_encoder(conflict_body(exc)),
        headers=exc.headers,
    )


async def _request_validation_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return validation_response(translate_errors(exc.errors()))


async def _input_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, InputError)
    return validation_response(exc.errors)


def install_error_handlers(app: FastAPI) -> None:
    """Deutsche Fehlerantworten; die OpenAPI-Beschreibung zeigt die neue Form."""
    app.add_exception_handler(RequestValidationError, _request_validation_handler)
    app.add_exception_handler(InputError, _input_error_handler)
    app.add_exception_handler(ConflictError, _conflict_handler)
    app.add_exception_handler(CodedError, _coded_handler)

    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = generate()
            schemas = schema.get("components", {}).get("schemas", {})
            if "HTTPValidationError" in schemas:
                replacement = ValidationErrorOut.model_json_schema(
                    ref_template="#/components/schemas/{model}"
                )
                schemas.update(replacement.pop("$defs", {}))
                replacement["title"] = "HTTPValidationError"
                schemas["HTTPValidationError"] = replacement
                schemas.pop("ValidationError", None)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
