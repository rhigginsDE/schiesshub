"""Abbruch zurücknehmen, Korrektur eines abgebrochenen Starts, Vorabauskunft beim Aufgeben,
Gleichstand „entschieden nach“ und Abbruch-Bemerkungen über `starts.hooks`."""

import uuid
from typing import Any

from app.modules import ergebnisse
from app.modules.ergebnisse.service import abort_remarks
from app.modules.starts import hooks
from tests.ergebnisse.conftest import Api, Setup, falls, shots
from tests.ergebnisse.test_starts_hooks import journal_types, person_start


def serie(seconds: int, standing: int = 0) -> dict[str, Any]:
    return {"time_cs": seconds * 100, "standing": standing}


async def audit_of(api: Api) -> list[dict[str, Any]]:
    return (await api.ok("GET", "/audit", params={"limit": 200}))["items"]


async def startlist_row(api: Api, tid: str, sid: str) -> dict[str, Any]:
    rows = await api.ok("GET", f"/tournaments/{tid}/startlist")
    return next(row for row in rows if row["start_id"] == sid)


# --- Abbruch zurücknehmen ------------------------------------------------------------


async def test_undo_abort_with_raw_returns_to_captured(api: Api, precision: Setup) -> None:
    tid = precision.tid
    _, sid = await person_start(api, precision)
    path = api.start_path(tid, sid)
    await api.shoot(tid, sid, shots([10] * 5), final=False)  # seq 1
    await api.ok("POST", f"{path}/result/abort", json={"abort_reason": "dnf", "reason": "Defekt"})
    api.drain()

    state = await api.ok(
        "POST", f"{path}/result/undo-abort", json={"reason": "Versehentlich aufgegeben"}
    )
    assert (state["status"], state["abort_reason"], state["seq"]) == ("captured", None, 3)
    assert state["raw"] == shots([10] * 5)
    assert state["abort_remark"] is None
    names = [(event.name, event.data) for event in api.drain()]
    status = [data for name, data in names if name == "start.status_changed"]
    assert [(d["from"], d["to"]) for d in status] == [("aborted", "captured")]
    assert "result.abort_undone" in [name for name, _ in names]

    events = await api.ok("GET", f"{path}/events")
    assert [e["type"] for e in events] == ["raw_set", "aborted", "abort_undone"]
    undone = events[-1]
    assert undone["type_label"] == "Abbruch zurückgenommen"
    assert undone["reason"] == "Versehentlich aufgegeben"
    assert journal_types(api)[-1] == "abort_undone"

    audit = next(item for item in await audit_of(api) if item["action"] == "start.abort_undone")
    assert audit["details"]["reason"] == "Versehentlich aufgegeben"
    assert (audit["details"]["from"], audit["details"]["abort_reason"]) == ("aborted", "dnf")
    assert audit["action_text"] != "start.abort_undone"

    # Ohne Schützenstand, nicht wieder aufgerufen.
    row = await startlist_row(api, tid, sid)
    assert (row["status"], row["on_lane"]) == ("captured", False)

    # Danach geht alles wie gewohnt: erfassen, abschließen.
    state = await api.put_raw(tid, sid, shots([10] * 5, [9] * 5), state["seq"])
    state = await api.finalize(tid, sid, state["seq"])
    assert (state["status"], state["score"]) == ("final", "95")

    # Neuaufbau aus den Ereignissen ergibt denselben Stand.
    await api.ok("POST", f"/tournaments/{tid}/competitions/{precision.cid}/recompute")
    again = await api.ok("GET", f"{path}/form")
    assert (again["current"]["seq"], again["current"]["is_final"]) == (5, True)


async def test_undo_abort_without_raw_returns_to_registered(api: Api, precision: Setup) -> None:
    tid = precision.tid
    _, sid = await person_start(api, precision)
    _, other = await person_start(api, precision)
    path = api.start_path(tid, sid)
    await api.call(tid, sid)
    await api.ok("POST", f"/tournaments/{tid}/starts/{sid}/abort", json={"abort_reason": "dns"})

    state = await api.ok("POST", f"{path}/result/undo-abort", json={"reason": "Doch angetreten"})
    assert (state["status"], state["abort_reason"]) == ("registered", None)
    row = await startlist_row(api, tid, sid)
    assert (row["status"], row["lane"], row["on_lane"]) == ("registered", None, False)
    # Er reiht sich in die Reihenfolge ein (hinten), aufgerufen wird er nicht.
    queue = await api.ok("GET", f"/tournaments/{tid}/ranges/{precision.range_id}/queue")
    assert [item["start_id"] for item in queue["waiting"]] == [other, sid]

    # Erneut abbrechen geht.
    again = await api.ok("POST", f"{path}/result/abort", json={"abort_reason": "dns"})
    assert (again["status"], again["abort_reason"]) == ("aborted", "dns")


async def test_undo_abort_rules(api: Api, precision: Setup) -> None:
    tid = precision.tid
    _, sid = await person_start(api, precision)
    path = api.start_path(tid, sid)
    body = await api.fail("POST", f"{path}/result/undo-abort", 409, json={"reason": "x"})
    assert body["detail"] == "Zurücknehmen lässt sich nur der Abbruch eines abgebrochenen Starts."
    await api.ok("POST", f"{path}/result/abort", json={"abort_reason": "dsq"})
    await api.fail("POST", f"{path}/result/undo-abort", 422, json={"reason": "  "})
    await api.fail("POST", f"{path}/result/undo-abort", 422, json={})
    await api.fail("POST", f"{path}/result/undo-abort", 422, json={"reason": "x" * 501})
    # Veraltetes base_seq: 409 mit dem aktuellen Stand.
    stale = await api.fail(
        "POST", f"{path}/result/undo-abort", 409, json={"reason": "Irrtum", "base_seq": 0}
    )
    assert stale["current"]["status"] == "aborted"
    # Wiederholung mit demselben Schlüssel: kein zweites Ereignis.
    key = {"Idempotency-Key": "undo-1"}
    first = await api.ok(
        "POST", f"{path}/result/undo-abort", json={"reason": "Irrtum"}, headers=key
    )
    second = await api.ok(
        "POST", f"{path}/result/undo-abort", json={"reason": "Irrtum"}, headers=key
    )
    assert first["seq"] == second["seq"] == 2
    # Die Startroute „zurückstellen“ öffnet einen Abbruch nicht.
    await api.ok("POST", f"{path}/result/abort", json={"abort_reason": "dns"})
    await api.fail("POST", f"/tournaments/{tid}/starts/{sid}/return", 409, json={})


# --- Korrektur eines abgebrochenen Starts ------------------------------------------------


async def test_correct_aborted_start_keeps_it_aborted(api: Api, fallscheibe: Setup) -> None:
    """Serienstatus „Abbruch durch den Schützen“ nachtragen, ohne den Abbruch zurückzunehmen."""
    tid, cid = fallscheibe.tid, fallscheibe.cid
    _, sid = await person_start(api, fallscheibe)
    path = api.start_path(tid, sid)
    await api.shoot(tid, sid, falls(serie(15), serie(15), {"time_cs": 900}), final=False)
    state = await api.ok("POST", f"{path}/result/abort", json={"abort_reason": "dnf"})
    ranking = await api.ranking(tid, cid)
    (row,) = ranking["groups"][0]["rows"]
    assert row["place"] is None
    assert "unvollständig" in row["abort_note"]

    fixed = falls(serie(15), serie(15), {"status": "aborted_by_shooter", "standing": 5})
    state = await api.ok(
        "POST",
        f"{path}/correct",
        json={"raw": fixed, "reason": "Serie 3 abgebrochen", "base_seq": state["seq"]},
    )
    assert (state["status"], state["abort_reason"], state["is_final"]) == ("aborted", "dnf", False)
    assert state["raw"] == fixed
    events = await api.ok("GET", f"{path}/events")
    assert [e["type"] for e in events] == ["raw_set", "aborted", "corrected"]
    ranking = await api.ranking(tid, cid)
    (row,) = ranking["groups"][0]["rows"]
    assert row["place"] == 1
    assert row["abort_label"] == "Abbruch (AB)"

    # Neuaufbau: bleibt offen (nicht abgeschlossen).
    await api.ok("POST", f"/tournaments/{tid}/competitions/{cid}/recompute")
    form = await api.ok("GET", f"{path}/form")
    assert (form["current"]["is_final"], form["current"]["raw"]) == (False, fixed)
    audit = [i for i in await audit_of(api) if i["action"] == "result.corrected"]
    assert audit[0]["details"]["status"] == "aborted"


async def test_correct_open_start_still_rejected(api: Api, precision: Setup) -> None:
    tid = precision.tid
    _, sid = await person_start(api, precision)
    state = await api.shoot(tid, sid, shots([10] * 5), final=False)
    body = await api.fail(
        "POST",
        f"{api.start_path(tid, sid)}/correct",
        409,
        json={"raw": shots([9] * 5), "reason": "x", "base_seq": state["seq"]},
    )
    assert "abgeschlossenen oder abgebrochenen" in body["detail"]


# --- Vorabauskunft beim Aufgeben -------------------------------------------------------


async def test_abort_preview_in_form_and_preview(api: Api, fallscheibe: Setup) -> None:
    tid = fallscheibe.tid
    _, sid = await person_start(api, fallscheibe)
    path = api.start_path(tid, sid)

    form = await api.ok("GET", f"{path}/form")
    assert form["abort_preview"] == {
        "would_place": False,
        "reason_code": "no_values",
        "message_de": "Noch kein Wertungsschuss erfasst: Abbruch (AB) ohne Platz.",
        "open_series": [1, 2, 3, 4],
        "score_text": None,
        "open_series_items": [
            {
                "section_id": "fallscheibe",
                "section_name": form["form"]["sections"][0]["name"],
                "series": number,
                "path": f"sections.fallscheibe.series[{number - 1}]",
                "state": "not_shot",
            }
            for number in (1, 2, 3, 4)
        ],
        "missing_fields": [],
    }

    await api.shoot(tid, sid, falls(serie(15), serie(15)), final=False)
    form = await api.ok("GET", f"{path}/form")
    preview = form["abort_preview"]
    assert preview["would_place"] is True
    assert preview["reason_code"] == "placed"
    assert preview["score_text"] == "250,00 s"
    assert preview["open_series"] == [3, 4]
    assert preview["message_de"] == (
        "Würde nach dem bisherigen Ergebnis platziert (250,00 s). Serie 3 und 4 zählen nach der "
        "Regel der Wertung."
    )

    partial = await api.ok(
        "POST", f"{path}/preview", json={"raw": falls(serie(15), serie(15), {"time_cs": 900})}
    )
    assert partial["abort_preview"] == {
        "would_place": False,
        "reason_code": "incomplete_series",
        "message_de": (
            "Serie 3 ist unvollständig erfasst – ohne Serienstatus ‚Abbruch durch den Schützen‘ "
            "bleibt der Start ohne Platz."
        ),
        "open_series": [3, 4],
        "score_text": None,
        "open_series_items": [
            {**item, "state": "started" if item["series"] == 3 else "not_shot"}
            for item in preview["open_series_items"]
        ],
        "missing_fields": [],
    }

    # Dieselbe Rechnung wie die Rangliste: aufgegeben → Platz mit 250,00 s.
    await api.ok("POST", f"{path}/result/abort", json={"abort_reason": "dnf"})
    (row,) = (await api.ranking(tid, fallscheibe.cid))["groups"][0]["rows"]
    assert (row["place"], row["score_text"]) == (1, preview["score_text"])
    # Abgebrochen: Auskunft, wie dieser Abbruch gewertet wird.
    form = await api.ok("GET", f"{path}/form")
    assert form["abort_preview"]["reason_code"] == "placed"
    assert form["abort_preview"]["message_de"].startswith(
        "Abbruch (AB): kommt nach dem bisherigen Ergebnis in die Rangliste (250,00 s)."
    )


async def test_abort_preview_rings_counts_unshot_as_zero(api: Api, precision: Setup) -> None:
    tid = precision.tid
    _, sid = await person_start(api, precision)
    preview = await api.ok(
        "POST", f"{api.start_path(tid, sid)}/preview", json={"raw": shots([10, 9, 9, 9, 9])}
    )
    assert preview["abort_preview"]["would_place"] is True
    assert preview["abort_preview"]["open_series"] == [2]
    assert preview["abort_preview"]["score_text"] == "46 Ringe"


# --- Gleichstand: entschieden nach … ---------------------------------------------------


async def test_ranking_shows_resolving_criterion(api: Api, precision: Setup) -> None:
    tid = precision.tid
    _, a = await person_start(api, precision)
    _, b = await person_start(api, precision)
    await api.shoot(tid, a, shots([10, 10, 9, 9, 8], [9] * 5))  # 91, 2 Zehner
    await api.shoot(tid, b, shots([10, 9, 9, 9, 9], [9] * 5))  # 91, 1 Zehner
    rows = (await api.ranking(tid, precision.cid))["groups"][0]["rows"]
    assert [(r["start_id"], r["place"]) for r in rows] == [(a, 1), (b, 2)]
    for row in rows:
        assert (row["tied"], row["tie_unresolved"], row["tie_reason"]) == (False, False, "resolved")
        assert row["tie_criterion"] == "zehner"
        assert row["tie_note"] == "Ringgleichheit, entschieden nach: Anzahl der Zehner"


# --- Abbruch-Bemerkungen ----------------------------------------------------------------


async def test_abort_note_provider_is_registered(api: Api, precision: Setup) -> None:
    assert hooks._abort_note_provider == [abort_remarks]
    tid = precision.tid
    _, sid = await person_start(api, precision)
    await api.ok(
        "POST",
        f"{api.start_path(tid, sid)}/result/abort",
        json={"abort_reason": "dns", "reason": "Krank"},
    )
    session_factory = api.app.state.session_factory
    async with session_factory() as session:
        notes = await hooks.abort_notes(session, [uuid.UUID(sid)])
    assert list(notes.values()) == ["Krank"]
    # Beim Herunterfahren meldet sich das Modul ab, beim Start wieder an.
    await ergebnisse.on_shutdown(api.app)
    try:
        assert hooks._abort_note_provider == []
    finally:
        await ergebnisse.on_startup(api.app)
    assert hooks._abort_note_provider == [abort_remarks]
