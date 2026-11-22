"""Ranglisten: Mehrfachstart, Klassen, Gleichstand, Anzeigename, Umfang, Übersicht."""

from typing import Any

import pytest

from tests.ergebnisse.conftest import Api, Setup, make_setup, precision_definition, shots


def rows_of(ranking: dict[str, Any], group: int = 0) -> list[dict[str, Any]]:
    return ranking["groups"][group]["rows"]


async def person_start(
    api: Api, setup: Setup, class_id: str | None = None, count: int = 1, **person: Any
) -> list[str]:
    eid = await api.entry(setup.tid, class_id or setup.class_id, **person)
    return await api.starts(setup.tid, eid, setup.cid, count)


def series_sum(total_a: int, total_b: int, tens: int | None = None) -> dict[str, Any]:
    def one(total: int) -> dict[str, Any]:
        return {"sum": total} if tens is None else {"sum": total, "tens": tens}

    return {"sections": {"praezision": {"series": [one(total_a), one(total_b)]}}}


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("best", [(1, 1, 2, "95"), (2, 2, 1, "92")]),
        ("first", [(1, 2, 1, "92"), (2, 1, 1, "90")]),
        ("all", [(1, 1, 2, "95"), (2, 2, 1, "92"), (3, 1, 1, "90")]),
    ],
)
async def test_multi_start_rules(
    api: Api, rule: str, expected: list[tuple[int, int, int, str]]
) -> None:
    setup = await make_setup(
        api,
        definition=precision_definition(),
        capture_mode="shot",
        multi_start=True,
        max_starts=3,
        multi_start_rule=rule,
    )
    first, second = await person_start(api, setup, count=2)
    (other,) = await person_start(api, setup)
    await api.shoot(setup.tid, first, shots([9] * 5, [9] * 5))
    await api.shoot(setup.tid, other, shots([10] * 5, [9, 9, 8, 8, 8]))
    await api.shoot(setup.tid, second, shots([10] * 5, [9] * 5))

    rows = rows_of(await api.ranking(setup.tid, setup.cid))
    assert [(r["place"], r["start_number"], r["attempt"], r["score"]) for r in rows] == expected
    assert (await api.ranking(setup.tid, setup.cid))["multi_start_rule"] == rule


async def test_first_rule_waits_for_first_attempt(api: Api) -> None:
    setup = await make_setup(
        api,
        definition=precision_definition(),
        multi_start=True,
        max_starts=2,
        multi_start_rule="first",
    )
    first, second = await person_start(api, setup, count=2)
    await api.shoot(setup.tid, first, shots([9] * 5), final=False)
    # Der erste Start ist erfasst und belegt noch die Bahn; für den zweiten erst freigeben.
    await api.ok("POST", f"{api.start_path(setup.tid, first)}/release-lane")
    await api.shoot(setup.tid, second, shots([10] * 5, [10] * 5))
    assert rows_of(await api.ranking(setup.tid, setup.cid)) == []
    live = rows_of(await api.ranking(setup.tid, setup.cid, scope="live"))
    assert [(r["attempt"], r["status"], r["complete"]) for r in live] == [(1, "running", False)]


async def test_classes_merged_and_combined(api: Api) -> None:
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    ladies = await api.klass(setup.tid, "damen", merge_into_id=setup.class_id)
    (a,) = await person_start(api, setup)
    (b,) = await person_start(api, setup, ladies)
    (c,) = await person_start(api, setup, ladies)
    await api.shoot(setup.tid, a, shots([9] * 5, [9] * 5))
    await api.shoot(setup.tid, b, shots([10] * 5, [10] * 5))
    await api.shoot(setup.tid, c, shots([8] * 5, [8] * 5))

    ranking = await api.ranking(setup.tid, setup.cid)
    assert [(g["class_short"], [r["score"] for r in g["rows"]]) for g in ranking["groups"]] == [
        ("OFF", ["90"]),
        ("DAM", ["100", "80"]),
    ]
    only = await api.ranking(setup.tid, setup.cid, class_id=ladies)
    assert [g["class_id"] for g in only["groups"]] == [ladies]

    merged = await api.ranking(setup.tid, setup.cid, merged="true")
    (group,) = merged["groups"]
    assert group["class_id"] == setup.class_id
    assert sorted(group["class_ids"]) == sorted([setup.class_id, ladies])
    assert [(r["place"], r["class_short"]) for r in group["rows"]] == [
        (1, "DAM"),
        (2, "OFF"),
        (3, "DAM"),
    ]

    url = f"/tournaments/{setup.tid}/competitions/{setup.cid}"
    await api.ok("PATCH", url, json={"combined_ranking": True, "reason": "Gemeinsame Wertung"})
    combined = await api.ranking(setup.tid, setup.cid)
    assert combined["combined"] is True
    (group,) = combined["groups"]
    assert group["class_id"] is None
    assert [r["score"] for r in group["rows"]] == ["100", "90", "80"]
    filtered = rows_of(await api.ranking(setup.tid, setup.cid, class_id=setup.class_id))
    assert [(r["place"], r["score"]) for r in filtered] == [(2, "90")]


async def test_ties_resolved_and_unresolved(api: Api) -> None:
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    starts = {}
    for name in "DABCE":
        (starts[name],) = await person_start(api, setup)
    await api.shoot(setup.tid, starts["D"], shots([10, 10, 9, 9, 9], [10, 10, 9, 9, 8]))  # 93
    await api.shoot(setup.tid, starts["A"], shots([10, 10, 9, 9, 8], [10, 10, 9, 9, 8]))  # 92/4/0
    await api.shoot(setup.tid, starts["B"], shots(["X", 10, 9, 9, 8], [10, 10, 9, 9, 8]))  # 92/4/1
    await api.shoot(setup.tid, starts["C"], series_sum(46, 46, tens=2))  # 92/4/?
    await api.shoot(setup.tid, starts["E"], shots([10, 10, 10, 9, 7], [9, 9, 9, 9, 10]))  # 92/4+…

    rows = rows_of(await api.ranking(setup.tid, setup.cid))
    by_start = {r["start_id"]: r for r in rows}
    assert by_start[starts["D"]]["place"] == 1
    assert by_start[starts["D"]]["tied"] is False
    tied = [by_start[starts[name]] for name in "ABCE"]
    assert {(r["place"], r["tied"], r["tie_unresolved"]) for r in tied} == {(2, True, True)}


async def test_ties_split_by_tens_and_inner_tens(api: Api) -> None:
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    starts = {}
    for name in "ABE":
        (starts[name],) = await person_start(api, setup)
    await api.shoot(setup.tid, starts["A"], shots([10, 10, 9, 9, 8], [10, 10, 9, 9, 8]))
    await api.shoot(setup.tid, starts["B"], shots(["X", 10, 9, 9, 8], [10, 10, 9, 9, 8]))
    await api.shoot(setup.tid, starts["E"], shots([10, 10, 10, 10, 6], [10, 9, 9, 9, 9]))
    rows = rows_of(await api.ranking(setup.tid, setup.cid))
    assert [(r["start_id"], r["place"], r["tied"]) for r in rows] == [
        (starts["E"], 1, False),  # 5 Zehner
        (starts["B"], 2, False),  # 4 Zehner, davon 1 Innenzehner
        (starts["A"], 3, False),  # 4 Zehner, kein Innenzehner
    ]


async def test_display_mode_and_club(api: Api, precision: Setup) -> None:
    club = (await api.ok("POST", "/clubs", 201, json={"name": "SV Tell"}))["id"]
    people = [
        {"name": "Markus Brandt", "display_mode": "short", "club_id": club},
        {"name": "Geheim Person", "display_mode": "hidden", "club_id": club, "show_club": False},
        {"name": "Anna Voll", "display_mode": "full"},
    ]
    for index, person in enumerate(people):
        (sid,) = await person_start(api, precision, **person)
        await api.shoot(precision.tid, sid, shots([10 - index] * 5, [10 - index] * 5))
    rows = rows_of(await api.ranking(precision.tid, precision.cid))
    assert [(r["start_number"], r["display_name"], r["club"]) for r in rows] == [
        (1, "M. Brandt", "SV Tell"),
        (2, None, None),
        (3, "Anna Voll", None),
    ]
    summary = await api.ok("GET", f"/tournaments/{precision.tid}/ranking-summary")
    text = str(summary)
    assert "Markus" not in text
    assert "Geheim" not in text


async def test_scope_status_and_aborts(api: Api) -> None:
    tid = await api.tournament(protest_minutes=30)
    range_id = await api.range(tid)
    class_id = await api.klass(tid)
    cid = (await api.competition(tid, range_id, definition=precision_definition()))["id"]
    setup = Setup(tid, range_id, class_id, cid)
    final, running, dnf, dns, dsq, waiting = [(await person_start(api, setup))[0] for _ in range(6)]
    await api.shoot(tid, final, shots([10] * 5, [9] * 5))
    await api.shoot(tid, running, shots([10] * 5, [10] * 5), final=False)
    await api.shoot(tid, dnf, shots([10] * 5), final=False)
    await api.ok("POST", f"{api.start_path(tid, dnf)}/result/abort", json={"abort_reason": "dnf"})
    await api.ok("POST", f"{api.start_path(tid, dns)}/result/abort", json={"abort_reason": "dns"})
    await api.ok("POST", f"/tournaments/{tid}/starts/{dsq}/abort", json={"abort_reason": "dsq"})

    rows = rows_of(await api.ranking(tid, cid))
    assert [(r["start_id"], r["place"], r["status"], r["group"]) for r in rows] == [
        (final, 1, "provisional", "ranked"),
        (dnf, 2, "aborted", "last"),
    ]
    assert rows[0]["provisional_until"] is not None
    live = rows_of(await api.ranking(tid, cid, scope="live"))
    assert [(r["start_id"], r["place"], r["status"]) for r in live] == [
        (running, 1, "running"),
        (final, 2, "provisional"),
        (dnf, 3, "aborted"),
    ]
    without = rows_of(await api.ranking(tid, cid, include_provisional="false"))
    assert [r["start_id"] for r in without] == [dnf]

    summary = await api.ok("GET", f"/tournaments/{tid}/ranking-summary")
    (item,) = summary["competitions"]
    assert item["counts"] == {"registered": 1, "called": 0, "captured": 1, "final": 1, "aborted": 3}
    assert item["provisional"] == 1
    assert item["needs_review"] == 0
    assert [(leader["start_number"], leader["status"]) for leader in item["leaders"]] == [
        (1, "provisional")
    ]
    assert waiting not in {r["start_id"] for r in live}
