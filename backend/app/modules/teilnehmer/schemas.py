"""Ein- und Ausgabeformate der Teilnehmer-API. Feldnamen englisch wie im Datenmodell."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints, model_validator

from app.modules.teilnehmer.names import DisplayMode

NAME_MAX = 200
MEMBER_NO_MAX = 50
CLUB_SHORT_MAX = 40

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX)]
MemberNo = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MEMBER_NO_MAX)
]
ClubShort = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CLUB_SHORT_MAX)
]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _reject_explicit_null(model: BaseModel, fields: tuple[str, ...]) -> None:
    for name in fields:
        if name in model.model_fields_set and getattr(model, name) is None:
            raise ValueError(f"Das Feld „{name}“ darf nicht leer sein.")


# --- Verein ------------------------------------------------------------------


class ClubCreate(_Input):
    name: Name
    short: ClubShort | None = None


class ClubUpdate(_Input):
    name: Name | None = None
    short: ClubShort | None = None

    @model_validator(mode="after")
    def _name_not_null(self) -> Self:
        _reject_explicit_null(self, ("name",))
        return self


class ClubMerge(_Input):
    # Ziel der Zusammenführung; der Verein aus dem Pfad wird danach gelöscht.
    into_id: UUID


class ClubOut(BaseModel):
    id: UUID
    name: str
    short: str | None
    person_count: int
    created_at: datetime
    updated_at: datetime


# --- Person ------------------------------------------------------------------


class PersonCreate(_Input):
    name: Name
    member_no: MemberNo | None = None
    club_id: UUID | None = None
    display_mode: DisplayMode = "full"
    show_club: StrictBool = True


class PersonUpdate(_Input):
    name: Name | None = None
    member_no: MemberNo | None = None
    club_id: UUID | None = None
    display_mode: DisplayMode | None = None
    show_club: StrictBool | None = None

    @model_validator(mode="after")
    def _required_not_null(self) -> Self:
        _reject_explicit_null(self, ("name", "display_mode", "show_club"))
        return self


class PersonOut(BaseModel):
    id: UUID
    # Klartext, nur über Endpunkte mit der Berechtigung `person.read`.
    name: str
    member_no: str | None
    club_id: UUID | None
    club_name: str | None
    display_mode: DisplayMode
    show_club: bool
    # Wie die Person auf Anzeige und Listen erscheint: voll, abgekürzt oder gar nicht (null).
    display_name: str | None
    # Verein für Anzeige und Listen; null, wenn kein Verein oder `show_club` aus ist.
    display_club: str | None
    created_at: datetime
    updated_at: datetime


class DuplicateOut(BaseModel):
    """Antwort 409 beim Anlegen: ähnliche Personen im selben Verein."""

    detail: str
    candidates: list[PersonOut]


# --- Import ------------------------------------------------------------------


class ImportRowOut(BaseModel):
    # Zeilennummer in der Datei (Kopfzeile = 1).
    line: int
    status: Literal["new", "duplicate", "error"]
    message: str | None = None
    # new: angelegte Person (null bei dry_run) · duplicate: vorhandene Person (null, wenn die
    # Dublette weiter oben in derselben Datei steht).
    person_id: UUID | None = None


class ImportReportOut(BaseModel):
    dry_run: bool
    new: int
    duplicate: int
    error: int
    # Vereine, die fehlten und angelegt wurden (bei dry_run: angelegt würden).
    new_clubs: list[str]
    rows: list[ImportRowOut]
