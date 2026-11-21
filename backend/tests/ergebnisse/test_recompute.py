"""Neuaufbau aus den Ereignissen; automatische Neuberechnung bei Änderung der Definition."""

from collections.abc import Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.ergebnisse.conftest import Api, Setup, make_setup, precision_definition, shots

ROW = (
    "SELECT start_id, raw, computed, score, rank_keys, is_final, finalized_at, "
    "provisional_until, last_seq, definition_revision, needs_review, review_reason "
    "FROM result_current ORDER BY start_id"
)


async def snapshot(engine: AsyncEngine) -> list[tuple[Any, ...]]:
    async with engine.connect() as connection:
        return [tuple(row) for row in await connection.execute(text(ROW))]


async def change_definition(
    api: Api, setup: Setup, change: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    url = f"/tournaments/{setup.tid}/competitions/{setup.cid}"
    definition = (await api.ok("GET", url))["definition"]
    change(definition["variant"]["abschnitte"][0])
    return await api.ok(
        "PATCH", url, json={"definition": definition, "reason": "Ausschreibung geändert"}
    )


async def test_rebuild_from_events_gives_identical_state(api: Api, engine: AsyncEngine) -> None:
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    sids = []
    for _ in range(3):
        eid = await api.entry(setup.tid, setup.class_id)
        sids.append((await api.starts(setup.tid, eid, setup.cid))[0])
    a, b, c = sids
    await api.shoot(setup.tid, a, shots([10] * 5, [9] * 5))
    await api.ok(
        "POST",
        f"{api.start_path(setup.tid, a)}/correct",
        json={"raw": shots([10] * 5, [8] * 5), "reason": "Zählfehler", "base_seq": 2},
    )
    await api.shoot(setup.tid, b, shots([7] * 5, [7] * 5))
    await api.ok("POST", f"{api.start_path(setup.tid, b)}/reopen", json={"reason": "Prüfen"})
    await api.shoot(setup.tid, c, shots([9, 9]), final=False)
    await api.ok(
        "POST", f"{api.start_path(setup.tid, c)}/result/abort", json={"abort_reason": "dnf"}
    )

    before = await snapshot(engine)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE result_current SET raw = '{}', computed = NULL, score = NULL, "
                "rank_keys = NULL, is_final = false, finalized_at = NULL, last_seq = 1"
            )
        )
    result = await api.ok("POST", f"/tournaments/{setup.tid}/competitions/{setup.cid}/recompute")
    assert result == {
        "competition_id": setup.cid,
        "definition_revision": 1,
        "recomputed": 3,
        "needs_review": 0,
    }
    assert await snapshot(engine) == before


async def test_counted_series_six_to_four_after_start(api: Api, engine: AsyncEngine) -> None:
    setup = await make_setup(api, definition=precision_definition(series=6), capture_mode="shot")
    first_four = [[10, 10, 9, 9, 8], [10, 9, 9, 8, 8], [10, 10, 10, 9, 9], [9, 9, 9, 9, 9]]
    six = shots(*first_four, [10] * 5, [10] * 5)
    four = shots(*first_four)

    eid_a = await api.entry(setup.tid, setup.class_id)
    eid_b = await api.entry(setup.tid, setup.class_id)
    a = (await api.starts(setup.tid, eid_a, setup.cid))[0]
    b = (await api.starts(setup.tid, eid_b, setup.cid))[0]
    state_a = await api.shoot(setup.tid, a, six)
    assert state_a["score"] == "283"
    state_b = await api.shoot(setup.tid, b, four, final=False)
    await api.fail(
        "POST", f"{api.start_path(setup.tid, b)}/finalize", 422, json={"base_seq": state_b["seq"]}
    )
    events_before = await api.ok("GET", f"{api.start_path(setup.tid, a)}/events")

    # Nach dem Start: nur noch 4 Serien gewertet. Der Neuaufbau läuft automatisch mit.
    competition = await change_definition(api, setup, lambda s: s.update(serien_gewertet=4))
    assert competition["definition_revision"] == 2

    form_a = await api.ok("GET", f"{api.start_path(setup.tid, a)}/form")
    current = form_a["current"]
    assert current["definition_revision"] == 2
    assert current["score"] == "183"
    assert current["raw"] == six  # Rohdaten bleiben, gestrichene Serien inklusive
    assert [s["struck"] for s in current["computed"]["sections"][0]["series"]] == [
        False,
        False,
        False,
        False,
        True,
        True,
    ]
    assert "Serie 5 und 6 gestrichen (nicht gewertet)" in current["computed"]["steps"]
    assert current["needs_review"] is False
    assert await api.ok("GET", f"{api.start_path(setup.tid, a)}/events") == events_before

    state_b = await api.finalize(setup.tid, b, state_b["seq"])
    assert state_b["score"] == "183"

    ranking = await api.ranking(setup.tid, setup.cid)
    rows = ranking["groups"][0]["rows"]
    assert [(r["place"], r["tied"], r["score"]) for r in rows] == [
        (1, True, "183"),
        (1, True, "183"),
    ]
    series_a = next(r for r in rows if r["start_id"] == a)["series"]
    assert [s["struck"] for s in series_a][-2:] == [True, True]
    assert series_a[-1]["rings"] == 50

    # Zurück auf 6: B ist abgeschlossen, aber unvollständig → prüfen, nicht geöffnet.
    await change_definition(api, setup, lambda s: s.pop("serien_gewertet"))
    review = await api.ok("GET", f"/tournaments/{setup.tid}/results/needs-review")
    assert [item["start_id"] for item in review] == [b]
    assert "unvollständig" in review[0]["review_reason"]
    assert "Serie 5 fehlt" in review[0]["review_reason"]
    form_b = await api.ok("GET", f"{api.start_path(setup.tid, b)}/form")
    assert form_b["current"]["status"] == "final"
    assert form_b["current"]["is_final"] is True
    rows = (await api.ranking(setup.tid, setup.cid))["groups"][0]["rows"]
    assert [(r["start_id"], r["place"], r["status"], r["group"]) for r in rows] == [
        (a, 1, "final", "ranked"),
        (b, 2, "review", "last"),
    ]
    summary = await api.ok("GET", f"/tournaments/{setup.tid}/ranking-summary")
    assert summary["competitions"][0]["needs_review"] == 1

    # Mit einer Korrektur (vollständige Rohwerte) ist die Prüfung erledigt.
    await api.ok(
        "POST",
        f"{api.start_path(setup.tid, b)}/correct",
        json={"raw": six, "reason": "Serien 5 und 6 nachgetragen", "base_seq": 2},
    )
    assert await api.ok("GET", f"/tournaments/{setup.tid}/results/needs-review") == []


async def test_raw_that_no_longer_fits_is_marked_not_lost(api: Api) -> None:
    setup = await make_setup(api, definition=precision_definition(series=2), capture_mode="shot")
    eid = await api.entry(setup.tid, setup.class_id)
    sid = (await api.starts(setup.tid, eid, setup.cid))[0]
    raw = shots([10] * 5, [9] * 5)
    await api.shoot(setup.tid, sid, raw)

    # Eine Serie weniger: Die Rohwerte passen nicht mehr. Die Änderung gelingt trotzdem.
    await change_definition(api, setup, lambda s: s.update(serien=1))
    form = await api.ok("GET", f"{api.start_path(setup.tid, sid)}/form")
    current = form["current"]
    assert current["raw"] == raw
    assert current["computed"] is None
    assert current["needs_review"] is True
    assert "passen nicht zur Definition" in current["review_reason"]
    rows = (await api.ranking(setup.tid, setup.cid))["groups"][0]["rows"]
    assert [(r["place"], r["status"]) for r in rows] == [(None, "review")]


async def test_stale_rows_are_brought_up_to_date_on_read(
    api: Api, precision: Setup, engine: AsyncEngine
) -> None:
    eid = await api.entry(precision.tid, precision.class_id)
    sid = (await api.starts(precision.tid, eid, precision.cid))[0]
    await api.shoot(precision.tid, sid, shots([10] * 5, [9] * 5))
    # Etwa eine Erfassung, die gleichzeitig mit einer Änderung der Definition lief
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE result_current SET definition_revision = 0, score = 1")
        )
    rows = (await api.ranking(precision.tid, precision.cid))["groups"][0]["rows"]
    assert rows[0]["score"] == "95"
    assert (await snapshot(engine))[0][9] == 1
