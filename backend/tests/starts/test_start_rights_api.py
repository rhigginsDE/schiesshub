"""Startrecht in der Anmeldung: Vorab-Auskunft, Buchen mit Warnung, Ausgabe der Anmeldung.

Mit dem echten Katalog (DSB mit Startrecht-Tabelle, BDS ohne). Gebucht wird immer.
"""

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from app.core import crypto
from app.core.config import Settings
from app.main import create_app
from tests.conftest import REAL_CATALOG_DIR, running
from tests.starts.conftest import Api

STAND = "DM 2025–2028 (Sportschießen), DM 2026–2028 (Bogen)"
PREFIX = f"Laut DM-Tabelle des DSB (Stand: {STAND})"


@pytest.fixture
async def api(
    clean_db: None, settings_for: Callable[[Path], Settings], tmp_path: Path
) -> AsyncIterator[Api]:
    settings = settings_for(REAL_CATALOG_DIR).model_copy(update={"data_dir": tmp_path / "data"})
    app = create_app(settings)
    async with running(app) as client:
        queue = app.state.events.subscribe()
        yield Api(client=client, app=app, events=queue)
        app.state.events.unsubscribe(queue)
    crypto.set_field_cipher(None)


async def _classes(api: Api, tid: str, federation: str) -> dict[str, str]:
    created = await api.ok(
        "POST", f"/tournaments/{tid}/classes/import", 201, json={"federation": federation}
    )
    return {item["code"]: item["id"] for item in created}


async def _catalog_competition(api: Api, tid: str, federation: str, code: str) -> dict[str, Any]:
    body = {"catalog_federation": federation, "catalog_code": code, "planning": "queue"}
    return await api.ok("POST", f"/tournaments/{tid}/competitions", 201, json=body)


async def _check(api: Api, tid: str, **params: Any) -> list[dict[str, Any]]:
    return await api.ok("GET", f"/tournaments/{tid}/start-rights", params=params)


async def test_precheck_and_booking_in_dsb_competitions(api: Api) -> None:
    tid = await api.tournament()
    classes = await _classes(api, tid, "dsb")
    zimmerstutzen = await _catalog_competition(api, tid, "dsb", "1.30")
    luftgewehr = await _catalog_competition(api, tid, "dsb", "1.10")
    own = await api.competition(tid, None, "Vereinsscheibe")

    # Vorab: Schüler männlich in Zimmerstutzen hat laut Tabelle kein Startrecht.
    checks = await _check(
        api,
        tid,
        class_id=classes["schueler-m"],
        competition_id=[zimmerstutzen["id"], luftgewehr["id"], own["id"]],
    )
    assert [(c["competition_code"], c["status"]) for c in checks] == [
        ("1.30", "kein_startrecht"),
        ("1.10", "startberechtigt"),
        (None, "keine_angabe"),
    ]
    assert checks[0]["start_rights"] == [
        {
            "code": "kein_startrecht",
            "severity": "warning",
            "message_de": (
                f"{PREFIX} hat Klasse Schüler männlich (20) in Zimmerstutzen (1.30) kein "
                "Startrecht."
            ),
            "source": (
                f"Startrecht-Tabelle DSB zur Deutschen Meisterschaft, Stand: {STAND}; "
                "Eintrag 1.30 „Zimmerstutzen“"
            ),
        }
    ]
    assert checks[1]["start_rights"] == []
    assert checks[2]["start_rights"] == []

    # Ohne competition_id: alle Wettbewerbe des Turniers.
    every = await _check(api, tid, class_id=classes["schueler-m"])
    assert [c["competition_id"] for c in every] == [
        zimmerstutzen["id"],
        luftgewehr["id"],
        own["id"],
    ]

    # Buchen geht trotzdem; die Antwort trägt die Warnung.
    entry = await api.entry(tid, classes["schueler-m"], await api.person("Kai Probe"))
    booked = await api.book(tid, entry["id"], zimmerstutzen["id"])
    assert booked[0]["status"] == "registered"
    assert booked[0]["start_rights"] == checks[0]["start_rights"]
    other = await api.book(tid, entry["id"], luftgewehr["id"])
    assert other[0]["start_rights"] == []

    # Ausgabe der Anmeldung: je Start dieselben Meldungen.
    detail = await api.ok("GET", f"/tournaments/{tid}/entries/{entry['id']}")
    assert [s["start_rights"] for s in detail["starts"]] == [checks[0]["start_rights"], []]
    listed = await api.ok("GET", f"/tournaments/{tid}/entries")
    assert listed[0]["starts"][0]["start_rights"] == checks[0]["start_rights"]

    # Nachkauf: Vorab-Auskunft über die Anmeldung.
    by_entry = await _check(api, tid, entry_id=entry["id"], competition_id=zimmerstutzen["id"])
    assert by_entry[0]["status"] == "kein_startrecht"


async def test_class_change_updates_the_notices(api: Api) -> None:
    tid = await api.tournament()
    classes = await _classes(api, tid, "dsb")
    zimmerstutzen = await _catalog_competition(api, tid, "dsb", "1.30")
    entry = await api.entry(tid, classes["damen-3"], await api.person("Lea Beispiel"))
    booked = await api.book(tid, entry["id"], zimmerstutzen["id"])
    assert booked[0]["start_rights"] == []

    changed = await api.ok(
        "PATCH",
        f"/tournaments/{tid}/entries/{entry['id']}",
        json={"class_id": classes["damen-4"]},
    )
    assert [(n["code"], n["severity"]) for n in changed["starts"][0]["start_rights"]] == [
        ("startet_bei", "hint")
    ]
    assert changed["starts"][0]["start_rights"][0]["message_de"] == (
        f"{PREFIX} startet Klasse Damen IV (17) in Zimmerstutzen (1.30) bei Klasse Damen III (15)."
    )


async def test_green_cell_is_only_a_hint(api: Api) -> None:
    tid = await api.tournament()
    classes = await _classes(api, tid, "dsb")
    zimmerstutzen = await _catalog_competition(api, tid, "dsb", "1.30")
    checks = await _check(
        api, tid, class_id=classes["junioren-2-m"], competition_id=zimmerstutzen["id"]
    )
    assert checks[0]["status"] == "startmoeglichkeit_0711"
    assert [(n["code"], n["severity"]) for n in checks[0]["start_rights"]] == [
        ("startmoeglichkeit_0711", "hint")
    ]


async def test_bds_has_no_table_and_no_warning(api: Api) -> None:
    tid = await api.tournament()
    classes = await _classes(api, tid, "bds")
    competition = await _catalog_competition(api, tid, "bds", "4401")
    class_id = next(iter(classes.values()))
    checks = await _check(api, tid, class_id=class_id)
    assert [(c["status"], c["start_rights"]) for c in checks] == [("keine_angabe", [])]

    entry = await api.entry(tid, class_id, await api.person("Mia Platzhalter"))
    booked = await api.book(tid, entry["id"], competition["id"])
    assert booked[0]["start_rights"] == []


async def test_stations_do_not_get_start_rights(api: Api) -> None:
    tid = await api.tournament()
    range_id = await api.range(tid)
    classes = await _classes(api, tid, "dsb")
    body = {"catalog_federation": "dsb", "catalog_code": "1.30", "range_id": range_id}
    body["planning"] = "queue"
    competition = await api.ok("POST", f"/tournaments/{tid}/competitions", 201, json=body)
    entry = await api.entry(tid, classes["schueler-m"], await api.person("Tom Muster"))
    booked = await api.book(tid, entry["id"], competition["id"])
    assert booked[0]["start_rights"]

    startlist = await api.ok("GET", f"/tournaments/{tid}/startlist")
    queue = await api.ok("GET", f"/tournaments/{tid}/ranges/{range_id}/queue")
    called = await api.ok("POST", f"/tournaments/{tid}/starts/{booked[0]['id']}/call")
    for item in [*startlist, *queue["waiting"], called]:
        assert "start_rights" not in item


async def test_precheck_input_errors(api: Api) -> None:
    tid = await api.tournament()
    classes = await _classes(api, tid, "dsb")
    other = await api.tournament()
    foreign = await _catalog_competition(api, other, "dsb", "1.10")
    path = f"/tournaments/{tid}/start-rights"
    response = await api.client.get(f"/api/v1{path}")
    assert response.status_code == 422
    response = await api.client.get(
        f"/api/v1{path}",
        params={"class_id": classes["herren-1"], "competition_id": foreign["id"]},
    )
    assert response.status_code == 422
    assert "gehört nicht zu diesem Turnier" in response.text
