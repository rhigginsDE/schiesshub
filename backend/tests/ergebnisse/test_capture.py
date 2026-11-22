"""Erfassen, Abschließen, Korrigieren, Wiederöffnen, Abbrechen; Konflikte und Wiederholungen."""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import Actor, reset_permission_checker, set_permission_checker
from app.modules.ergebnisse import journal
from tests.ergebnisse.conftest import (
    Api,
    Setup,
    falls,
    make_setup,
    new_id,
    precision_definition,
    shots,
)

FALL_RAW = falls(
    {"time_cs": 1284, "standing": 1},
    {"status": "time_limit", "standing": 2},
    {"status": "aborted_by_shooter", "standing": 0, "time_cs": 3000},
    {"time_cs": 990, "standing": 0},
)


async def one_start(api: Api, setup: Setup, **person: Any) -> str:
    eid = await api.entry(setup.tid, setup.class_id, **person)
    return (await api.starts(setup.tid, eid, setup.cid))[0]


async def start_status(api: Api, setup: Setup, sid: str) -> str:
    rows = await api.ok("GET", f"/tournaments/{setup.tid}/startlist")
    return next(row["status"] for row in rows if row["start_id"] == sid)


# --- Fallscheibe 4401: kompletter Weg -------------------------------------------------


async def test_fallscheibe_full_path(api: Api, fallscheibe: Setup) -> None:
    setup = fallscheibe
    sid = await one_start(api, setup)
    path = api.start_path(setup.tid, sid)
    await api.call(setup.tid, sid)

    form = await api.ok("GET", f"{path}/form")
    assert form["header"]["start_number"] == 1
    assert form["header"]["attempt"] == 1
    assert form["header"]["attempts_booked"] == 1
    assert form["header"]["lane"] == 1
    assert form["form"]["model"] == "zeit_plus_zuschlaege"
    statuses = [o["key"] for o in form["form"]["sections"][0]["series"][0]["fields"][0]["options"]]
    assert "time_limit" in statuses
    assert "aborted_by_shooter" in statuses
    assert form["current"]["seq"] == 0
    assert form["current"]["raw"] == {}
    assert form["current"]["computed"]["complete"] is False

    # Zwischenstand nach zwei Serien
    partial = falls(FALL_RAW["sections"]["fallscheibe"]["series"][0], None)
    api.drain()
    state = await api.put_raw(setup.tid, sid, partial, 0)
    assert state["seq"] == 1
    assert state["status"] == "captured"
    assert state["computed"]["complete"] is False
    assert state["computed"]["steps"][0] == "Serie 1: 12,84 s + 1 stehende Scheibe × 10 s = 22,84 s"
    names = [event.name for event in api.drain()]
    assert names == ["start.status_changed", "result.raw_set"]

    state = await api.put_raw(setup.tid, sid, FALL_RAW, 1)
    assert state["seq"] == 2
    assert state["score"] == "172.74"
    assert state["computed"]["score_text"] == "172,74 s"
    steps = state["computed"]["steps"]
    assert "Zeitlimit erreicht" in steps[1]
    assert "80,00 s" in steps[1]
    assert "gemessene Zeit 30,00 s wird nicht gewertet" in steps[2]

    state = await api.finalize(setup.tid, sid, 2)
    assert state["status"] == "final"
    assert state["is_final"] is True
    assert state["finalized_at"] is not None
    assert state["provisional_until"] is None
    assert state["is_provisional"] is False
    assert await start_status(api, setup, sid) == "final"

    # Nach dem Abschluss keine einfache Erfassung mehr
    detail = await api.fail("PUT", f"{path}/raw", 409, json={"raw": FALL_RAW, "base_seq": 3})
    assert "Korrektur" in detail["detail"]

    events = await api.ok("GET", f"{path}/events")
    assert [e["type"] for e in events] == ["raw_set", "raw_set", "finalized"]
    assert events[0]["changes"][0] == {
        "path": "sections.fallscheibe.series[0].standing",
        "before": None,
        "after": 1,
    }
    second = {c["path"]: c for c in events[1]["changes"]}
    assert second["sections.fallscheibe.series[1].status"]["after"] == "time_limit"
    assert "sections.fallscheibe.series[0].time_cs" not in second
    assert events[2]["type_label"] == "abgeschlossen"
    assert events[2]["raw"] is None


async def test_precision_shot_and_series_sum(api: Api, precision: Setup) -> None:
    setup = precision
    by_shot = await one_start(api, setup)
    by_sum = await one_start(api, setup)

    state = await api.shoot(setup.tid, by_shot, shots([10, 9, "X", 8, 7], [10, 10, 9, 9, 9]))
    assert state["score"] == "91"
    assert state["computed"]["tens"] == 4
    assert state["computed"]["inner_tens"] == 1
    assert state["computed"]["steps"][0] == "Serie 1: 10 + 9 + X + 8 + 7 = 44 Ringe"

    form = await api.ok(
        "GET", f"{api.start_path(setup.tid, by_sum)}/form", params={"capture_mode": "series"}
    )
    assert form["form"]["capture_mode"] == "series"
    assert form["competition_capture_mode"] == "shot"
    keys = [f["key"] for f in form["form"]["sections"][0]["series"][0]["fields"]]
    assert "sum" in keys

    raw = {"sections": {"praezision": {"series": [{"sum": 44, "tens": 2}, {"sum": 47}]}}}
    state = await api.shoot(setup.tid, by_sum, raw)
    assert state["score"] == "91"
    assert state["computed"]["tens"] is None
    assert "Seriensumme 44 Ringe, 2 Zehner" in state["computed"]["steps"][0]

    # Nur die von der Wertung unterstützten Darstellungen
    await api.fail(
        "GET", f"{api.start_path(setup.tid, by_sum)}/form", 422, params={"capture_mode": "x"}
    )


# --- Prüfungen -------------------------------------------------------------------------


async def test_validation_errors_with_paths(api: Api, fallscheibe: Setup) -> None:
    setup = fallscheibe
    sid = await one_start(api, setup)
    await api.call(setup.tid, sid)
    body = await api.fail(
        "PUT",
        f"{api.start_path(setup.tid, sid)}/raw",
        422,
        json={"raw": falls({"time_cs": -5, "standing": 9}), "base_seq": 0},
    )
    assert body["errors"] == [
        {
            "field": "raw.sections.fallscheibe.series[0].time_cs",
            "message": "Serie 1: Zeit: in Hundertstelsekunden als ganze Zahl größer 0",
        },
        {
            "field": "raw.sections.fallscheibe.series[0].standing",
            "message": "Serie 1: höchstens 5 stehende Scheiben",
        },
    ]
    assert body["detail"].startswith("Die Eingabe enthält 2 Fehler")
    events = await api.ok("GET", f"{api.start_path(setup.tid, sid)}/events")
    assert events == []
    # Schemafehler (base_seq fehlt, unbekanntes Feld) bleiben deutsch
    body = await api.fail(
        "PUT", f"{api.start_path(setup.tid, sid)}/raw", 422, json={"raw": {}, "seq": 1}
    )
    assert {e["field"] for e in body["errors"]} == {"base_seq", "seq"}


async def test_finalize_incomplete_is_rejected(api: Api, fallscheibe: Setup) -> None:
    setup = fallscheibe
    sid = await one_start(api, setup)
    state = await api.shoot(setup.tid, sid, falls({"time_cs": 1000, "standing": 1}), final=False)
    body = await api.fail(
        "POST",
        f"{api.start_path(setup.tid, sid)}/finalize",
        422,
        json={"base_seq": state["seq"]},
    )
    assert [e["message"] for e in body["errors"]] == [
        "Serie 2 fehlt",
        "Serie 3 fehlt",
        "Serie 4 fehlt",
    ]
    assert body["errors"][0]["field"] == "raw.sections.fallscheibe.series[1]"
    assert await start_status(api, setup, sid) == "captured"


async def test_not_called_start_is_captured_without_lane(api: Api, fallscheibe: Setup) -> None:
    """Nachträgliche Erfassung ohne Aufrufen: angemeldet → erfasst, die Bahn bleibt leer."""
    setup = fallscheibe
    sid = await one_start(api, setup)
    other = await one_start(api, setup)
    state = await api.put_raw(setup.tid, sid, FALL_RAW, 0)
    assert (state["status"], state["seq"]) == ("captured", 1)
    status_events = [e.data for e in api.drain() if e.name == "start.status_changed"]
    assert [(e["from"], e["to"]) for e in status_events] == [("registered", "captured")]

    entry_rows = await api.ok("GET", f"/tournaments/{setup.tid}/startlist")
    row = next(row for row in entry_rows if row["start_id"] == sid)
    assert row["status"] == "captured"
    assert row["lane"] is None
    # Der Start hat die Reihenfolge verlassen, der andere rückt auf Platz 1.
    queue = await api.ok("GET", f"/tournaments/{setup.tid}/ranges/{setup.range_id}/queue")
    assert [item["start_id"] for item in queue["waiting"]] == [other]
    assert all(lane["start"] is None for lane in queue["lanes"])

    final = await api.finalize(setup.tid, sid, state["seq"])
    assert final["status"] == "final"


async def test_two_terminals_conflict_on_base_seq(api: Api, fallscheibe: Setup) -> None:
    setup = fallscheibe
    sid = await one_start(api, setup)
    await api.call(setup.tid, sid)
    first = falls({"time_cs": 1000, "standing": 0})
    await api.put_raw(setup.tid, sid, first, 0)
    # Terminal B kennt noch Stand 0
    body = await api.fail(
        "PUT",
        f"{api.start_path(setup.tid, sid)}/raw",
        409,
        json={"raw": falls({"time_cs": 2000, "standing": 3}), "base_seq": 0},
    )
    assert "anderes Gerät" in body["detail"]
    assert body["current"]["seq"] == 1
    assert body["current"]["raw"] == first
    events = await api.ok("GET", f"{api.start_path(setup.tid, sid)}/events")
    assert len(events) == 1


async def test_concurrent_writes_one_wins(api: Api, fallscheibe: Setup) -> None:
    setup = fallscheibe
    sid = await one_start(api, setup)
    await api.call(setup.tid, sid)
    url = f"/api/v1{api.start_path(setup.tid, sid)}/raw"
    responses = await asyncio.gather(
        *(
            api.client.put(
                url, json={"raw": falls({"time_cs": 1000 + i, "standing": 0}), "base_seq": 0}
            )
            for i in range(4)
        )
    )
    assert sorted(r.status_code for r in responses) == [200, 409, 409, 409]


async def test_idempotency_key_replays_without_second_event(api: Api, fallscheibe: Setup) -> None:
    setup = fallscheibe
    sid = await one_start(api, setup)
    await api.call(setup.tid, sid)
    headers = {"Idempotency-Key": "terminal-7-0001"}
    first = await api.put_raw(setup.tid, sid, FALL_RAW, 0, headers=headers)
    api.drain()
    again = await api.put_raw(setup.tid, sid, FALL_RAW, 0, headers=headers)
    assert again == first
    assert api.drain() == []
    assert len(await api.ok("GET", f"{api.start_path(setup.tid, sid)}/events")) == 1

    # Derselbe Schlüssel mit anderem Inhalt ist ein Fehler
    body = await api.fail(
        "PUT",
        f"{api.start_path(setup.tid, sid)}/raw",
        422,
        json={"raw": falls({"time_cs": 1, "standing": 0}), "base_seq": 0},
        headers=headers,
    )
    assert "Idempotency-Key" in body["detail"]
    # Abschließen mit eigenem Schlüssel, ebenfalls wiederholbar
    final_headers = {"Idempotency-Key": "terminal-7-0002"}
    done = await api.ok(
        "POST",
        f"{api.start_path(setup.tid, sid)}/finalize",
        json={"base_seq": 1},
        headers=final_headers,
    )
    repeated = await api.ok(
        "POST",
        f"{api.start_path(setup.tid, sid)}/finalize",
        json={"base_seq": 1},
        headers=final_headers,
    )
    assert repeated == done
    assert done["seq"] == 2


# --- Korrektur, Wiederöffnen, Abbruch ---------------------------------------------------


async def test_correct_needs_reason_and_stays_final(api: Api, precision: Setup) -> None:
    setup = precision
    sid = await one_start(api, setup)
    path = api.start_path(setup.tid, sid)
    state = await api.shoot(setup.tid, sid, shots([10] * 5, [9] * 5))
    assert state["score"] == "95"
    fixed = shots([10] * 5, [9, 9, 9, 9, 8])

    body = await api.fail("POST", f"{path}/correct", 422, json={"raw": fixed, "base_seq": 2})
    assert body["errors"][0]["field"] == "reason"
    body = await api.fail(
        "POST", f"{path}/correct", 422, json={"raw": fixed, "reason": "   ", "base_seq": 2}
    )
    assert body["errors"][0]["field"] == "reason"
    # Unvollständige Korrektur ist kein abgeschlossenes Ergebnis
    await api.fail(
        "POST",
        f"{path}/correct",
        422,
        json={"raw": shots([10] * 5), "reason": "Zählfehler", "base_seq": 2},
    )

    state = await api.ok(
        "POST",
        f"{path}/correct",
        json={"raw": fixed, "reason": "Zählfehler Serie 2", "base_seq": 2},
    )
    assert state["score"] == "94"
    assert state["status"] == "final"
    assert state["seq"] == 3
    events = await api.ok("GET", f"{path}/events")
    assert events[-1]["type"] == "corrected"
    assert events[-1]["reason"] == "Zählfehler Serie 2"
    assert events[-1]["changes"] == [
        {"path": "sections.praezision.series[1].shots", "before": [9] * 5, "after": [9, 9, 9, 9, 8]}
    ]


async def test_reopen_needs_reason(api: Api, precision: Setup) -> None:
    setup = precision
    sid = await one_start(api, setup)
    path = api.start_path(setup.tid, sid)
    await api.shoot(setup.tid, sid, shots([10] * 5, [9] * 5))

    body = await api.fail("POST", f"{path}/reopen", 422, json={})
    assert body["errors"][0]["field"] == "reason"
    state = await api.ok("POST", f"{path}/reopen", json={"reason": "Scheibe vertauscht"})
    assert state["status"] == "captured"
    assert state["is_final"] is False
    assert state["finalized_at"] is None
    assert state["seq"] == 3
    # Danach wieder normal erfassbar und abschließbar
    state = await api.put_raw(setup.tid, sid, shots([9] * 5, [9] * 5), 3)
    state = await api.finalize(setup.tid, sid, state["seq"])
    assert state["score"] == "90"
    # Nur ein abgeschlossenes Ergebnis lässt sich wieder öffnen
    await api.ok("POST", f"{path}/reopen", json={"reason": "noch mal"})
    await api.fail("POST", f"{path}/reopen", 409, json={"reason": "doppelt"})


async def test_abort_keeps_raw(api: Api, fallscheibe: Setup) -> None:
    setup = fallscheibe
    sid = await one_start(api, setup)
    path = api.start_path(setup.tid, sid)
    partial = falls({"time_cs": 1000, "standing": 1})
    await api.shoot(setup.tid, sid, partial, final=False)

    state = await api.ok(
        "POST", f"{path}/result/abort", json={"abort_reason": "dnf", "reason": "Waffendefekt"}
    )
    assert state["status"] == "aborted"
    assert state["abort_reason"] == "dnf"
    assert state["raw"] == partial
    assert state["seq"] == 2
    events = await api.ok("GET", f"{path}/events")
    assert events[-1]["abort_reason"] == "dnf"
    assert events[-1]["reason"] == "Waffendefekt"
    # Abgebrochen: weder erfassen noch noch einmal abbrechen
    await api.fail("PUT", f"{path}/raw", 409, json={"raw": partial, "base_seq": 2})
    await api.fail("POST", f"{path}/result/abort", 409, json={"abort_reason": "dsq"})


async def test_abort_from_final_is_refused(api: Api, precision: Setup) -> None:
    sid = await one_start(api, precision)
    await api.shoot(precision.tid, sid, shots([10] * 5, [9] * 5))
    body = await api.fail(
        "POST",
        f"{api.start_path(precision.tid, sid)}/result/abort",
        409,
        json={"abort_reason": "dsq"},
    )
    assert "abgeschlossen" in body["detail"]


async def test_protest_period_sets_provisional_until(api: Api) -> None:
    tid = await api.tournament(protest_minutes=30)
    range_id = await api.range(tid)
    class_id = await api.klass(tid)
    cid = (await api.competition(tid, range_id, definition=precision_definition()))["id"]
    setup = Setup(tid, range_id, class_id, cid)
    sid = await one_start(api, setup)
    state = await api.shoot(tid, sid, shots([10] * 5, [9] * 5))
    finalized = datetime.fromisoformat(state["finalized_at"])
    assert datetime.fromisoformat(state["provisional_until"]) - finalized == timedelta(minutes=30)
    assert state["is_provisional"] is True


async def test_closed_tournament_refuses_capture(api: Api, precision: Setup) -> None:
    sid = await one_start(api, precision)
    await api.call(precision.tid, sid)
    await api.status(precision.tid, "closed")
    body = await api.fail(
        "PUT",
        f"{api.start_path(precision.tid, sid)}/raw",
        409,
        json={"raw": shots([10]), "base_seq": 0},
    )
    assert "abgeschlossen" in body["detail"]


async def test_unknown_start_is_404(api: Api, precision: Setup) -> None:
    other = await api.tournament()
    sid = await one_start(api, precision)
    await api.fail("GET", f"{api.start_path(other, sid)}/form", 404)
    await api.fail("GET", f"{api.start_path(precision.tid, new_id())}/events", 404)


# --- Name in der Maske ----------------------------------------------------------------


async def test_form_shows_full_name_only_with_capture_permission(
    api: Api, precision: Setup
) -> None:
    club = (await api.ok("POST", "/clubs", 201, json={"name": "SV Tell"}))["id"]
    sid = await one_start(
        api,
        precision,
        name="Hans-Peter Müller",
        display_mode="short",
        show_club=False,
        club_id=club,
    )
    path = f"{api.start_path(precision.tid, sid)}/form"
    header = (await api.ok("GET", path))["header"]
    assert header["display_name"] == "Hans-Peter Müller"
    assert header["full_name_shown"] is True
    assert header["club"] == "SV Tell"

    async def no_capture(request: Any, permission: str) -> Actor:
        from fastapi import HTTPException

        if permission == "result.capture":
            raise HTTPException(403, "Dafür fehlt die Berechtigung.")
        return Actor()

    set_permission_checker(no_capture)
    try:
        header = (await api.ok("GET", path))["header"]
    finally:
        reset_permission_checker()
    assert header["display_name"] == "H.-P. Müller"
    assert header["full_name_shown"] is False
    assert header["club"] is None


# --- Unveränderliches Protokoll -----------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    ["UPDATE result_event SET reason = 'geändert'", "DELETE FROM result_event"],
)
async def test_database_refuses_update_and_delete(
    api: Api, precision: Setup, engine: AsyncEngine, statement: str
) -> None:
    sid = await one_start(api, precision)
    await api.shoot(precision.tid, sid, shots([10] * 5, [9] * 5))
    with pytest.raises(DBAPIError, match="result_event ist unveränderlich"):
        async with engine.begin() as connection:
            await connection.execute(text(statement))
    async with engine.connect() as connection:
        count = await connection.scalar(text("SELECT count(*) FROM result_event"))
    assert count == 2


# --- Mitschrift der Sicherung ------------------------------------------------------------


def journal_records(api: Api) -> list[dict[str, Any]]:
    records = []
    for path in sorted((api.data_dir / "backups" / "journal").glob("*.ndjson")):
        for line in path.read_text("utf-8").splitlines():
            records.append(json.loads(line)["record"])
    return [r for r in records if r.get("kind") == journal.RECORD_KIND]


async def test_journal_gets_every_event_without_names(api: Api, fallscheibe: Setup) -> None:
    sid = await one_start(api, fallscheibe, name="Erika Mustermann")
    await api.shoot(fallscheibe.tid, sid, FALL_RAW)
    records = journal_records(api)
    assert [(r["seq"], r["type"]) for r in records] == [(1, "raw_set"), (2, "finalized")]
    first = records[0]
    assert first["start_id"] == sid
    assert first["start_number"] == 1
    assert first["payload"]["raw"] == FALL_RAW
    assert first["tournament_id"] == fallscheibe.tid
    assert "Mustermann" not in json.dumps(records)


async def test_journal_failure_never_breaks_capture(
    api: Api, fallscheibe: Setup, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def broken(record: dict[str, Any]) -> int:
        raise OSError("Platte voll")

    monkeypatch.setattr(journal, "append_journal", broken)
    sid = await one_start(api, fallscheibe)
    state = await api.shoot(fallscheibe.tid, sid, FALL_RAW)
    assert state["status"] == "final"
    assert "nicht in die Mitschrift geschrieben" in caplog.text
    events = await api.ok("GET", f"{api.start_path(fallscheibe.tid, sid)}/events")
    assert len(events) == 2


async def test_raw_set_on_schedule_start_calls_and_captures(api: Api) -> None:
    setup = await make_setup(
        api, definition=precision_definition(), planning="schedule", heat_minutes=20
    )
    heat = await api.ok(
        "POST",
        f"/tournaments/{setup.tid}/ranges/{setup.range_id}/heats",
        201,
        json={"starts_at": "2027-03-06T09:00:00Z", "ends_at": "2027-03-06T09:20:00Z"},
    )
    heat_id = heat["id"]
    eid = await api.entry(setup.tid, setup.class_id)
    sid = (
        await api.ok(
            "POST",
            f"/tournaments/{setup.tid}/entries/{eid}/starts",
            201,
            json={"competition_id": setup.cid, "heat_id": heat_id},
        )
    )[0]["id"]
    api.drain()
    state = await api.put_raw(setup.tid, sid, shots([10, 10]), 0)
    assert state["status"] == "captured"
    changes = [e.data["to"] for e in api.drain() if e.name == "start.status_changed"]
    assert changes == ["called", "captured"]
