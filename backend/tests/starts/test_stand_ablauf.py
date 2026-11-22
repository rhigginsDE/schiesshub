"""Ablauf am Stand (QA-Durchlauf 2): eigenes Recht zum Abbrechen, „Nächsten auf Bahn N“ wie
„Nächste aufrufen“, Zeitplan und Reihenfolge auf demselben Stand, Fortschritt über Abschnitte."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException, Request

from app.core.security import Actor, reset_permission_checker, set_permission_checker
from tests.starts.conftest import Api, Setup


@pytest.fixture
def grant() -> Iterator:
    def install(*allowed: str) -> None:
        async def checker(request: Request, permission: str) -> Actor:
            if permission not in allowed:
                raise HTTPException(403, f"Dafür fehlt die Berechtigung „{permission}“.")
            return Actor(permissions=frozenset(allowed))

        set_permission_checker(checker)

    yield install
    reset_permission_checker()


async def _start(api: Api, setup: Setup, cid: str | None = None, **booking: Any) -> dict:
    entry = await api.entry(setup.tid, setup.class_id)
    return (await api.book(setup.tid, entry["id"], cid or setup.competition_id, **booking))[0]


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


# --- Recht „start.abort“ -----------------------------------------------------


async def test_abort_needs_its_own_permission(api: Api, queue_setup: Setup, grant) -> None:
    start = await _start(api, queue_setup)
    path = f"/tournaments/{queue_setup.tid}/starts/{start['id']}"
    grant("start.read", "start.call")
    await api.ok("POST", f"{path}/call", json={})
    detail = await api.fail("POST", f"{path}/abort", 403, json={"abort_reason": "dsq"})
    assert "start.abort" in detail
    grant("start.read", "start.abort")
    aborted = await api.ok("POST", f"{path}/abort", json={"abort_reason": "dsq"})
    assert (aborted["status"], aborted["abort_reason"]) == ("aborted", "dsq")


def test_manifest_declares_start_abort() -> None:
    from app.modules.starts import manifest

    assert "start.abort" in manifest.permissions
    assert "start.call" in manifest.permissions


# --- „Nächsten auf Bahn N“ ---------------------------------------------------


async def test_call_next_on_one_lane_skips_person_on_another_range(
    api: Api, queue_setup: Setup
) -> None:
    setup = queue_setup
    other_range = await api.range(setup.tid, lanes=2, name="15-m-Stand")
    other = await api.competition(setup.tid, other_range, "Kurzwaffe", planning="queue")
    ilse = await api.entry(setup.tid, setup.class_id)
    elsewhere = (await api.book(setup.tid, ilse["id"], other["id"]))[0]
    await api.ok(
        "POST", f"/tournaments/{setup.tid}/starts/{elsewhere['id']}/call", json={"lane": 2}
    )
    ilse_here = (await api.book(setup.tid, ilse["id"], setup.competition_id))[0]
    jana = await _start(api, setup)
    call_next = f"/tournaments/{setup.tid}/ranges/{setup.range_id}/call-next"

    result = await api.ok("POST", call_next, json={"lane": 2})
    assert [(item["id"], item["lane"]) for item in result["called"]] == [(jana["id"], 2)]
    assert result["skipped"] == [
        {
            "start_id": ilse_here["id"],
            "entry_id": ilse["id"],
            "start_number": ilse["start_number"],
            "competition_id": setup.competition_id,
            "queue_position": 1,
            "reason": "on_lane",
        }
    ]
    assert result["held_lanes"] == []
    assert result["message"] == (
        f"Startnummer {ilse['start_number']} steht gerade auf einer Bahn und wurde übersprungen."
    )
    # Bahn 1 blieb frei, Ilse behält ihren Platz.
    queue = await api.ok("GET", f"/tournaments/{setup.tid}/ranges/{setup.range_id}/queue")
    assert [lane["start"] is None for lane in queue["lanes"]] == [True, False]
    assert [item["start_id"] for item in queue["waiting"]] == [ilse_here["id"]]

    response = await api.client.post(f"/api/v1{call_next}", json={"lane": 2})
    assert response.status_code == 409
    assert response.json()["errors"] == [{"field": "lane", "message": "Bahn 2 ist schon belegt."}]
    detail = await api.fail("POST", call_next, 422, json={"lane": 3})
    assert detail == "Der Stand hat nur 2 Bahnen."
    # Nur Ilse wartet, sie steht noch drüben: niemand wird aufgerufen.
    result = await api.ok("POST", call_next, json={"lane": 1})
    assert result["called"] == []
    assert [item["start_id"] for item in result["skipped"]] == [ilse_here["id"]]


async def test_call_next_without_body_keeps_working(api: Api, queue_setup: Setup) -> None:
    first = await _start(api, queue_setup)
    result = await api.ok(
        "POST", f"/tournaments/{queue_setup.tid}/ranges/{queue_setup.range_id}/call-next"
    )
    assert [item["id"] for item in result["called"]] == [first["id"]]
    assert (result["skipped"], result["held_lanes"], result["message"]) == ([], [], None)
    assert result["upcoming_heat"] is None


# --- Zeitplan und Reihenfolge auf demselben Stand ----------------------------


@pytest.fixture
async def mixed(api: Api) -> dict[str, Any]:
    """Stand mit 3 Bahnen: Präzision nach Zeitplan, Fallscheibe nach Reihenfolge."""
    tid = await api.tournament()
    range_id = await api.range(tid, lanes=3, name="25-m-Stand")
    class_id = await api.klass(tid)
    precision = await api.competition(
        tid, range_id, "Präzision", planning="schedule", heat_minutes=25
    )
    falling = await api.competition(tid, range_id, "Fallscheibe", planning="queue")
    return {
        "setup": Setup(tid, range_id, class_id, falling["id"]),
        "precision": precision["id"],
    }


async def _heat(api: Api, setup: Setup, starts_at: datetime) -> dict[str, Any]:
    return await api.ok(
        "POST",
        f"/tournaments/{setup.tid}/ranges/{setup.range_id}/heats",
        201,
        json={"starts_at": _iso(starts_at), "ends_at": _iso(starts_at + timedelta(minutes=25))},
    )


async def test_imminent_heat_holds_its_lanes(api: Api, mixed: dict[str, Any]) -> None:
    setup: Setup = mixed["setup"]
    begin = (datetime.now(UTC) + timedelta(minutes=5)).replace(microsecond=0)
    heat = await _heat(api, setup, begin)
    karl = await _start(api, setup, mixed["precision"], heat_id=heat["id"], lane=3)
    waiting = [await _start(api, setup) for _ in range(3)]
    base = f"/tournaments/{setup.tid}"
    clock = begin.astimezone(ZoneInfo("Europe/Berlin")).strftime("%H:%M")

    queue = await api.ok("GET", f"{base}/ranges/{setup.range_id}/queue")
    expected = {
        "heat_id": heat["id"],
        "number": 1,
        "starts_at": _iso(begin),
        "ends_at": _iso(begin + timedelta(minutes=25)),
        "lanes": [3],
        "reserve_minutes": 10,
        "reserved_from": _iso(begin - timedelta(minutes=10)),
        "active": True,
    }
    assert queue["upcoming_heat"] == expected
    assert (await api.ok("GET", f"{base}/ranges/{setup.range_id}/now"))["upcoming_heat"] == expected

    # „Nächste aufrufen“ füllt nur die Bahnen, die der Durchgang nicht braucht.
    result = await api.ok("POST", f"{base}/ranges/{setup.range_id}/call-next")
    assert [(item["id"], item["lane"]) for item in result["called"]] == [
        (waiting[0]["id"], 1),
        (waiting[1]["id"], 2),
    ]
    assert result["held_lanes"] == [3]
    assert result["message"] == f"Bahn 3 bleibt für Durchgang 1 ({clock} Uhr) frei."
    assert result["upcoming_heat"]["lanes"] == [3]

    # Nur noch Bahn 3 frei: ohne Bestätigung 409 mit Code, Uhrzeit und Bahn im Text.
    for path, body in (
        (f"{base}/ranges/{setup.range_id}/call-next", {}),
        (f"{base}/ranges/{setup.range_id}/call-next", {"lane": 3}),
        (f"{base}/starts/{waiting[2]['id']}/call", {}),
        (f"{base}/starts/{waiting[2]['id']}/call", {"lane": 3}),
    ):
        response = await api.client.post(f"/api/v1{path}", json=body)
        assert response.status_code == 409, (path, body)
        assert response.json() == {
            "detail": (
                f"Durchgang 1 beginnt um {clock} Uhr und braucht Bahn 3. Soll trotzdem aus der "
                "Reihenfolge aufgerufen werden, bitte bestätigen."
            ),
            "code": "heat_imminent",
        }

    called = await api.ok(
        "POST", f"{base}/starts/{waiting[2]['id']}/call", json={"confirm_heat_conflict": True}
    )
    assert called["lane"] == 3
    # Der Durchgang selbst ruft wie gewohnt; die Bahn ist jetzt belegt.
    detail = await api.fail("POST", f"{base}/ranges/{setup.range_id}/heats/{heat['id']}/call", 409)
    assert detail.startswith("Bahn 3 ist noch belegt.")
    assert karl["lane"] == 3


async def test_confirmed_call_next_fills_held_lanes(api: Api, mixed: dict[str, Any]) -> None:
    setup: Setup = mixed["setup"]
    heat = await _heat(api, setup, datetime.now(UTC) - timedelta(minutes=2))
    await _start(api, setup, mixed["precision"], heat_id=heat["id"], lane=1)
    first = await _start(api, setup)
    path = f"/tournaments/{setup.tid}/ranges/{setup.range_id}/call-next"
    # Begonnen, aber noch nicht aufgerufen: hält Bahn 1 weiter frei.
    result = await api.ok("POST", path)
    assert [(item["id"], item["lane"]) for item in result["called"]] == [(first["id"], 2)]
    assert result["held_lanes"] == []
    second = await _start(api, setup)
    third = await _start(api, setup)
    result = await api.ok("POST", path)
    assert [item["id"] for item in result["called"]] == [second["id"]]
    assert result["held_lanes"] == [1]
    assert "hat um" not in (result["message"] or "")
    detail = (await api.client.post(f"/api/v1{path}", json={})).json()["detail"]
    assert "hat um" in detail
    assert "begonnen und braucht Bahn 1" in detail
    result = await api.ok("POST", path, json={"confirm_heat_conflict": True})
    assert [(item["id"], item["lane"]) for item in result["called"]] == [(third["id"], 1)]


async def test_reserve_off_or_heat_far_away(api: Api, mixed: dict[str, Any]) -> None:
    setup: Setup = mixed["setup"]
    later = (datetime.now(UTC) + timedelta(minutes=45)).replace(microsecond=0)
    heat = await _heat(api, setup, later)
    await _start(api, setup, mixed["precision"], heat_id=heat["id"], lane=1)
    waiting = [await _start(api, setup) for _ in range(2)]
    base = f"/tournaments/{setup.tid}"

    queue = await api.ok("GET", f"{base}/ranges/{setup.range_id}/queue")
    assert queue["upcoming_heat"]["active"] is False
    assert queue["upcoming_heat"]["lanes"] == [1]
    # Frist auf 45 Minuten: jetzt hält der Durchgang Bahn 1 frei.
    await api.ok("PATCH", f"{base}", json={"settings": {"heat_reserve_minutes": 45}})
    queue = await api.ok("GET", f"{base}/ranges/{setup.range_id}/queue")
    assert queue["upcoming_heat"]["active"] is True
    # 0 = aus: alles darf belegt werden.
    await api.ok("PATCH", f"{base}", json={"settings": {"heat_reserve_minutes": 0}})
    queue = await api.ok("GET", f"{base}/ranges/{setup.range_id}/queue")
    assert (queue["upcoming_heat"]["active"], queue["upcoming_heat"]["reserved_from"]) == (
        False,
        None,
    )
    result = await api.ok("POST", f"{base}/ranges/{setup.range_id}/call-next")
    assert [(item["id"], item["lane"]) for item in result["called"]] == [
        (waiting[0]["id"], 1),
        (waiting[1]["id"], 2),
    ]


# --- Fortschritt über mehrere Abschnitte -------------------------------------

TWO_SECTIONS: dict[str, Any] = {
    "variant": {
        "id": "zwei",
        "name": "Zwei Abschnitte",
        "abschnitte": [
            {"id": "fertigkeit", "name": "Fertigkeit", "serien": 4, "schuss_je_serie": 5},
            {"id": "parcours", "name": "Parcours", "serien": 4, "schuss_je_serie": 5},
        ],
    },
    "scoring": {"modell": "ringe", "rangfolge": "absteigend", "geprueft": False},
}


async def test_progress_counts_all_sections(api: Api, queue_setup: Setup) -> None:
    setup = queue_setup
    competition = await api.competition(
        setup.tid, setup.range_id, "Mehrdistanz", planning="queue", definition=TWO_SECTIONS
    )
    start = await _start(api, setup, competition["id"])
    base = f"/tournaments/{setup.tid}"
    await api.ok("POST", f"{base}/starts/{start['id']}/call", json={})
    raw = {
        "sections": {
            "fertigkeit": {"series": [{"sum": 45}, {"sum": 44}, {"sum": 42}, {"sum": 40}]},
            "parcours": {"series": [{"sum": 46}]},
        }
    }
    await api.ok("PUT", f"{base}/starts/{start['id']}/raw", json={"raw": raw, "base_seq": 0})
    queue = await api.ok("GET", f"{base}/ranges/{setup.range_id}/queue")
    progress = next(lane["progress"] for lane in queue["lanes"] if lane["start"])
    assert progress == {
        "section_id": "parcours",
        "series_done": 1,
        "series_total": 4,
        "complete": False,
        "section_number": 2,
        "section_count": 2,
        "series_done_overall": 5,
        "series_total_overall": 8,
    }


async def test_station_views_name_the_discipline_code(api: Api, queue_setup: Setup) -> None:
    await _start(api, queue_setup)
    base = f"/tournaments/{queue_setup.tid}"
    rows = await api.ok("GET", f"{base}/startlist")
    queue = await api.ok("GET", f"{base}/ranges/{queue_setup.range_id}/queue")
    # Eigener Wettbewerb ohne Katalog: Feld vorhanden, leer.
    assert rows[0]["competition_code"] is None
    assert queue["waiting"][0]["competition_code"] is None
