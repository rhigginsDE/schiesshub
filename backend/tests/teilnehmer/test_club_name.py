"""Verein beim Speichern der Person: `club_name` statt `club_id`.

Der Verein wird in derselben Transaktion wie die Person gesucht oder angelegt. Scheitert das
Speichern der Person, bleibt kein Verein zurück.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import func, select

from app.core import security
from app.core.events import EventHub
from app.modules.teilnehmer import service
from app.modules.teilnehmer.models import Club
from app.modules.teilnehmer.schemas import PersonCreate
from tests.teilnehmer.conftest import API, EventRecorder
from tests.teilnehmer.test_api import csv_body, import_csv, make_club, make_person, search

BOTH_MESSAGE = (
    "Bitte entweder einen vorhandenen Verein (club_id) oder einen Vereinsnamen (club_name) "
    "angeben, nicht beides."
)


async def club_names(api: httpx.AsyncClient) -> list[str]:
    return [club["name"] for club in (await api.get(f"{API}/clubs")).json()]


class Checker:
    """Prüfer, der mitschreibt, wonach gefragt wird, und `club.edit` wahlweise verweigert."""

    def __init__(self, *, club_edit: bool) -> None:
        self.club_edit = club_edit
        self.asked: list[str] = []

    async def __call__(self, request: Request, permission: str) -> security.Actor:
        self.asked.append(permission)
        if permission == "club.edit" and not self.club_edit:
            raise HTTPException(
                status_code=403, detail=f"Dafür fehlt die Berechtigung „{permission}“."
            )
        return security.Actor()


@pytest.fixture
def person_edit_only() -> Iterator[Checker]:
    checker = Checker(club_edit=False)
    security.set_permission_checker(checker)
    yield checker
    security.reset_permission_checker()


@pytest.fixture
def with_club_edit() -> Iterator[Checker]:
    checker = Checker(club_edit=True)
    security.set_permission_checker(checker)
    yield checker
    security.reset_permission_checker()


# --- Anlegen -----------------------------------------------------------------


async def test_create_with_new_club_name(api: httpx.AsyncClient, recorder: EventRecorder) -> None:
    person = await make_person(api, "Markus Brandt", club_name="  SV   Hubertus ")

    assert person["club_name"] == "SV Hubertus"
    assert person["display_club"] == "SV Hubertus"
    clubs = (await api.get(f"{API}/clubs")).json()
    assert [(c["id"], c["name"], c["person_count"]) for c in clubs] == [
        (person["club_id"], "SV Hubertus", 1)
    ]
    # Suchindex kennt den neuen Verein.
    assert await search(api, "hubertus") == ["Markus Brandt"]
    # Wie bei der normalen Vereinsanlage: Ereignis `club.created` mit der ID, nur IDs.
    events = [e for e in recorder.drain() if not e.name.startswith("katalog.")]
    assert [(e.name, e.data) for e in events] == [
        ("club.created", {"club_id": person["club_id"]}),
        ("person.created", {"person_id": person["id"]}),
    ]


async def test_create_finds_existing_club_like_the_search(
    api: httpx.AsyncClient, recorder: EventRecorder
) -> None:
    club = await make_club(api, "Schützengilde Köhlerwald")
    recorder.drain().clear()

    # Groß-/Kleinschreibung, Leerzeichen, Akzente und Umlaut-Schreibweise wie bei der Suche.
    for spelling in (
        "schützengilde köhlerwald",
        "  SCHUETZENGILDE   koehlerwald ",
        "Schutzengilde Kohlerwald",
    ):
        person = await make_person(api, "Anna Bergmann", club_name=spelling, display_mode="short")
        assert person["club_id"] == club["id"], spelling
        assert person["club_name"] == "Schützengilde Köhlerwald"
        await api.delete(f"{API}/persons/{person['id']}")

    assert await club_names(api) == ["Schützengilde Köhlerwald"]
    assert "club.created" not in recorder.names()


async def test_new_club_has_no_duplicates_of_persons_without_club(api: httpx.AsyncClient) -> None:
    await make_person(api, "Markus Brandt")

    # Gleicher Name ohne Verein ist im neuen Verein keine Dublette.
    person = await make_person(api, "Markus Brandt", club_name="SV Hubertus")

    assert person["club_name"] == "SV Hubertus"


async def test_duplicate_in_existing_club_keeps_clubs_unchanged(api: httpx.AsyncClient) -> None:
    club = await make_club(api, "SV Hubertus")
    existing = await make_person(api, "Jürgen Köhler", club_id=club["id"])

    duplicate = await api.post(
        f"{API}/persons", json={"name": "Juergen Koehler", "club_name": "sv hubertus"}
    )

    assert duplicate.status_code == 409
    assert [c["id"] for c in duplicate.json()["candidates"]] == [existing["id"]]
    assert await club_names(api) == ["SV Hubertus"]
    forced = await api.post(
        f"{API}/persons",
        params={"force": "true"},
        json={"name": "Juergen Koehler", "club_name": "sv hubertus"},
    )
    assert forced.status_code == 201
    assert forced.json()["club_id"] == club["id"]


async def test_club_id_and_club_name_together_are_rejected(api: httpx.AsyncClient) -> None:
    club = await make_club(api, "SV Hubertus")
    person = await make_person(api, "Markus Brandt")
    body = {"club_id": club["id"], "club_name": "Adler Nord"}

    created = await api.post(f"{API}/persons", json={"name": "Anna Bergmann", **body})
    changed = await api.patch(f"{API}/persons/{person['id']}", json=body)

    for response in (created, changed):
        assert response.status_code == 422
        assert response.json() == {
            "detail": BOTH_MESSAGE,
            "errors": [{"field": "club_name", "message": BOTH_MESSAGE}],
        }
    assert await club_names(api) == ["SV Hubertus"]
    assert (await api.get(f"{API}/persons")).headers["x-total-count"] == "1"


async def test_club_name_input_validation(api: httpx.AsyncClient) -> None:
    cases: list[dict[str, Any]] = [
        {"name": "Markus Brandt", "club_name": "   "},
        {"name": "Markus Brandt", "club_name": "x" * 201},
        {"name": "Markus Brandt", "club_name": 7},
        # Person ungültig: Der Verein darf nicht trotzdem entstehen.
        {"name": "", "club_name": "SV Hubertus"},
        {"name": "Markus Brandt", "display_mode": "voll", "club_name": "SV Hubertus"},
    ]
    for body in cases:
        response = await api.post(f"{API}/persons", json=body)
        assert response.status_code == 422, body
    assert await club_names(api) == []


async def test_club_name_null_means_not_given(api: httpx.AsyncClient) -> None:
    club = await make_club(api, "SV Hubertus")

    person = await make_person(api, "Markus Brandt", club_id=club["id"], club_name=None)
    changed = await api.patch(f"{API}/persons/{person['id']}", json={"club_name": None})

    assert person["club_id"] == club["id"]
    assert changed.status_code == 200
    assert changed.json()["club_id"] == club["id"]


async def test_failed_person_save_leaves_no_club(app: FastAPI, api: httpx.AsyncClient) -> None:
    # Die Datenbank lehnt die Person ab (CHECK auf display_mode), nachdem der Verein schon in
    # der Transaktion steckt.
    data = PersonCreate.model_construct(
        name="Markus Brandt",
        member_no=None,
        club_id=None,
        club_name="SV Hubertus",
        display_mode="voll",  # type: ignore[arg-type]
        show_club=True,
    )
    index = app.state.person_index
    async with app.state.session_factory() as session:
        with pytest.raises(Exception, match="display_mode"):
            await service.create_person(session, index, EventHub(), data, force=False)

    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Club)) == 0
    assert await club_names(api) == []
    assert await search(api, "hubertus") == []
    # Danach klappt es normal.
    person = await make_person(api, "Markus Brandt", club_name="SV Hubertus")
    assert person["club_name"] == "SV Hubertus"


# --- Ändern ------------------------------------------------------------------


async def test_update_with_club_name(api: httpx.AsyncClient, recorder: EventRecorder) -> None:
    club = await make_club(api, "SV Hubertus")
    person = await make_person(api, "Markus Brandt", club_id=club["id"])
    recorder.drain().clear()

    moved = await api.patch(f"{API}/persons/{person['id']}", json={"club_name": "Adler Nord"})
    assert moved.status_code == 200
    assert moved.json()["club_name"] == "Adler Nord"
    new_club_id = moved.json()["club_id"]
    assert new_club_id not in (None, club["id"])

    back = await api.patch(
        f"{API}/persons/{person['id']}", json={"club_name": "sv hubertus", "show_club": False}
    )
    assert back.json()["club_id"] == club["id"]
    assert back.json()["show_club"] is False

    assert await club_names(api) == ["Adler Nord", "SV Hubertus"]
    assert await search(api, "hubertus") == ["Markus Brandt"]
    assert recorder.names() == ["club.created", "person.updated", "person.updated"]


async def test_failed_update_leaves_no_club(api: httpx.AsyncClient) -> None:
    person = await make_person(api, "Markus Brandt")

    invalid = await api.patch(
        f"{API}/persons/{person['id']}", json={"club_name": "Adler Nord", "name": None}
    )
    missing = await api.patch(f"{API}/persons/{uuid.uuid4()}", json={"club_name": "Adler Nord"})

    assert invalid.status_code == 422
    assert missing.status_code == 404
    assert await club_names(api) == []


# --- Rechte ------------------------------------------------------------------

NO_CLUB_EDIT = (
    "Den Verein „Adler Nord“ gibt es noch nicht. Neue Vereine anlegen darf nur, wer die "
    "Berechtigung „club.edit“ hat. Bitte einen vorhandenen Verein wählen."
)


async def test_new_club_needs_club_edit(api: httpx.AsyncClient, person_edit_only: Checker) -> None:
    person_edit_only.club_edit = True
    await make_club(api, "SV Hubertus")
    other = await make_person(api, "Anna Bergmann")
    person_edit_only.club_edit = False
    person_edit_only.asked.clear()

    created = await api.post(
        f"{API}/persons", json={"name": "Markus Brandt", "club_name": "Adler Nord"}
    )
    changed = await api.patch(f"{API}/persons/{other['id']}", json={"club_name": "Adler Nord"})

    for response in (created, changed):
        assert response.status_code == 403
        assert response.json() == {"detail": NO_CLUB_EDIT}
    assert person_edit_only.asked == ["person.edit", "club.edit", "person.edit", "club.edit"]
    assert await club_names(api) == ["SV Hubertus"]
    persons = (await api.get(f"{API}/persons")).json()
    assert [(p["name"], p["club_id"]) for p in persons] == [("Anna Bergmann", None)]


async def test_existing_club_needs_only_person_edit(
    api: httpx.AsyncClient, person_edit_only: Checker
) -> None:
    person_edit_only.club_edit = True
    club = await make_club(api, "SV Hubertus")
    other = await make_person(api, "Anna Bergmann")
    person_edit_only.club_edit = False
    person_edit_only.asked.clear()

    created = await api.post(
        f"{API}/persons", json={"name": "Markus Brandt", "club_name": "SV HUBERTUS"}
    )
    changed = await api.patch(f"{API}/persons/{other['id']}", json={"club_name": "sv hubertus"})

    assert created.status_code == 201
    assert changed.status_code == 200
    assert created.json()["club_id"] == changed.json()["club_id"] == club["id"]
    # Nach `club.edit` wird gar nicht erst gefragt.
    assert person_edit_only.asked == ["person.edit", "person.edit"]


async def test_new_club_with_club_edit_asks_for_it(
    api: httpx.AsyncClient, with_club_edit: Checker
) -> None:
    person = await make_person(api, "Markus Brandt", club_name="Adler Nord")

    assert person["club_name"] == "Adler Nord"
    assert with_club_edit.asked == ["person.edit", "club.edit"]


# --- CSV-Import: gleiche Regel für neue Vereine --------------------------------

IMPORT_NO_CLUB_EDIT = (
    "Diese Vereine gibt es noch nicht: „Adler Nord“, „SV Tell“. Neue Vereine anlegen darf nur, "
    "wer die Berechtigung „club.edit“ hat. Es wurde nichts importiert. Bitte die Vereine zuerst "
    "anlegen lassen oder in der Datei vorhandene Vereine eintragen."
)

IMPORT_WITH_NEW_CLUBS = csv_body(
    "Name;Verein\n"
    "Markus Brandt;SV Tell\n"
    "Anna Bergmann;schuetzengilde\n"  # vorhanden: „Schützengilde“
    "Jürgen Köhler;Adler Nord\n"
    "Élodie Martin;ADLER NORD\n"
)


async def test_import_with_new_clubs_needs_club_edit(
    api: httpx.AsyncClient, person_edit_only: Checker, recorder: EventRecorder
) -> None:
    person_edit_only.club_edit = True
    await make_club(api, "Schützengilde")
    person_edit_only.club_edit = False
    recorder.drain().clear()
    person_edit_only.asked.clear()

    # Die Vorschau zeigt die neuen Vereine wie bisher und fragt nicht nach `club.edit`.
    preview = await import_csv(api, IMPORT_WITH_NEW_CLUBS, dry_run=True)
    assert preview.status_code == 200, preview.text
    assert preview.json()["new_clubs"] == ["Adler Nord", "SV Tell"]
    assert preview.json()["new"] == 4
    assert person_edit_only.asked == ["person.edit"]

    # Übernehmen: 403 mit den fehlenden Vereinen, nichts wird importiert.
    response = await import_csv(api, IMPORT_WITH_NEW_CLUBS)
    assert response.status_code == 403
    assert response.json() == {"detail": IMPORT_NO_CLUB_EDIT}
    assert person_edit_only.asked == ["person.edit", "person.edit", "club.edit"]
    assert await club_names(api) == ["Schützengilde"]
    assert (await api.get(f"{API}/persons")).headers["x-total-count"] == "0"
    assert recorder.names() == []


async def test_import_single_missing_club_message(
    api: httpx.AsyncClient, person_edit_only: Checker
) -> None:
    response = await import_csv(api, csv_body("Name;Verein\nMarkus Brandt;SV Tell\n"))

    assert response.status_code == 403
    assert response.json()["detail"].startswith(
        "Den Verein „SV Tell“ gibt es noch nicht. Neue Vereine anlegen darf nur, wer die "
        "Berechtigung „club.edit“ hat. Es wurde nichts importiert."
    )


async def test_import_into_existing_clubs_needs_only_person_edit(
    api: httpx.AsyncClient, person_edit_only: Checker
) -> None:
    person_edit_only.club_edit = True
    club = await make_club(api, "Schützengilde Köhlerwald")
    person_edit_only.club_edit = False
    person_edit_only.asked.clear()

    content = csv_body(
        "Name;Verein\n"
        "Markus Brandt;schuetzengilde koehlerwald\n"
        "Anna Bergmann;Schutzengilde Kohlerwald\n"
        "Jürgen Köhler;\n"
    )
    report = (await import_csv(api, content)).json()

    assert (report["new"], report["new_clubs"]) == (3, [])
    # Nach `club.edit` wird gar nicht erst gefragt.
    assert person_edit_only.asked == ["person.edit"]
    persons = {p["name"]: p["club_id"] for p in (await api.get(f"{API}/persons")).json()}
    assert persons == {
        "Markus Brandt": club["id"],
        "Anna Bergmann": club["id"],
        "Jürgen Köhler": None,
    }


async def test_import_with_new_clubs_and_club_edit(
    api: httpx.AsyncClient, with_club_edit: Checker
) -> None:
    await make_club(api, "Schützengilde")
    with_club_edit.asked.clear()

    report = (await import_csv(api, IMPORT_WITH_NEW_CLUBS)).json()

    assert (report["new"], report["new_clubs"]) == (4, ["Adler Nord", "SV Tell"])
    assert with_club_edit.asked == ["person.edit", "club.edit"]
    assert await club_names(api) == ["Adler Nord", "Schützengilde", "SV Tell"]


# --- Vereinsnamen: überall derselbe Vergleich (`names.fold`) -------------------


async def test_club_names_compare_with_fold_everywhere(api: httpx.AsyncClient) -> None:
    first = await make_club(api, "Schützengilde")
    other = await make_club(api, "Adler Nord")

    for spelling in ("Schutzengilde", "SCHUETZENGILDE", "Schützengílde"):
        created = await api.post(f"{API}/clubs", json={"name": spelling})
        assert created.status_code == 409, spelling
        assert created.json() == {
            "detail": f"Einen Verein mit dem Namen „{spelling}“ gibt es schon."
        }
    renamed = await api.patch(f"{API}/clubs/{other['id']}", json={"name": "Schuetzengilde"})
    assert renamed.status_code == 409
    # Die eigene Schreibweise ändern bleibt erlaubt.
    own = await api.patch(f"{API}/clubs/{first['id']}", json={"name": "Schuetzengilde"})
    assert own.status_code == 200
    assert own.json()["name"] == "Schuetzengilde"

    # club_name an der Person und der CSV-Import finden denselben Verein.
    person = await make_person(api, "Markus Brandt", club_name="Schützengilde")
    assert person["club_id"] == first["id"]
    report = (await import_csv(api, csv_body("Name;Verein\nAnna Bergmann;schutzengilde\n"))).json()
    assert report["new_clubs"] == []
    assert await club_names(api) == ["Adler Nord", "Schuetzengilde"]


async def test_import_rows_with_folded_club_names_share_one_new_club(
    api: httpx.AsyncClient,
) -> None:
    content = csv_body(
        "Name;Verein\nMarkus Brandt;Schützengilde\nAnna Bergmann;Schuetzengilde\n"
        "Markus Brandt;SCHUTZENGILDE\n"  # Dublette weiter oben in der Datei
    )

    report = (await import_csv(api, content)).json()

    assert (report["new"], report["duplicate"]) == (2, 1)
    assert report["new_clubs"] == ["Schützengilde"]
    clubs = (await api.get(f"{API}/clubs")).json()
    assert [(c["name"], c["person_count"]) for c in clubs] == [("Schützengilde", 2)]


# --- OpenAPI -----------------------------------------------------------------


async def test_openapi_describes_club_name(api: httpx.AsyncClient) -> None:
    schemas = (await api.get(f"{API}/openapi.json")).json()["components"]["schemas"]

    for model in ("PersonCreate", "PersonUpdate"):
        properties = schemas[model]["properties"]
        assert "club.edit" in properties["club_name"]["description"], model
        assert "club_name" in properties["club_id"]["description"], model
