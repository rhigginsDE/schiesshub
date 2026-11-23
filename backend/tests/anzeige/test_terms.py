"""Anzeige: `tie_reason` je Zeile, Titel nach dem Verband, keine Bemerkung zum Abbruch."""

from app.core.begriffe import begriffe_fuer
from tests.anzeige.conftest import Api, Setup, shots
from tests.anzeige.test_feed import rows


async def test_rows_carry_tie_reason_and_no_abort_remark(api: Api, setup: Setup) -> None:
    sids = []
    for name in ("Anna Gleich", "Berta Gleich", "Carla Weg"):
        entry = await api.entry(setup.tid, setup.class_id, name)
        sids.append(await api.start(setup.tid, entry, setup.cid))
    # Präzision mit Gleichstand nach Zehnern und Innenzehnern: völlig gleich → gleicher Platz,
    # alle Kriterien gerechnet (kein Grund).
    await api.shoot(setup.tid, sids[0], shots([10, 9, 9, 9, 9], [9] * 5))
    await api.shoot(setup.tid, sids[1], shots([9, 9, 10, 9, 9], [9] * 5))
    await api.call(setup.tid, sids[2])
    await api.ok(
        "POST",
        f"/tournaments/{setup.tid}/starts/{sids[2]}/result/abort",
        json={"abort_reason": "dnf", "reason": "Waffendefekt"},
    )
    display_id = await api.show(
        {"id": "live", "kind": "live_ranking", "show_aborted": True},
        {"id": "sieger", "kind": "winners"},
    )
    feed = await api.feed(display_id)
    live, winners = feed["scenes"]
    found = {row["start_id"]: row for row in rows(live)}
    assert found[sids[0]]["tied"] is True
    assert "tie_reason" in found[sids[0]]
    assert found[sids[0]]["tie_reason"] is None
    assert found[sids[0]]["tie_unresolved"] is False
    assert live["ranking"]["tie_word"] == "Ringgleichheit"
    assert live["ranking"]["federation"] is None
    assert feed["header"]["is_practice"] is False
    unplaced = [row for group in live["ranking"]["groups"] for row in group["unplaced"]]
    assert [row["abort_label"] for row in unplaced] == ["Abbruch (AB)"]
    assert "Waffendefekt" not in str(feed)
    assert all("abort_remark" not in row for row in [*rows(live), *unplaced])
    # eigene Disziplin: Standardsatz
    assert winners["title"] == begriffe_fuer(None).ergebnisliste


async def test_startlist_person_has_abort_label_and_federation(api: Api, setup: Setup) -> None:
    entry = await api.entry(setup.tid, setup.class_id, "Dora Weg")
    sid = await api.start(setup.tid, entry, setup.cid)
    await api.call(setup.tid, sid)
    await api.ok(
        "POST",
        f"/tournaments/{setup.tid}/starts/{sid}/result/abort",
        json={"abort_reason": "dns"},
    )
    other = await api.entry(setup.tid, setup.class_id, "Emil Wartet")
    open_sid = await api.start(setup.tid, other, setup.cid)
    display_id = await api.show(
        {"id": "liste", "kind": "startlist", "include_finished": True},
    )
    (page,) = (await api.feed(display_id))["scenes"]
    startlist = page["startlist"]
    assert startlist["federation"] is None
    by_id = {person["start_id"]: person for person in startlist["starts"]}
    assert by_id[sid]["abort_label"] == "nicht angetreten"
    assert by_id[open_sid]["abort_label"] is None
