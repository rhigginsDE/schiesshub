"""Befunde aus dem Audit (22.11.2026): Wertung abgebrochener Starts, Reihenfolge der Eingaben,
Protokoll, ältere Turnier-Einstellungen, Plausibilität gespeicherter Ergebnisse."""

import asyncio
import uuid
from typing import Any

from sqlalchemy import select, update

from app.modules.ergebnisse.models import ResultEvent
from app.modules.turnier.models import Tournament
from tests.ergebnisse.conftest import (
    API,
    FALLSCHEIBE,
    Api,
    Setup,
    falls,
    make_setup,
    shots,
)


def rows_of(ranking: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for group in ranking["groups"] for row in group["rows"]]


def serie(seconds: int, standing: int = 0) -> dict[str, Any]:
    return {"time_cs": seconds * 100, "standing": standing}


async def person_start(
    api: Api, setup: Setup, class_id: str | None = None, count: int = 1, **person: Any
) -> list[str]:
    eid = await api.entry(setup.tid, class_id or setup.class_id, **person)
    return await api.starts(setup.tid, eid, setup.cid, count)


async def give_up(api: Api, tid: str, sid: str, raw: dict[str, Any] | None = None) -> None:
    """Aufrufen, Teil erfassen, dann „aufgegeben“."""
    await api.call(tid, sid)
    if raw is not None:
        await api.put_raw(tid, sid, raw, 0)
    await api.ok("POST", f"{api.start_path(tid, sid)}/result/abort", json={"abort_reason": "dnf"})


async def abort(api: Api, tid: str, sid: str, reason: str) -> None:
    await api.ok("POST", f"/tournaments/{tid}/starts/{sid}/abort", json={"abort_reason": reason})


# --- Befund 1 (Regel seit 23.11.: Sporthandbuch K 1.14 / L 1.12) ----------------------------
# Abbruch nach „Feuer“: platziert nach dem bis dahin erzielten Ergebnis, nicht geschossene Serien
# nach der Regel der Wertung. Ohne Platz: nicht angetreten, disqualifiziert, Abbruch ohne
# Wertungswert (AB im Probeschießen).


async def test_fallscheibe_dnf_unshot_series_count_as_aborted_and_place_normally(
    api: Api, fallscheibe: Setup
) -> None:
    """QA 22.11.: 2 von 4 Serien, dann aufgegeben, stand mit 30 s auf Platz 1."""
    tid = fallscheibe.tid
    alone_class = await api.klass(tid, "alters")
    (bernd,) = await person_start(api, fallscheibe)
    (dieter,) = await person_start(api, fallscheibe)
    (emil,) = await person_start(api, fallscheibe)
    (fritz,) = await person_start(api, fallscheibe)
    (allein,) = await person_start(api, fallscheibe, alone_class)
    await api.shoot(tid, bernd, falls(serie(40), serie(40), serie(40), serie(39)))  # 159,00 s
    # 15 + 15 + (60 + 5 × 10) + (60 + 5 × 10) = 250,00 s
    await give_up(api, tid, dieter, falls(serie(15), serie(15)))
    await abort(api, tid, emil, "dns")
    await give_up(api, tid, fritz)  # ohne Wertungswert: Abbruch im Probeschießen
    await give_up(api, tid, allein, falls(serie(10), serie(10)))

    ranking = await api.ranking(tid, fallscheibe.cid)
    assert ranking["tie_word"] == "gleiches Ergebnis"
    rows = {group["class_id"]: group["rows"] for group in ranking["groups"]}
    main = rows[fallscheibe.class_id]
    assert [
        (r["start_id"], r["place"], r["group"], r["abort_reason"], r["abort_label"]) for r in main
    ] == [
        (bernd, 1, "ranked", None, None),
        (dieter, 2, "ranked", "dnf", "Abbruch (AB)"),
        (fritz, None, "unranked", "dnf", "Abbruch (AB)"),
        (emil, None, "unranked", "dns", "nicht angetreten"),
    ]
    assert main[1]["score"] == "250.00"
    assert main[1]["score_text"] == "250,00 s"
    assert [s["total_cs"] for s in main[1]["series"]] == [1500, 1500, 11000, 11000]
    assert [s["status"] for s in main[1]["series"]][2:] == ["aborted_by_shooter"] * 2
    assert all(r["abort_note"] is None for r in main)
    assert [(r["place"], r["abort_reason"]) for r in rows[alone_class]] == [(1, "dnf")]

    # Ohne Abgebrochene ohne Platz: der platzierte Abbruch bleibt.
    without = await api.ranking(tid, fallscheibe.cid, include_aborted="false")
    assert [r["start_id"] for r in rows_of(without)] == [bernd, dieter, allein]
    # Live: dieselbe Regel.
    live = rows_of(await api.ranking(tid, fallscheibe.cid, scope="live"))
    assert [(r["start_id"], r["place"]) for r in live][:3] == [
        (bernd, 1),
        (dieter, 2),
        (fritz, None),
    ]

    # Gespeichert bleibt der Zwischenstand der Erfassung (Rohwerte ändern sich nicht).
    form = await api.ok("GET", f"{api.start_path(tid, dieter)}/form")
    assert form["current"]["score"] == "30.00"


async def test_ring_scoring_dnf_counts_missing_shots_as_zero(api: Api, precision: Setup) -> None:
    tid = precision.tid
    (fertig,) = await person_start(api, precision)
    (aufgegeben,) = await person_start(api, precision)
    (stark,) = await person_start(api, precision)
    await api.shoot(tid, fertig, shots([9] * 5, [9] * 5))  # 90
    await give_up(api, tid, aufgegeben, shots([10] * 5))  # 50 + 0
    await give_up(api, tid, stark, shots([10] * 5, [10, 10, 10, 10]))  # 90, ein Schuss fehlt

    ranking = await api.ranking(tid, precision.cid)
    assert ranking["tie_word"] == "Ringgleichheit"
    rows = rows_of(ranking)
    assert [(r["start_id"], r["place"], r["group"], r["score"]) for r in rows] == [
        (stark, 1, "ranked", "90"),
        (fertig, 2, "ranked", "90"),
        (aufgegeben, 3, "ranked", "50"),
    ]


async def test_live_ranking_never_places_abort_without_values_both_directions(
    api: Api, precision: Setup, fallscheibe: Setup
) -> None:
    """QA 22.11.: Aufgegeben ohne Eingabe stand live als „1“ mit 0 Ringen (bleibt ohne Platz:
    Abbruch vor dem ersten Wertungsschuss)."""
    for setup, done, running in (
        (precision, shots([9] * 5, [9] * 5), shots([10] * 5)),
        (fallscheibe, falls(serie(12), serie(12), serie(12), serie(12)), falls(serie(5))),
    ):
        alone = await api.klass(setup.tid, "einzel")
        (fertig,) = await person_start(api, setup)
        (laeuft,) = await person_start(api, setup)
        (leer,) = await person_start(api, setup)
        (allein,) = await person_start(api, setup, alone)
        await api.shoot(setup.tid, fertig, done)
        await api.shoot(setup.tid, laeuft, running, final=False)
        await api.ok("POST", f"{api.start_path(setup.tid, laeuft)}/release-lane")
        await give_up(api, setup.tid, leer)  # ohne jede Eingabe
        await give_up(api, setup.tid, allein)
        for scope in ("live", "final"):
            ranking = await api.ranking(setup.tid, setup.cid, scope=scope)
            for group in ranking["groups"]:
                aborted = [r for r in group["rows"] if r["abort_reason"]]
                assert all(r["place"] is None for r in aborted), (scope, aborted)
                seen_aborted = False
                for row in group["rows"]:
                    seen_aborted = seen_aborted or row["abort_reason"] is not None
                    assert not (seen_aborted and row["abort_reason"] is None), scope
        live = rows_of(await api.ranking(setup.tid, setup.cid, scope="live"))
        placed = [(r["start_id"], r["place"]) for r in live if r["place"] is not None]
        assert placed == [(fertig, 1), (laeuft, 2)]


async def test_multi_start_prefers_scored_attempt_over_aborted(api: Api) -> None:
    setup = await make_setup(
        api,
        catalog_federation="bds",
        catalog_code=FALLSCHEIBE,
        capture_mode="series",
        multi_start=True,
        max_starts=2,
        multi_start_rule="best",
    )
    tid = setup.tid
    first, second = await person_start(api, setup, count=2)
    only_a, only_b = await person_start(api, setup, count=2)
    await give_up(api, tid, first, falls(serie(10), serie(10)))  # 20,00 s, „besser“
    await api.shoot(tid, second, falls(serie(12), serie(12), serie(12), serie(12)))
    await give_up(api, tid, only_a, falls(serie(5)))
    await abort(api, tid, only_b, "dns")

    rows = rows_of(await api.ranking(tid, setup.cid))
    # first: 10 + 10 + 110 + 110 = 240 s (Abbruch, platzierbar) gegen 48 s → zweiter Start.
    # only_a: 5 + 3 × 110 = 335 s, platziert; der nicht angetretene Versuch zählt nicht.
    assert [(r["start_id"], r["place"], r["abort_reason"]) for r in rows] == [
        (second, 1, None),
        (only_a, 2, "dnf"),
    ]


async def test_multi_start_placed_abort_competes_like_a_result(api: Api) -> None:
    for rule, expected in (("best", "first"), ("first", "first")):
        setup = await make_setup(
            api,
            catalog_federation="bds",
            catalog_code=FALLSCHEIBE,
            capture_mode="series",
            multi_start=True,
            max_starts=2,
            multi_start_rule=rule,
        )
        tid = setup.tid
        first, second = await person_start(api, setup, count=2)
        # Erster Start: 3 Serien à 10 s, dann Abbruch → 30 + 110 = 140 s; zweiter 200 s.
        await give_up(api, tid, first, falls(serie(10), serie(10), serie(10)))
        await api.shoot(tid, second, falls(serie(50), serie(50), serie(50), serie(50)))
        rows = rows_of(await api.ranking(tid, setup.cid))
        ids = {"first": first, "second": second}
        assert [(r["start_id"], r["place"]) for r in rows] == [(ids[expected], 1)], rule


# --- Befund 2: ältere Einstellungen ohne neue Schlüssel ----------------------------------


async def test_old_settings_without_new_keys(api: Api, precision: Setup) -> None:
    async with api.app.state.session_factory() as session:
        await session.execute(
            update(Tournament)
            .where(Tournament.id == precision.tid)
            .values(settings={"protest_minutes": 30})
        )
        await session.commit()
    (sid,) = await person_start(api, precision)
    state = await api.shoot(precision.tid, sid, shots([9] * 5, [9] * 5))
    assert state["provisional_until"] is not None
    corrected = await api.ok(
        "POST",
        f"{api.start_path(precision.tid, sid)}/correct",
        json={"raw": shots([10] * 5, [9] * 5), "reason": "Ablesefehler", "base_seq": state["seq"]},
    )
    assert corrected["score"] == "95"
    assert rows_of(await api.ranking(precision.tid, precision.cid))[0]["place"] == 1
    await api.ok("GET", f"/tournaments/{precision.tid}/ranking-summary")
    response = await api.client.get(f"{API}/tournaments/{precision.tid}/export/winners.csv")
    assert response.status_code == 200, response.text


# --- Befund 6: Reihenfolge der Eingaben ----------------------------------------------------


async def test_put_raw_requires_base_seq(api: Api, precision: Setup) -> None:
    (sid,) = await person_start(api, precision)
    await api.call(precision.tid, sid)
    body = await api.fail(
        "PUT", f"{api.start_path(precision.tid, sid)}/raw", 422, json={"raw": shots([9] * 5)}
    )
    assert "base_seq" in str(body)


async def test_concurrent_puts_with_same_base_seq_one_wins(api: Api, precision: Setup) -> None:
    (sid,) = await person_start(api, precision)
    await api.call(precision.tid, sid)
    path = f"{API}{api.start_path(precision.tid, sid)}/raw"
    bodies = [{"raw": shots([n] * 5), "base_seq": 0} for n in (7, 8, 9, 10)]
    responses = await asyncio.gather(*(api.client.put(path, json=body) for body in bodies))
    codes = sorted(response.status_code for response in responses)
    assert codes == [200, 409, 409, 409]
    winner = next(r for r in responses if r.status_code == 200).json()
    for response in responses:
        if response.status_code == 409:
            assert response.json()["current"]["seq"] == 1
            assert response.json()["current"]["raw"] == winner["raw"]


async def test_stale_request_after_newer_one_is_rejected(api: Api, precision: Setup) -> None:
    (sid,) = await person_start(api, precision)
    await api.call(precision.tid, sid)
    first = await api.put_raw(precision.tid, sid, shots([9] * 5), 0)
    second = await api.put_raw(precision.tid, sid, shots([9] * 5, [8] * 5), first["seq"])
    # Die ältere Anfrage (nur Serie 1) kommt nach der neueren an: abgelehnt, nichts verloren.
    path = f"{api.start_path(precision.tid, sid)}/raw"
    conflict = await api.fail(
        "PUT", path, 409, json={"raw": shots([9, 9, 9, 9, 1]), "base_seq": first["seq"]}
    )
    assert conflict["current"]["seq"] == second["seq"]
    assert conflict["current"]["raw"] == shots([9] * 5, [8] * 5)


async def test_same_idempotency_key_other_content_is_rejected(api: Api, precision: Setup) -> None:
    (sid,) = await person_start(api, precision)
    await api.call(precision.tid, sid)
    path = f"{api.start_path(precision.tid, sid)}/raw"
    headers = {"Idempotency-Key": "abc-1"}
    state = await api.ok("PUT", path, json={"raw": shots([9] * 5), "base_seq": 0}, headers=headers)
    again = await api.ok("PUT", path, json={"raw": shots([9] * 5), "base_seq": 0}, headers=headers)
    assert again["seq"] == state["seq"] == 1
    other = await api.fail(
        "PUT", path, 422, json={"raw": shots([8] * 5), "base_seq": 0}, headers=headers
    )
    assert "Idempotency-Key" in str(other)
    assert "anderen Eingabe" in str(other)
    async with api.app.state.session_factory() as session:
        count = len(
            list(await session.scalars(select(ResultEvent).where(ResultEvent.start_id == sid)))
        )
    assert count == 1


async def test_finalize_checks_expected_seq_and_score(api: Api, precision: Setup) -> None:
    (sid,) = await person_start(api, precision)
    await api.call(precision.tid, sid)
    state = await api.put_raw(precision.tid, sid, shots([9] * 5, [9] * 5), 0)
    path = f"{api.start_path(precision.tid, sid)}/finalize"
    wrong_score = await api.fail(
        "POST", path, 409, json={"base_seq": state["seq"], "expected_score": "91"}
    )
    assert wrong_score["current"]["score"] == "90"
    assert "Ergebnis" in wrong_score["detail"]
    wrong_seq = await api.fail(
        "POST", path, 409, json={"base_seq": state["seq"], "expected_seq": state["seq"] + 1}
    )
    assert wrong_seq["current"]["seq"] == state["seq"]
    final = await api.ok(
        "POST",
        path,
        json={"base_seq": state["seq"], "expected_seq": state["seq"], "expected_score": "90.00"},
    )
    assert final["status"] == "final"


async def test_finalize_and_put_raw_race(api: Api, precision: Setup) -> None:
    """Abschluss und eine letzte Eingabe mit demselben Stand: Nur eins geht durch."""
    (sid,) = await person_start(api, precision)
    await api.call(precision.tid, sid)
    state = await api.put_raw(precision.tid, sid, shots([9] * 5, [9] * 5), 0)
    base = f"{API}{api.start_path(precision.tid, sid)}"
    raw_put, final = await asyncio.gather(
        api.client.put(
            f"{base}/raw", json={"raw": shots([9] * 5, [10] * 5), "base_seq": state["seq"]}
        ),
        api.client.post(f"{base}/finalize", json={"base_seq": state["seq"]}),
    )
    assert sorted([raw_put.status_code, final.status_code]) == [200, 409]


# --- Befund 5: Protokoll -------------------------------------------------------------


async def audit_of(api: Api) -> list[dict[str, Any]]:
    return (await api.ok("GET", "/audit", params={"limit": 200}))["items"]


async def test_result_actions_are_in_the_audit_log(api: Api, fallscheibe: Setup) -> None:
    tid = fallscheibe.tid
    (sid,) = await person_start(api, fallscheibe, name="Geheim Name")
    (other,) = await person_start(api, fallscheibe, name="Geheim Zwei")
    raw = falls(serie(12), serie(12), serie(12), serie(12))
    state = await api.shoot(tid, sid, raw)
    state = await api.ok(
        "POST",
        f"{api.start_path(tid, sid)}/correct",
        json={
            "raw": falls(serie(11), serie(12), serie(12), serie(12)),
            "reason": "Zeit falsch abgelesen",
            "base_seq": state["seq"],
        },
    )
    await api.ok(
        "POST",
        f"{api.start_path(tid, sid)}/reopen",
        json={"reason": "Einspruch", "base_seq": state["seq"]},
    )
    await give_up(api, tid, other, falls(serie(20)))
    await api.ok("POST", f"/tournaments/{tid}/competitions/{fallscheibe.cid}/recompute")

    items = await audit_of(api)
    by_action: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_action.setdefault(item["action"], []).append(item)
    for action in (
        "result.finalized",
        "result.corrected",
        "start.reopened",
        "start.aborted",
        "result.recomputed",
    ):
        assert action in by_action, action
        assert by_action[action][0]["action_text"] != action
    corrected = by_action["result.corrected"][0]["details"]
    assert corrected["start_number"] == 1
    assert corrected["competition_code"] == FALLSCHEIBE
    assert corrected["reason"] == "Zeit falsch abgelesen"
    assert corrected["competition_name"]
    assert by_action["start.reopened"][0]["details"]["reason"] == "Einspruch"
    assert by_action["start.reopened"][0]["details"]["start_number"] == 1
    aborted = by_action["start.aborted"][0]["details"]
    assert (aborted["start_number"], aborted["abort_reason"]) == (2, "dnf")
    assert by_action["result.recomputed"][0]["details"]["competition_code"] == FALLSCHEIBE
    assert "Geheim" not in str(items)


async def test_queue_changes_are_in_the_audit_log(api: Api, precision: Setup) -> None:
    tid = precision.tid
    (a,) = await person_start(api, precision)
    (b,) = await person_start(api, precision)
    await api.ok("POST", f"/tournaments/{tid}/starts/{b}/move", json={"position": 1})
    await api.call(tid, a)
    await api.ok("POST", f"/tournaments/{tid}/starts/{a}/return", json={})
    actions = {item["action"]: item for item in await audit_of(api)}
    assert actions["start.moved"]["details"]["start_number"] == 2
    assert actions["start.moved"]["details"]["position"] == 1
    assert actions["start.returned"]["details"]["start_number"] == 1
    assert actions["start.moved"]["action_text"] != "start.moved"


# --- Befund 7: gespeicherte, unplausible Ergebnisse --------------------------------------


async def test_stored_implausible_result_becomes_review_on_recompute(
    api: Api, fallscheibe: Setup
) -> None:
    tid = fallscheibe.tid
    (sid,) = await person_start(api, fallscheibe)
    await api.shoot(tid, sid, falls(serie(12), serie(12), serie(12), serie(12)))
    # Wie ein Stand von früher, als 9.999 s nur eine Warnung war (Ereignisse sind
    # unveränderlich; ein weiteres wird angehängt).
    async with api.app.state.session_factory() as session:
        session.add(
            ResultEvent(
                id=uuid.uuid4(),
                start_id=uuid.UUID(sid),
                seq=3,
                type="raw_set",
                payload={"raw": falls(serie(12), serie(9999), serie(12), serie(12))},
            )
        )
        await session.commit()
    result = await api.ok("POST", f"/tournaments/{tid}/competitions/{fallscheibe.cid}/recompute")
    assert result["needs_review"] == 1

    state = (await api.ok("GET", f"{api.start_path(tid, sid)}/form"))["current"]
    assert state["needs_review"] is True
    assert state["status"] == "final"
    assert "unplausibel" in state["review_reason"]
    rows = rows_of(await api.ranking(tid, fallscheibe.cid))
    assert [(r["place"], r["status"]) for r in rows] == [(None, "review")]
    # Neue Eingaben dieser Art werden abgelehnt.
    (other,) = await person_start(api, fallscheibe)
    await api.call(tid, other)
    issue = await api.fail(
        "PUT",
        f"{api.start_path(tid, other)}/raw",
        422,
        json={"raw": falls(serie(12), serie(9999)), "base_seq": 0},
    )
    assert "unplausibel" in str(issue)
    assert "Zeitlimit erreicht" in str(issue)


async def test_speed_abort_without_rule_stays_unplaced_with_note(api: Api) -> None:
    """Ringe minus Zeit: für eine nicht geschossene Serie gibt es keine Regel – nichts erfinden."""
    setup = await make_setup(api, catalog_federation="bds", catalog_code="1401")
    tid = setup.tid
    (fertig,) = await person_start(api, setup)
    (aufgegeben,) = await person_start(api, setup)
    serie_ = {"shots": [10, 10, 10, 10, 10], "time_cs": 500}
    await api.shoot(tid, fertig, {"sections": {"speed": {"series": [serie_] * 4}}})
    await give_up(api, tid, aufgegeben, {"sections": {"speed": {"series": [serie_]}}})

    rows = rows_of(await api.ranking(tid, setup.cid))
    assert [(r["start_id"], r["place"], r["group"]) for r in rows] == [
        (fertig, 1, "ranked"),
        (aufgegeben, None, "unranked"),
    ]
    assert rows[1]["abort_label"] == "Abbruch (AB)"
    assert rows[1]["abort_note"] == (
        "Ergebnis nicht vergleichbar: Regel für nicht geschossene Serien fehlt"
    )
