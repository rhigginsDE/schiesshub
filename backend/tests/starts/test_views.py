"""Sichten für die Stationen: Startliste und „am Stand“ respektieren die Anzeige-Einstellung."""

from tests.starts.conftest import Api, Setup


async def _people(api: Api, setup: Setup) -> dict[str, dict]:
    club = await api.club("SV Adlerhorst")
    full = await api.entry(
        setup.tid, setup.class_id, await api.person("Anna Maria Vollname", club_id=club)
    )
    short = await api.entry(
        setup.tid,
        setup.class_id,
        await api.person("Bernhard Kurzform", club_id=club, display_mode="short"),
    )
    hidden = await api.entry(
        setup.tid,
        setup.class_id,
        await api.person("Clara Verborgen", club_id=club, display_mode="hidden", show_club=False),
    )
    for entry in (full, short, hidden):
        await api.book(setup.tid, entry["id"], setup.competition_id)
    return {"full": full, "short": short, "hidden": hidden}


def _assert_private(text: str) -> None:
    assert "Bernhard" not in text
    assert "Clara" not in text
    assert "Verborgen" not in text


async def test_startlist_respects_display_mode(api: Api, queue_setup: Setup) -> None:
    await _people(api, queue_setup)
    response = await api.client.get(f"/api/v1/tournaments/{queue_setup.tid}/startlist")
    assert response.status_code == 200
    _assert_private(response.text)
    rows = response.json()
    assert [(r["start_number"], r["display_name"], r["club"]) for r in rows] == [
        (1, "Anna Maria Vollname", "SV Adlerhorst"),
        (2, "B. Kurzform", "SV Adlerhorst"),
        (3, None, None),
    ]
    first = rows[0]
    assert first["class_short"] == "OFF"
    assert first["competition_name"] == "Fallscheibe"
    assert (first["status"], first["queue_position"], first["lane"]) == ("registered", 1, None)
    assert "name" not in first


async def test_startlist_filters(api: Api, queue_setup: Setup) -> None:
    await _people(api, queue_setup)
    other_range = await api.range(queue_setup.tid, lanes=1, name="Stand 2")
    other = await api.competition(queue_setup.tid, other_range, "Anderer")
    entry = await api.entry(queue_setup.tid, queue_setup.class_id)
    await api.book(queue_setup.tid, entry["id"], other["id"])
    path = f"/tournaments/{queue_setup.tid}/startlist"

    by_competition = await api.ok("GET", path, params={"competition_id": other["id"]})
    assert [row["start_number"] for row in by_competition] == [4]
    by_range = await api.ok("GET", path, params={"range_id": queue_setup.range_id})
    assert [row["start_number"] for row in by_range] == [1, 2, 3]


async def test_range_now_and_queue_respect_display_mode(api: Api, queue_setup: Setup) -> None:
    people = await _people(api, queue_setup)
    await api.ok("POST", f"/tournaments/{queue_setup.tid}/ranges/{queue_setup.range_id}/call-next")

    response = await api.client.get(
        f"/api/v1/tournaments/{queue_setup.tid}/ranges/{queue_setup.range_id}/now"
    )
    assert response.status_code == 200
    _assert_private(response.text)
    now = response.json()
    assert [(lane["lane"], lane["start"]["display_name"]) for lane in now["lanes"]] == [
        (1, "Anna Maria Vollname"),
        (2, "B. Kurzform"),
    ]
    assert [(row["start_number"], row["display_name"]) for row in now["next_queue"]] == [
        (people["hidden"]["start_number"], None)
    ]
    assert now["next_heat"] is None
    assert now["next_heat_starts"] == []

    queue = await api.client.get(
        f"/api/v1/tournaments/{queue_setup.tid}/ranges/{queue_setup.range_id}/queue"
    )
    _assert_private(queue.text)


async def test_range_now_shows_next_heat(api: Api) -> None:
    tid = await api.tournament()
    range_id = await api.range(tid, lanes=2)
    class_id = await api.klass(tid)
    competition = await api.competition(
        tid, range_id, "Präzision", planning="schedule", heat_minutes=30
    )
    heats = await api.ok(
        "POST",
        f"/tournaments/{tid}/ranges/{range_id}/heats/series",
        201,
        json={
            "competition_id": competition["id"],
            "starts_at": "2027-03-06T09:00:00Z",
            "count": 2,
        },
    )
    entry = await api.entry(
        tid, class_id, await api.person("Dieter Geheimer", display_mode="short")
    )
    await api.book(tid, entry["id"], competition["id"], heat_id=heats[1]["id"])

    now = await api.ok("GET", f"/tournaments/{tid}/ranges/{range_id}/now")
    # Durchgang 1 ist leer; als Nächstes kommt Durchgang 2 mit seiner Uhrzeit.
    assert now["next_heat"]["number"] == 2
    assert now["next_heat"]["starts_at"] == "2027-03-06T09:30:00Z"
    assert [(r["display_name"], r["lane"], r["heat_number"]) for r in now["next_heat_starts"]] == [
        ("D. Geheimer", 1, 2)
    ]
