"""API der Teilnehmer gegen die echte PostgreSQL-Testdatenbank."""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core import security
from app.core.crypto import FieldCipher, KeyStoreError, key_file_path, load_keyring, rotate_key
from app.modules.teilnehmer import manifest, service
from tests.conftest import running
from tests.teilnehmer.conftest import API, AppFactory, EventRecorder

# --- Hilfen ------------------------------------------------------------------


async def make_club(api: httpx.AsyncClient, name: str, short: str | None = None) -> dict:
    body: dict[str, Any] = {"name": name}
    if short is not None:
        body["short"] = short
    response = await api.post(f"{API}/clubs", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def make_person(api: httpx.AsyncClient, name: str, **fields: Any) -> dict:
    response = await api.post(f"{API}/persons", json={"name": name, **fields})
    assert response.status_code == 201, response.text
    return response.json()


async def search(api: httpx.AsyncClient, q: str) -> list[str]:
    response = await api.get(f"{API}/persons", params={"q": q})
    assert response.status_code == 200, response.text
    return [person["name"] for person in response.json()]


def csv_body(content: str, *, bom: bool = False) -> bytes:
    return ("﻿" if bom else "").encode() + content.encode("utf-8")


async def import_csv(
    api: httpx.AsyncClient, content: bytes, *, dry_run: bool = False
) -> httpx.Response:
    return await api.post(
        f"{API}/persons/import",
        params={"dry_run": str(dry_run).lower()},
        content=content,
        headers={"Content-Type": "text/csv"},
    )


# --- Vereine -----------------------------------------------------------------


async def test_club_crud(api: httpx.AsyncClient, recorder: EventRecorder) -> None:
    club = await make_club(api, "  SV   Brandenburg ", short="SVB")
    assert club["name"] == "SV Brandenburg"
    assert club["short"] == "SVB"
    assert club["person_count"] == 0

    fetched = await api.get(f"{API}/clubs/{club['id']}")
    assert fetched.json() == club

    changed = await api.patch(f"{API}/clubs/{club['id']}", json={"short": None})
    assert changed.status_code == 200
    assert changed.json()["short"] is None
    assert changed.json()["name"] == "SV Brandenburg"

    renamed = await api.patch(f"{API}/clubs/{club['id']}", json={"name": "SV Brandenburg 1890"})
    assert renamed.json()["name"] == "SV Brandenburg 1890"

    await make_club(api, "Adler Nord")
    listed = (await api.get(f"{API}/clubs")).json()
    assert [c["name"] for c in listed] == ["Adler Nord", "SV Brandenburg 1890"]

    deleted = await api.delete(f"{API}/clubs/{club['id']}")
    assert deleted.status_code == 204
    missing = await api.get(f"{API}/clubs/{club['id']}")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Diesen Verein gibt es nicht."}

    assert recorder.names() == [
        "club.created",
        "club.updated",
        "club.updated",
        "club.created",
        "club.deleted",
    ]


async def test_club_name_is_unique_ignoring_case(api: httpx.AsyncClient) -> None:
    first = await make_club(api, "SV Brandenburg")
    other = await make_club(api, "Adler Nord")

    duplicate = await api.post(f"{API}/clubs", json={"name": "sv BRANDENBURG"})
    rename = await api.patch(f"{API}/clubs/{other['id']}", json={"name": "SV brandenburg"})
    same = await api.patch(f"{API}/clubs/{first['id']}", json={"name": "SV BRANDENBURG"})

    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "Einen Verein mit dem Namen „sv BRANDENBURG“ gibt es schon."
    }
    assert rename.status_code == 409
    # Die eigene Schreibweise ändern ist erlaubt.
    assert same.status_code == 200
    assert same.json()["name"] == "SV BRANDENBURG"


async def test_club_unique_index_holds_in_the_database(
    engine: AsyncEngine, api: httpx.AsyncClient
) -> None:
    await make_club(api, "SV Brandenburg")

    async with engine.connect() as connection:
        with pytest.raises(Exception, match="uq_club_name_ci"):
            await connection.execute(
                text("INSERT INTO club (id, name) VALUES (gen_random_uuid(), 'SV BRANDENBURG')")
            )


async def test_club_input_is_strict(api: httpx.AsyncClient) -> None:
    unknown = await api.post(f"{API}/clubs", json={"name": "SV", "farbe": "blau"})
    empty = await api.post(f"{API}/clubs", json={"name": "   "})
    null_name = await api.patch(f"{API}/clubs/{uuid.uuid4()}", json={"name": None})

    assert unknown.status_code == 422
    assert empty.status_code == 422
    assert null_name.status_code == 422


async def test_club_with_persons_cannot_be_deleted(api: httpx.AsyncClient) -> None:
    club = await make_club(api, "SV Brandenburg")
    await make_person(api, "Markus Brandt", club_id=club["id"])

    response = await api.delete(f"{API}/clubs/{club['id']}")

    assert response.status_code == 409
    assert "noch 1 Person(en)" in response.json()["detail"]


async def test_merge_clubs(api: httpx.AsyncClient, recorder: EventRecorder) -> None:
    source = await make_club(api, "SV Brandenburg e.V.")
    target = await make_club(api, "SV Brandenburg")
    moved = [
        await make_person(api, "Markus Brandt", club_id=source["id"]),
        await make_person(api, "Anna Bergmann", club_id=source["id"]),
    ]
    stays = await make_person(api, "Jürgen Köhler", club_id=target["id"])
    recorder.drain().clear()

    response = await api.post(f"{API}/clubs/{source['id']}/merge", json={"into_id": target["id"]})

    assert response.status_code == 200
    assert response.json()["id"] == target["id"]
    assert response.json()["person_count"] == 3
    assert (await api.get(f"{API}/clubs/{source['id']}")).status_code == 404
    for person in [*moved, stays]:
        body = (await api.get(f"{API}/persons/{person['id']}")).json()
        assert body["club_id"] == target["id"]
        assert body["club_name"] == "SV Brandenburg"
    # Der Suchindex kennt den neuen Verein, den alten nicht mehr.
    assert await search(api, "e.v.") == []
    assert sorted(await search(api, "brandenburg")) == [
        "Anna Bergmann",
        "Jürgen Köhler",
        "Markus Brandt",
    ]

    [event] = recorder.drain()
    assert event.name == "club.merged"
    assert event.data["club_id"] == source["id"]
    assert event.data["into_id"] == target["id"]
    assert sorted(event.data["person_ids"]) == sorted(p["id"] for p in moved)


async def test_merge_errors(api: httpx.AsyncClient) -> None:
    club = await make_club(api, "SV Brandenburg")
    unknown = str(uuid.uuid4())

    itself = await api.post(f"{API}/clubs/{club['id']}/merge", json={"into_id": club["id"]})
    no_source = await api.post(f"{API}/clubs/{unknown}/merge", json={"into_id": club["id"]})
    no_target = await api.post(f"{API}/clubs/{club['id']}/merge", json={"into_id": unknown})

    assert itself.status_code == 409
    assert (
        itself.json()["detail"] == "Ein Verein kann nicht mit sich selbst zusammengeführt werden."
    )
    assert no_source.status_code == 404
    assert no_target.status_code == 422
    assert no_target.json()["detail"] == "Den Zielverein der Zusammenführung gibt es nicht."


# --- Personen ----------------------------------------------------------------


async def test_person_crud_and_display(api: httpx.AsyncClient, recorder: EventRecorder) -> None:
    club = await make_club(api, "SV Brandenburg")
    person = await make_person(
        api, " Markus   Brandt ", member_no="4711", club_id=club["id"], display_mode="short"
    )

    assert person | {"id": None, "created_at": None, "updated_at": None} == {
        "id": None,
        "name": "Markus Brandt",
        "member_no": "4711",
        "club_id": club["id"],
        "club_name": "SV Brandenburg",
        "display_mode": "short",
        "show_club": True,
        "display_name": "M. Brandt",
        "display_club": "SV Brandenburg",
        "created_at": None,
        "updated_at": None,
    }
    assert (await api.get(f"{API}/persons/{person['id']}")).json() == person

    hidden = await api.patch(
        f"{API}/persons/{person['id']}", json={"display_mode": "hidden", "show_club": False}
    )
    assert hidden.status_code == 200
    assert hidden.json()["display_name"] is None
    assert hidden.json()["display_club"] is None
    assert hidden.json()["club_name"] == "SV Brandenburg"

    full = await api.patch(
        f"{API}/persons/{person['id']}",
        json={
            "display_mode": "full",
            "name": "Markus Peter Brandt",
            "member_no": None,
            "club_id": None,
        },
    )
    assert full.json()["display_name"] == "Markus Peter Brandt"
    assert full.json()["member_no"] is None
    assert full.json()["club_id"] is None
    assert full.json()["club_name"] is None
    assert full.json()["updated_at"] >= person["updated_at"]

    deleted = await api.delete(f"{API}/persons/{person['id']}")
    assert deleted.status_code == 204
    assert (await api.get(f"{API}/persons/{person['id']}")).status_code == 404
    assert (await api.delete(f"{API}/persons/{person['id']}")).status_code == 404
    assert await search(api, "brandt") == []

    assert recorder.names() == [
        "club.created",
        "person.created",
        "person.updated",
        "person.updated",
        "person.deleted",
    ]


async def test_person_input_validation(api: httpx.AsyncClient) -> None:
    base = f"{API}/persons"
    cases = [
        {"name": ""},
        {"name": "x" * 201},
        {"name": "Markus Brandt", "display_mode": "voll"},
        {"name": "Markus Brandt", "show_club": "ja"},
        {"name": "Markus Brandt", "birth_year": 1980},
        {"name": "Markus Brandt", "birthdate": "1980-01-01"},
        {"name": "Markus Brandt", "member_no": "1" * 51},
    ]
    for body in cases:
        response = await api.post(base, json=body)
        assert response.status_code == 422, body

    unknown_club = await api.post(
        base, json={"name": "Markus Brandt", "club_id": str(uuid.uuid4())}
    )
    assert unknown_club.status_code == 422
    assert unknown_club.json() == {"detail": "Den angegebenen Verein gibt es nicht."}

    person = await make_person(api, "Markus Brandt")
    for body in ({"name": None}, {"display_mode": None}, {"show_club": None}, {"x": 1}):
        response = await api.patch(f"{base}/{person['id']}", json=body)
        assert response.status_code == 422, body
    assert (await api.patch(f"{base}/{uuid.uuid4()}", json={"name": "X"})).status_code == 404


async def test_no_birth_date_anywhere(engine: AsyncEngine, api: httpx.AsyncClient) -> None:
    async with engine.connect() as connection:
        columns = (
            await connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name IN ('person', 'club')"
                )
            )
        ).scalars()
        names = set(columns)
    schema = (await api.get(f"{API}/openapi.json")).json()["components"]["schemas"]

    assert not {n for n in names if "birth" in n or "geburt" in n}
    for model in ("PersonCreate", "PersonUpdate", "PersonOut"):
        assert not [f for f in schema[model]["properties"] if "birth" in f or "geburt" in f]


async def test_names_are_encrypted_in_the_database(
    engine: AsyncEngine, api: httpx.AsyncClient, data_dir: Path
) -> None:
    club = await make_club(api, "SV Brandenburg")
    person = await make_person(api, "Jürgen Köhler", member_no="MG-4711", club_id=club["id"])

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text("SELECT name_enc, member_no_enc, person::text AS whole FROM person")
            )
        ).one()

    cipher = FieldCipher(load_keyring(data_dir / "keys", create=False))
    assert cipher.decrypt(row.name_enc) == "Jürgen Köhler"
    assert cipher.decrypt(row.member_no_enc) == "MG-4711"
    for plain in ("Köhler", "Jürgen", "4711"):
        assert plain.encode() not in row.name_enc
        assert plain.encode() not in row.member_no_enc
        assert plain not in row.whole
    assert person["name"] == "Jürgen Köhler"


# --- Suche -------------------------------------------------------------------


async def test_search_ignores_case_accents_and_umlaut_spelling(api: httpx.AsyncClient) -> None:
    club = await make_club(api, "Schützenverein Weißenfels")
    await make_person(api, "Jürgen Köhler", member_no="4711", club_id=club["id"])
    await make_person(api, "Markus Brandt", member_no="0815")
    await make_person(api, "Élodie Martin")

    for query in ("köhler", "KOEHLER", "kohler", "Koeh", "jurgen kohler"):
        assert await search(api, query) == ["Jürgen Köhler"], query
    assert await search(api, "elodie") == ["Élodie Martin"]
    # Mitgliedsnummer und Vereinsname
    assert await search(api, "0815") == ["Markus Brandt"]
    assert await search(api, "schuetzenverein") == ["Jürgen Köhler"]
    assert await search(api, "weissenfels") == ["Jürgen Köhler"]
    assert await search(api, "zzz") == []


async def test_search_puts_prefix_matches_first(api: httpx.AsyncClient) -> None:
    for name in ("Klaus Schönberg", "Anna Bergmann", "Bergner Klaus"):
        await make_person(api, name)

    assert await search(api, "berg") == ["Bergner Klaus", "Anna Bergmann", "Klaus Schönberg"]


async def test_list_without_query_is_sorted_and_paged(api: httpx.AsyncClient) -> None:
    for name in ("Markus Brandt", "Anna Bergmann", "Jürgen Köhler"):
        await make_person(api, name)

    everything = await api.get(f"{API}/persons")
    page = await api.get(f"{API}/persons", params={"limit": 1, "offset": 1})

    assert [p["name"] for p in everything.json()] == [
        "Anna Bergmann",
        "Jürgen Köhler",
        "Markus Brandt",
    ]
    assert everything.headers["x-total-count"] == "3"
    assert [p["name"] for p in page.json()] == ["Jürgen Köhler"]
    assert page.headers["x-total-count"] == "3"


async def test_index_is_rebuilt_after_restart(make_app: AppFactory) -> None:
    async with running(make_app()) as api:
        club = await make_club(api, "SV Brandenburg")
        await make_person(api, "Jürgen Köhler", club_id=club["id"])

    async with running(make_app()) as api:
        assert await search(api, "koehler") == ["Jürgen Köhler"]
        assert await search(api, "brandenburg") == ["Jürgen Köhler"]


async def test_rotated_key_reads_old_rows_and_writes_new_ones(
    make_app: AppFactory, engine: AsyncEngine, data_dir: Path
) -> None:
    async with running(make_app()) as api:
        old = await make_person(api, "Markus Brandt")
    old_key = FieldCipher(load_keyring(data_dir / "keys", create=False)).active_key_id

    new_key = rotate_key(data_dir / "keys").active_id
    async with running(make_app()) as api:
        assert await search(api, "brandt") == ["Markus Brandt"]
        assert (await api.get(f"{API}/persons/{old['id']}")).json()["name"] == "Markus Brandt"
        fresh = await make_person(api, "Anna Bergmann")
        # Eine echte Änderung schreibt den Wert neu, jetzt mit dem neuen Schlüssel.
        await api.patch(f"{API}/persons/{old['id']}", json={"name": "Markus P. Brandt"})

    async with engine.connect() as connection:
        rows = dict((await connection.execute(text("SELECT id::text, name_enc FROM person"))).all())
    assert FieldCipher.key_id_of(rows[fresh["id"]]) == new_key
    assert FieldCipher.key_id_of(rows[old["id"]]) == new_key
    assert old_key != new_key


async def test_start_refuses_new_key_when_encrypted_data_exists(
    make_app: AppFactory, data_dir: Path
) -> None:
    async with running(make_app()) as api:
        await make_person(api, "Markus Brandt")
    key_file_path(data_dir / "keys").unlink()

    with pytest.raises(KeyStoreError, match="aus der Sicherung wiederherstellen"):
        async with running(make_app()):
            pass
    assert not key_file_path(data_dir / "keys").exists()


# --- Dubletten ---------------------------------------------------------------


async def test_duplicate_hint_on_create(api: httpx.AsyncClient) -> None:
    club = await make_club(api, "SV Brandenburg")
    other = await make_club(api, "Adler Nord")
    existing = await make_person(api, "Jürgen Köhler", club_id=club["id"])

    duplicate = await api.post(
        f"{API}/persons", json={"name": "juergen  KOEHLER", "club_id": club["id"]}
    )
    assert duplicate.status_code == 409
    body = duplicate.json()
    assert body["detail"].startswith("Eine Person mit diesem Namen gibt es in diesem Verein schon.")
    assert [c["id"] for c in body["candidates"]] == [existing["id"]]
    assert body["candidates"][0]["name"] == "Jürgen Köhler"

    # Anderer Verein oder ohne Verein: kein Hinweis.
    await make_person(api, "Jürgen Köhler", club_id=other["id"])
    await make_person(api, "Jürgen Köhler")
    # Mit force=true trotzdem anlegen.
    forced = await api.post(
        f"{API}/persons",
        params={"force": "true"},
        json={"name": "Jürgen Köhler", "club_id": club["id"]},
    )
    assert forced.status_code == 201
    assert len(await search(api, "köhler")) == 4


# --- Import und Export -------------------------------------------------------


async def test_import_dry_run_reports_without_saving(
    api: httpx.AsyncClient, recorder: EventRecorder
) -> None:
    club = await make_club(api, "SV Brandenburg")
    await make_person(api, "Markus Brandt", club_id=club["id"])
    recorder.drain().clear()
    content = csv_body(
        "Name;Verein;Mitgliedsnummer\n"
        "Markus Brandt;sv brandenburg;1\n"  # Dublette in der Datenbank
        "Anna Bergmann;Adler Nord;2\n"  # neu, neuer Verein
        ";Adler Nord;3\n"  # Fehler: Name fehlt
        "Anna Bergmann;ADLER NORD;\n"  # Dublette weiter oben in der Datei
        "\n"
        "Jürgen Köhler;;\n"  # neu, ohne Verein
    )

    response = await import_csv(api, content, dry_run=True)

    assert response.status_code == 200, response.text
    report = response.json()
    assert report["dry_run"] is True
    assert (report["new"], report["duplicate"], report["error"]) == (2, 2, 1)
    assert report["new_clubs"] == ["Adler Nord"]
    assert [(row["line"], row["status"]) for row in report["rows"]] == [
        (2, "duplicate"),
        (3, "new"),
        (4, "error"),
        (5, "duplicate"),
        (7, "new"),
    ]
    assert report["rows"][0]["person_id"] is not None
    assert report["rows"][2]["message"] == "Der Name fehlt."
    assert all(row["person_id"] is None for row in report["rows"] if row["status"] == "new")
    # Nichts gespeichert, kein Ereignis.
    assert (await api.get(f"{API}/persons")).headers["x-total-count"] == "1"
    assert [c["name"] for c in (await api.get(f"{API}/clubs")).json()] == ["SV Brandenburg"]
    assert recorder.names() == []


async def test_import_creates_persons_and_missing_clubs(
    api: httpx.AsyncClient, recorder: EventRecorder
) -> None:
    content = csv_body(
        "name,club,member_no,display_mode,show_club\n"
        '"Brandt, Markus",SV Brandenburg,4711,short,false\n'
        "Anna Bergmann,SV Brandenburg,,kurz,nein\n"
        "Jürgen Köhler,Adler Nord,0815,,\n"
        "Élodie Martin,,,verborgen,ja\n"
        "Kaputt,,,irgendwie,\n",
        bom=True,
    )

    response = await import_csv(api, content)

    report = response.json()
    assert (report["new"], report["duplicate"], report["error"]) == (4, 0, 1)
    assert report["new_clubs"] == ["Adler Nord", "SV Brandenburg"]
    assert "irgendwie" in report["rows"][4]["message"]
    created = {row["person_id"] for row in report["rows"] if row["status"] == "new"}
    assert None not in created

    persons = {p["name"]: p for p in (await api.get(f"{API}/persons")).json()}
    assert set(persons) == {"Brandt, Markus", "Anna Bergmann", "Jürgen Köhler", "Élodie Martin"}
    assert {p["id"] for p in persons.values()} == created
    assert persons["Brandt, Markus"]["member_no"] == "4711"
    assert persons["Brandt, Markus"]["display_mode"] == "short"
    assert persons["Brandt, Markus"]["show_club"] is False
    assert persons["Anna Bergmann"]["display_name"] == "A. Bergmann"
    assert persons["Anna Bergmann"]["club_id"] == persons["Brandt, Markus"]["club_id"]
    assert persons["Jürgen Köhler"]["display_mode"] == "full"
    assert persons["Jürgen Köhler"]["show_club"] is True
    assert persons["Élodie Martin"]["display_mode"] == "hidden"
    assert persons["Élodie Martin"]["club_id"] is None
    clubs = (await api.get(f"{API}/clubs")).json()
    assert [(c["name"], c["person_count"]) for c in clubs] == [
        ("Adler Nord", 1),
        ("SV Brandenburg", 2),
    ]
    # Suchindex ist nachgeführt.
    assert await search(api, "koehler") == ["Jürgen Köhler"]

    events = [e for e in recorder.drain() if not e.name.startswith("katalog.")]
    assert [e.name for e in events] == ["club.created", "club.created", "person.imported"]
    assert sorted(events[-1].data["person_ids"]) == sorted(created)

    # Zweiter Import derselben Datei: alles Dubletten.
    again = (await import_csv(api, content)).json()
    assert (again["new"], again["duplicate"], again["error"]) == (0, 4, 1)
    assert again["new_clubs"] == []


async def test_import_rejects_unusable_files(api: httpx.AsyncClient) -> None:
    cases = {
        b"": "Die Datei ist leer.",
        b"Verein;Mitgliedsnummer\nSV;1\n": "Die Kopfzeile braucht eine Spalte „Name“",
        b"Mitgliederliste 2026\nMarkus Brandt\n": "Die Kopfzeile braucht eine Spalte „Name“",
        b"name;Name\nA;B\n": "Die Spalte „Name“ kommt doppelt vor.",
        b"Verein;Vereinsname;Name\nA;B;C\n": "Die Spalten „Verein“ und „Vereinsname“ meinen",
        b"Vorname;Verein\nMarkus;SV\n": "Zur Spalte „Vorname“ fehlt die Spalte „Nachname“.",
        b"Nachname;Verein\nBrandt;SV\n": "Zur Spalte „Nachname“ fehlt die Spalte „Vorname“.",
        b"Name;Vorname;Nachname\nA;B;C\n": "Die Spalten „Name“ und „Nachname“ meinen",
        b"Vor- und Nachname;Vorname;Nachname\nA;B;C\n": "Die Datei hat eine Spalte",
        # 0x81 ist auch in Windows-1252 kein Zeichen.
        b"Name\nK\x81hler\n": "Die Datei enthält Zeichen, die sich nicht lesen lassen.",
    }
    for content, message in cases.items():
        response = await import_csv(api, content)
        assert response.status_code == 400, content
        assert response.json()["detail"].startswith(message), (content, response.json())

    too_many = await import_csv(api, b"name\nA;B\n")
    assert too_many.status_code == 200
    assert too_many.json()["rows"][0]["status"] == "error"
    assert too_many.json()["rows"][0]["message"].startswith("Die Zeile hat 2 Werte")


async def test_import_reads_windows_1252(api: httpx.AsyncClient) -> None:
    # So speichert Excel unter Windows „CSV (Trennzeichen-getrennt)“: cp1252, Semikolon, CRLF.
    content = "Name;Verein\r\nJürgen Köhler;Schützengilde Groß-Gerau\r\nÉlodie Maß;\r\n".encode(
        "cp1252"
    )
    with pytest.raises(UnicodeDecodeError):
        content.decode("utf-8")

    report = (await import_csv(api, content)).json()

    assert report["new"] == 2
    assert [(row["name"], row["club"]) for row in report["rows"]] == [
        ("Jürgen Köhler", "Schützengilde Groß-Gerau"),
        ("Élodie Maß", None),
    ]
    assert report["new_clubs"] == ["Schützengilde Groß-Gerau"]
    assert sorted(await search(api, "koehler")) == ["Jürgen Köhler"]
    # UTF-8 mit und ohne BOM bleibt, wie es war.
    for bom in (False, True):
        again = await import_csv(api, csv_body("Name\nJürgen Köhler\n", bom=bom), dry_run=True)
        assert again.json()["rows"][0]["name"] == "Jürgen Köhler"


async def test_import_ignores_unknown_columns(
    api: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    content = csv_body(
        "Mitglieds-Nr.;Anrede;Vorname;Nachname;Straße;PLZ;E-Mail;Geburtsdatum;Geburtsjahr;"
        "Verein;\n"
        "4711;Herr;Markus;Brandt;Lindenweg 3;12345;markus@example.org;01.02.1980;1980;"
        "SV Tell;\n"
    )

    report = (await import_csv(api, content)).json()

    assert report["ignored_columns"] == [
        "Anrede",
        "Straße",
        "PLZ",
        "E-Mail",
        "Geburtsdatum",
        "Geburtsjahr",
    ]
    assert report["new"] == 1
    assert report["rows"][0]["name"] == "Markus Brandt"
    (person,) = (await api.get(f"{API}/persons")).json()
    assert (person["name"], person["member_no"], person["club_name"]) == (
        "Markus Brandt",
        "4711",
        "SV Tell",
    )
    # Die Werte der ignorierten Spalten stehen nirgends: nicht in Antwort, Person oder Protokoll.
    stored = json.dumps([report, person], ensure_ascii=False)
    app_logs = "\n".join(
        r.getMessage() for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))
    )
    # (Reine Ziffernfolgen wie PLZ oder Jahr nicht prüfen: Sie können zufällig in UUIDs stehen.)
    for value in ("Herr", "Lindenweg", "markus@example.org", "01.02.1980"):
        assert value not in stored
        assert value not in app_logs
    # Nur bekannte Spalten: nichts ignoriert.
    plain = (await import_csv(api, csv_body("Name\nAnna Bergmann\n"), dry_run=True)).json()
    assert plain["ignored_columns"] == []


async def test_import_joins_first_and_last_name(api: httpx.AsyncClient) -> None:
    club = await make_club(api, "SV Tell")
    await make_person(api, "Markus Brandt", club_id=club["id"])
    content = csv_body(
        "VORNAME ; Familienname ;vereinsname;Mitgliedsnummer\n"
        "Markus;Brandt;sv tell;1\n"  # Dublette in der Datenbank
        "Hans-Peter;von der Leyen;SV Tell;2\n"
        "  Anna  ;  Bergmann ;;3\n"
        ";;SV Tell;4\n"  # Fehler: kein Name
        "Cher;;;5\n"  # nur ein Name: erlaubt
    )

    report = (await import_csv(api, content)).json()

    assert [(row["line"], row["status"], row["name"]) for row in report["rows"]] == [
        (2, "duplicate", "Markus Brandt"),
        (3, "new", "Hans-Peter von der Leyen"),
        (4, "new", "Anna Bergmann"),
        (5, "error", None),
        (6, "new", "Cher"),
    ]
    assert report["rows"][3]["message"] == "Vorname und Nachname fehlen."
    assert report["rows"][3]["club"] == "SV Tell"
    persons = {p["name"]: p for p in (await api.get(f"{API}/persons")).json()}
    assert persons["Hans-Peter von der Leyen"]["club_id"] == club["id"]
    assert persons["Hans-Peter von der Leyen"]["display_name"] == "Hans-Peter von der Leyen"
    assert persons["Anna Bergmann"]["club_id"] is None

    # „Name“ neben „Vorname“ ist der Nachname.
    other = (await import_csv(api, csv_body("Vorname,Name\nJürgen,Köhler\n"), dry_run=True)).json()
    assert other["rows"][0]["name"] == "Jürgen Köhler"


async def test_import_detects_delimiter(api: httpx.AsyncClient) -> None:
    variants = {
        "Semikolon": 'Name;Verein\n"Brandt; Markus";SV Tell, Nord\n',
        "Komma": 'Name,Verein\n"Brandt, Markus","SV Tell, Nord"\n',
        "Tabulator": "Name\tVerein\nBrandt, Markus\tSV Tell, Nord\n",
    }
    expected = {"Semikolon": "Brandt; Markus"}
    for label, content in variants.items():
        report = (await import_csv(api, csv_body(content), dry_run=True)).json()
        assert report["error"] == 0, label
        row = report["rows"][0]
        assert (row["name"], row["club"]) == (
            expected.get(label, "Brandt, Markus"),
            "SV Tell, Nord",
        ), label


async def test_import_limits_file_size(api: httpx.AsyncClient) -> None:
    response = await import_csv(api, b"name\n" + b"A\n" * (3 * 1024 * 1024))

    assert response.status_code == 413
    assert response.json() == {"detail": "Die Datei ist größer als 5 MB."}


async def test_export_and_reimport_roundtrip(api: httpx.AsyncClient, make_app: AppFactory) -> None:
    club = await make_club(api, "SV Brandenburg")
    await make_person(api, "Markus Brandt", member_no="4711", club_id=club["id"], show_club=False)
    await make_person(api, "Anna Bergmann", display_mode="short")
    await make_person(api, '=HYPERLINK("x")', member_no="+49")

    response = await api.get(f"{API}/persons/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="personen.csv"'
    raw = response.content
    assert raw.startswith("﻿".encode())
    lines = raw.decode("utf-8-sig").splitlines()
    assert lines == [
        "name;club;member_no;display_mode;show_club",
        # Formel entschärft; wegen der Anführungszeichen steht die Zelle selbst in welchen.
        '"\'=HYPERLINK(""x"")";;\'+49;full;true',
        "Anna Bergmann;;;short;true",
        "Markus Brandt;SV Brandenburg;4711;full;false",
    ]

    # Wieder einlesen in eine leere Datenbank ergibt dieselben Daten.
    before = sorted(
        (p["name"], p["member_no"], p["club_name"], p["display_mode"], p["show_club"])
        for p in (await api.get(f"{API}/persons")).json()
    )
    for person in (await api.get(f"{API}/persons")).json():
        await api.delete(f"{API}/persons/{person['id']}")
    await api.delete(f"{API}/clubs/{club['id']}")
    report = (await import_csv(api, raw)).json()
    after = sorted(
        (p["name"], p["member_no"], p["club_name"], p["display_mode"], p["show_club"])
        for p in (await api.get(f"{API}/persons")).json()
    )
    assert report["new"] == 3
    assert after == before


# --- Löschen -----------------------------------------------------------------


async def test_other_modules_can_block_deletion(api: httpx.AsyncClient) -> None:
    keep = await make_person(api, "Markus Brandt")
    free = await make_person(api, "Anna Bergmann")
    asked: list[uuid.UUID] = []

    async def has_entries(session: AsyncSession, person_id: uuid.UUID) -> str | None:
        asked.append(person_id)
        await session.execute(text("SELECT 1"))
        if str(person_id) == keep["id"]:
            return "Die Person ist in einem laufenden Turnier angemeldet."
        return None

    service.register_person_deletion_check(has_entries)
    try:
        blocked = await api.delete(f"{API}/persons/{keep['id']}")
        allowed = await api.delete(f"{API}/persons/{free['id']}")
    finally:
        service.unregister_person_deletion_check(has_entries)

    assert blocked.status_code == 409
    assert blocked.json() == {"detail": "Die Person ist in einem laufenden Turnier angemeldet."}
    assert allowed.status_code == 204
    assert [str(i) for i in asked] == [keep["id"], free["id"]]
    assert (await api.get(f"{API}/persons/{keep['id']}")).status_code == 200
    # Ohne Prüfer darf gelöscht werden.
    assert (await api.delete(f"{API}/persons/{keep['id']}")).status_code == 204


async def test_can_delete_person_without_checks(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        assert await service.can_delete_person(session, uuid.uuid4()) == []


async def test_deleted_person_is_gone_from_the_database(
    engine: AsyncEngine, api: httpx.AsyncClient
) -> None:
    person = await make_person(api, "Markus Brandt", member_no="4711")

    await api.delete(f"{API}/persons/{person['id']}")

    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM person")) == 0


# --- Berechtigungen ----------------------------------------------------------


async def test_every_endpoint_asks_for_its_permission(api: httpx.AsyncClient, app: FastAPI) -> None:
    club = await make_club(api, "SV Brandenburg")
    other = await make_club(api, "Adler Nord")
    person = await make_person(api, "Markus Brandt")
    asked: list[str] = []

    async def recording(request: Request, permission: str) -> security.Actor:
        asked.append(permission)
        return security.Actor()

    calls: list[tuple[str, str, dict[str, Any], str]] = [
        ("GET", "/clubs", {}, "person.read"),
        ("POST", "/clubs", {"json": {"name": "Neu"}}, "club.edit"),
        ("GET", f"/clubs/{club['id']}", {}, "person.read"),
        ("PATCH", f"/clubs/{club['id']}", {"json": {"short": "SVB"}}, "club.edit"),
        ("POST", f"/clubs/{club['id']}/merge", {"json": {"into_id": other["id"]}}, "club.edit"),
        ("DELETE", f"/clubs/{other['id']}", {}, "club.edit"),
        ("GET", "/persons", {}, "person.read"),
        ("POST", "/persons", {"json": {"name": "Anna Bergmann"}}, "person.edit"),
        ("POST", "/persons/check", {"json": {"name": "Anna Bergmann"}}, "person.read"),
        ("GET", "/persons/export.csv", {}, "person.export"),
        ("POST", "/persons/import", {"content": b"name\nX\n"}, "person.edit"),
        ("GET", f"/persons/{person['id']}", {}, "person.read"),
        ("PATCH", f"/persons/{person['id']}", {"json": {"show_club": False}}, "person.edit"),
        ("DELETE", f"/persons/{person['id']}", {}, "person.delete"),
    ]
    security.set_permission_checker(recording)
    try:
        for method, path, kwargs, permission in calls:
            asked.clear()
            response = await api.request(method, f"{API}{path}", **kwargs)
            assert response.status_code < 500, (method, path)
            assert asked == [permission], (method, path)
    finally:
        security.reset_permission_checker()

    # Jede Route kommt vor, jede Berechtigung steht im Manifest.
    routes = {(m, r.path) for r in manifest.router.routes for m in r.methods}  # type: ignore[attr-defined]
    assert len(routes) == len(calls)
    assert set(manifest.permissions) == {permission for *_, permission in calls}


async def test_denied_permission_stops_the_request(api: httpx.AsyncClient) -> None:
    async def deny_export(request: Request, permission: str) -> security.Actor:
        if permission == "person.export":
            raise HTTPException(status_code=403, detail="Dafür fehlt die Berechtigung.")
        return security.Actor()

    security.set_permission_checker(deny_export)
    try:
        denied = await api.get(f"{API}/persons/export.csv")
        allowed = await api.get(f"{API}/persons")
    finally:
        security.reset_permission_checker()

    assert denied.status_code == 403
    assert allowed.status_code == 200


# --- Datenschutz: Ereignisse und Logs ----------------------------------------


async def test_events_and_logs_contain_no_names(
    api: httpx.AsyncClient,
    recorder: EventRecorder,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    secrets = ("Köhler", "Koehler", "Jürgen", "Brandt", "Markus", "4711", "0815")

    club = await make_club(api, "SV Brandenburg")
    other = await make_club(api, "Adler Nord")
    person = await make_person(api, "Jürgen Köhler", member_no="4711", club_id=club["id"])
    await api.post(f"{API}/persons", json={"name": "Jürgen Köhler", "club_id": club["id"]})
    await api.patch(f"{API}/persons/{person['id']}", json={"name": "Jürgen Koehler"})
    await search(api, "köhler")
    await import_csv(api, csv_body("Name;Verein;Mitgliedsnummer\nMarkus Brandt;Adler Nord;0815\n"))
    await import_csv(api, csv_body("Name\nMarkus Brandt\n"), dry_run=True)
    await api.get(f"{API}/persons/export.csv")
    await api.post(f"{API}/clubs/{club['id']}/merge", json={"into_id": other["id"]})
    await api.delete(f"{API}/persons/{person['id']}")

    events = [e for e in recorder.drain() if not e.name.startswith("katalog.")]
    assert {e.name for e in events} == {
        "club.created",
        "club.merged",
        "person.created",
        "person.updated",
        "person.imported",
        "person.deleted",
    }
    for event in events:
        encoded = json.dumps(event.data, ensure_ascii=False)
        assert all(secret not in encoded for secret in secrets), event
        # Nur IDs: jeder Wert ist eine UUID oder eine Liste von UUIDs.
        for value in event.data.values():
            for item in value if isinstance(value, list) else [value]:
                uuid.UUID(item)

    # Protokolle der Anwendung (der Test-Client protokolliert seine eigenen URLs, das ist nicht
    # der Server).
    app_logs = [r for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))]
    assert any(r.name == "schiesshub.teilnehmer" for r in app_logs)
    text_of_logs = "\n".join(r.getMessage() for r in app_logs)
    assert all(secret not in text_of_logs for secret in secrets)
