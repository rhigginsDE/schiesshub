"""Zusammenspiel mit dem Modul `starts`: Abbruch über beide Endpunkte, Lösch- und Stornoschutz,
nachträgliche Erfassung in Rangliste und Übersicht."""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.ergebnisse import journal
from app.modules.ergebnisse.service import abort_from_starts
from app.modules.starts import hooks
from tests.ergebnisse.conftest import Api, Setup, make_setup, precision_definition, shots


async def person_start(api: Api, setup: Setup) -> tuple[str, str]:
    eid = await api.entry(setup.tid, setup.class_id)
    return eid, (await api.starts(setup.tid, eid, setup.cid))[0]


def journal_types(api: Api) -> list[str]:
    records = []
    for path in sorted((api.data_dir / "backups" / "journal").glob("*.ndjson")):
        for line in path.read_text("utf-8").splitlines():
            records.append(json.loads(line)["record"])
    return [r["type"] for r in records if r.get("kind") == journal.RECORD_KIND]


async def test_both_abort_endpoints_write_the_same_event(api: Api, precision: Setup) -> None:
    assert hooks.abort_handler() is abort_from_starts
    tid = precision.tid
    _, via_starts = await person_start(api, precision)
    _, via_results = await person_start(api, precision)

    start = await api.ok(
        "POST", f"/tournaments/{tid}/starts/{via_starts}/abort", json={"abort_reason": "dns"}
    )
    # Die Antwort bleibt der Start (Form des Moduls `starts`).
    assert (start["id"], start["status"], start["abort_reason"]) == (via_starts, "aborted", "dns")
    names = [event.name for event in api.drain()]
    assert "start.status_changed" in names
    assert "result.aborted" in names

    state = await api.ok(
        "POST", f"{api.start_path(tid, via_results)}/result/abort", json={"abort_reason": "dns"}
    )
    assert (state["status"], state["abort_reason"], state["seq"]) == ("aborted", "dns", 1)

    for sid in (via_starts, via_results):
        events = await api.ok("GET", f"{api.start_path(tid, sid)}/events")
        assert [(e["seq"], e["type"], e["abort_reason"]) for e in events] == [(1, "aborted", "dns")]
    assert journal_types(api).count("aborted") == 2

    # Ein zweiter Abbruch scheitert über beide Wege gleich.
    for path in (
        f"/tournaments/{tid}/starts/{via_starts}/abort",
        f"{api.start_path(tid, via_starts)}/result/abort",
    ):
        body = await api.fail("POST", path, 409, json={"abort_reason": "dsq"})
        assert (
            body["detail"] == "Ein Start im Status „abgebrochen“ kann nicht „abgebrochen“ werden."
        )


async def test_abort_via_starts_keeps_raw(api: Api, precision: Setup) -> None:
    tid = precision.tid
    _, sid = await person_start(api, precision)
    await api.shoot(tid, sid, shots([10] * 5), final=False)
    await api.ok("POST", f"/tournaments/{tid}/starts/{sid}/abort", json={"abort_reason": "dnf"})
    state = await api.ok("GET", f"{api.start_path(tid, sid)}/form")
    assert state["current"]["raw"] == shots([10] * 5)
    assert (state["current"]["status"], state["current"]["seq"]) == ("aborted", 2)


async def test_entry_with_dns_event_cannot_be_deleted(api: Api, precision: Setup) -> None:
    tid = precision.tid
    eid, sid = await person_start(api, precision)
    await api.ok("POST", f"{api.start_path(tid, sid)}/result/abort", json={"abort_reason": "dns"})

    body = await api.fail("DELETE", f"/tournaments/{tid}/entries/{eid}", 409)
    assert "Ergebnisprotokoll" in body["detail"]
    # Die Anmeldung steht noch da, das Protokoll auch.
    await api.ok("GET", f"/tournaments/{tid}/entries/{eid}")
    assert len(await api.ok("GET", f"{api.start_path(tid, sid)}/events")) == 1

    # Ohne Ereignisse geht das Löschen weiter.
    other_eid, _ = await person_start(api, precision)
    await api.ok("DELETE", f"/tournaments/{tid}/entries/{other_eid}", 204)


async def test_registered_start_with_events_cannot_be_cancelled(
    api: Api, precision: Setup, engine: AsyncEngine
) -> None:
    tid = precision.tid
    _, sid = await person_start(api, precision)
    await api.put_raw(tid, sid, shots([9] * 5), 0)
    # Zustand wie nach einer Reparatur von Hand: angemeldet, aber mit Protokoll.
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE start SET status = 'registered' WHERE id = :id"), {"id": sid}
        )
    body = await api.fail("DELETE", f"/tournaments/{tid}/starts/{sid}", 409)
    assert "Ergebnisprotokoll" in body["detail"]


async def test_live_ranking_and_summary_count_registered_with_result(
    api: Api, engine: AsyncEngine
) -> None:
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    tid, cid = setup.tid, setup.cid
    _, final = await person_start(api, setup)
    _, called = await person_start(api, setup)
    _, early = await person_start(api, setup)
    _, waiting = await person_start(api, setup)
    _, dns = await person_start(api, setup)
    await api.shoot(tid, final, shots([10] * 5, [9] * 5))
    await api.shoot(tid, called, shots([10] * 5), final=False)
    # Nachträglich erfasst ohne Aufruf, danach (etwa von Hand) wieder „angemeldet“.
    await api.put_raw(tid, early, shots([9] * 5, [9] * 5), 0)
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE start SET status = 'registered' WHERE id = :id"), {"id": early}
        )
    await api.ok("POST", f"/tournaments/{tid}/starts/{dns}/abort", json={"abort_reason": "dns"})

    live = (await api.ranking(tid, cid, scope="live"))["groups"][0]["rows"]
    by_id: dict[str, Any] = {row["start_id"]: row for row in live}
    assert by_id[early]["status"] == "running"
    assert by_id[early]["score"] == "90"
    assert by_id[called]["status"] == "running"
    assert waiting not in by_id
    final_rows = (await api.ranking(tid, cid))["groups"][0]["rows"]
    assert early not in {row["start_id"] for row in final_rows}

    (item,) = (await api.ok("GET", f"/tournaments/{tid}/ranking-summary"))["competitions"]
    assert item["counts"] == {
        "registered": 2,
        "called": 0,
        "captured": 1,
        "final": 1,
        "aborted": 1,
    }
    assert (
        item["starts_total"],
        item["starts_final"],
        item["starts_running"],
        item["starts_waiting"],
    ) == (5, 1, 2, 1)
