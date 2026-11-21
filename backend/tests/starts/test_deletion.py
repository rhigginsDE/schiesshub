"""Löschschutz im Turnier: Was Anmeldungen, Starts oder Durchgänge hat, lässt sich nicht löschen."""

from collections.abc import Iterator

import pytest

from app.modules.starts.deletion import turnier_deletion_check
from app.modules.turnier import hooks
from tests.starts.conftest import Api, Setup


async def booked(api: Api, setup: Setup, count: int = 2) -> None:
    for _ in range(count):
        entry = await api.entry(setup.tid, setup.class_id)
        await api.book(setup.tid, entry["id"], setup.competition_id)


async def test_competition_with_starts(api: Api, queue_setup: Setup) -> None:
    await booked(api, queue_setup, 2)

    detail = await api.fail(
        "DELETE", f"/tournaments/{queue_setup.tid}/competitions/{queue_setup.competition_id}", 409
    )

    assert detail == "Der Wettbewerb hat 2 Starts und kann nicht gelöscht werden."


async def test_class_with_entries(api: Api, queue_setup: Setup) -> None:
    await api.entry(queue_setup.tid, queue_setup.class_id)

    detail = await api.fail(
        "DELETE", f"/tournaments/{queue_setup.tid}/classes/{queue_setup.class_id}", 409
    )

    assert detail == "Die Klasse hat 1 Anmeldung und kann nicht gelöscht werden."


async def test_range_with_starts(api: Api, queue_setup: Setup) -> None:
    await booked(api, queue_setup, 1)

    detail = await api.fail(
        "DELETE", f"/tournaments/{queue_setup.tid}/ranges/{queue_setup.range_id}", 409
    )

    assert detail == "Der Stand hat 1 Start und kann nicht gelöscht werden."


async def test_range_with_heats(api: Api) -> None:
    tid = await api.tournament()
    range_id = await api.range(tid, lanes=2)
    competition = await api.competition(tid, range_id, planning="schedule", heat_minutes=25)
    await api.ok(
        "POST",
        f"/tournaments/{tid}/ranges/{range_id}/heats/series",
        201,
        json={
            "competition_id": competition["id"],
            "starts_at": "2027-03-06T09:00:00+01:00",
            "count": 3,
        },
    )

    detail = await api.fail("DELETE", f"/tournaments/{tid}/ranges/{range_id}", 409)

    assert detail == "Der Stand hat 3 Durchgänge und kann nicht gelöscht werden."


async def test_tournament_with_entries(api: Api, queue_setup: Setup) -> None:
    await api.entry(queue_setup.tid, queue_setup.class_id)

    detail = await api.fail("DELETE", f"/tournaments/{queue_setup.tid}", 409)

    assert detail == "Das Turnier hat 1 Anmeldung und kann nicht gelöscht werden."


async def test_empty_items_can_still_be_deleted(api: Api, queue_setup: Setup) -> None:
    base = f"/tournaments/{queue_setup.tid}"

    await api.ok("DELETE", f"{base}/competitions/{queue_setup.competition_id}", 204)
    await api.ok("DELETE", f"{base}/classes/{queue_setup.class_id}", 204)
    await api.ok("DELETE", f"{base}/ranges/{queue_setup.range_id}", 204)
    await api.ok("DELETE", base, 204)


@pytest.fixture
def without_checker(api: Api) -> Iterator[None]:
    # Nach dem Start der Anwendung, die den Prüfer im on_startup anmeldet.
    hooks.unregister_deletion_check(turnier_deletion_check)
    yield
    hooks.register_deletion_check(turnier_deletion_check)


@pytest.mark.usefixtures("without_checker")
async def test_database_reference_gives_409_not_500(api: Api, queue_setup: Setup) -> None:
    await booked(api, queue_setup, 1)

    detail = await api.fail(
        "DELETE", f"/tournaments/{queue_setup.tid}/competitions/{queue_setup.competition_id}", 409
    )

    assert detail == (
        "Der Wettbewerb kann nicht gelöscht werden, weil noch Daten darauf verweisen "
        "(zum Beispiel Anmeldungen oder Starts)."
    )
    # Die Sitzung ist danach wieder benutzbar: Der Wettbewerb ist noch da.
    await api.ok("GET", f"/tournaments/{queue_setup.tid}/competitions/{queue_setup.competition_id}")
