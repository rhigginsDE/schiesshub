"""Ergebnisse: Kopf der Maske, Namen im Verlauf, Korrektur-Vorschau, Einspruchsfrist bei Korrektur,
Fortschritt für die Sichten am Stand."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Request
from sqlalchemy import select

from app.core.security import Actor, reset_permission_checker, set_permission_checker
from app.modules.auth.models import Device, Role, UserAccount
from app.modules.ergebnisse.progress import progress_of
from tests.ergebnisse.conftest import (
    FALLSCHEIBE,
    Api,
    Setup,
    precision_definition,
    shots,
)


async def one_start(api: Api, setup: Setup) -> str:
    eid = await api.entry(setup.tid, setup.class_id)
    return (await api.starts(setup.tid, eid, setup.cid))[0]


# --- Kopf der Maske ------------------------------------------------------------------


async def test_form_header_has_code_and_range(
    api: Api, precision: Setup, fallscheibe: Setup
) -> None:
    sid = await one_start(api, precision)
    header = (await api.ok("GET", f"{api.start_path(precision.tid, sid)}/form"))["header"]
    assert header["competition_code"] is None
    assert (header["range_id"], header["range_name"]) == (precision.range_id, "Stand 1")

    sid = await one_start(api, fallscheibe)
    header = (await api.ok("GET", f"{api.start_path(fallscheibe.tid, sid)}/form"))["header"]
    assert header["competition_code"] == FALLSCHEIBE


async def test_form_header_without_range(api: Api) -> None:
    tid = await api.tournament()
    class_id = await api.klass(tid)
    body = {"name": "Ohne Stand", "range_id": None, "definition": precision_definition()}
    cid = (await api.ok("POST", f"/tournaments/{tid}/competitions", 201, json=body))["id"]
    eid = await api.entry(tid, class_id)
    sid = (await api.starts(tid, eid, cid))[0]
    header = (await api.ok("GET", f"{api.start_path(tid, sid)}/form"))["header"]
    assert (header["range_id"], header["range_name"]) == (None, None)


# --- Namen im Verlauf ------------------------------------------------------------------


@pytest.fixture
def acting() -> Iterator[list[Actor]]:
    """Wer als Handelnder gilt (erster Eintrag); ohne Eintrag niemand."""
    who: list[Actor] = []

    async def checker(request: Request, permission: str) -> Actor:
        return who[0] if who else Actor()

    set_permission_checker(checker)
    yield who
    reset_permission_checker()


async def test_events_resolve_user_and_device_names_at_query_time(
    api: Api, precision: Setup, acting: list[Actor]
) -> None:
    factory = api.app.state.session_factory
    async with factory() as session:
        role = await session.scalar(select(Role).limit(1))
        assert role is not None
        user = UserAccount(name="Erika Auswertung", pin_hash="x", role_id=role.id)
        device = Device(name="Terminal 1", token_hash="h" * 64, paired_at=datetime.now(UTC))
        session.add_all([user, device])
        await session.commit()
        user_id, device_id = user.id, device.id

    sid = await one_start(api, precision)
    path = api.start_path(precision.tid, sid)
    acting.append(Actor(user_id=user_id, device_id=device_id))
    state = await api.put_raw(precision.tid, sid, shots([10] * 5), 0)
    acting.clear()
    acting.append(Actor(user_id=None, device_id=device_id))
    await api.put_raw(precision.tid, sid, shots([10] * 5, [9] * 5), state["seq"])

    async with factory() as session:
        renamed = await session.get(UserAccount, user_id)
        assert renamed is not None
        renamed.name = "Erika Neu"
        await session.commit()

    events = await api.ok("GET", f"{path}/events")
    assert [(e["user_id"], e["user_name"], e["device_name"]) for e in events] == [
        (str(user_id), "Erika Neu", "Terminal 1"),
        (None, None, "Terminal 1"),
    ]


# --- Vorschau ------------------------------------------------------------------------


async def test_preview_computes_without_storing(api: Api, precision: Setup) -> None:
    sid = await one_start(api, precision)
    path = api.start_path(precision.tid, sid)
    api.drain()

    partial = await api.ok("POST", f"{path}/preview", json={"raw": shots([10, 9, 9, 8, 7])})
    assert (partial["valid"], partial["complete"], partial["errors"]) == (True, False, [])
    assert partial["score"] == "43"
    assert partial["computed"]["progress"]["series_complete"] == 1
    assert [e["message"] for e in partial["finalize_errors"]] == ["Serie 2 fehlt"]
    assert (partial["seq"], partial["status"]) == (0, "registered")

    wrong = await api.ok("POST", f"{path}/preview", json={"raw": shots([11, 9, 9, 8, 7])})
    assert wrong["valid"] is False
    assert wrong["computed"] is None
    assert wrong["score"] is None
    assert wrong["errors"][0]["field"].startswith("raw.sections.praezision.series[0]")

    # Nichts gespeichert: kein Ereignis, kein Statuswechsel, keine Server-Ereignisse.
    assert await api.ok("GET", f"{path}/events") == []
    form = await api.ok("GET", f"{path}/form")
    assert (form["current"]["seq"], form["current"]["status"]) == (0, "registered")
    assert api.drain() == []


async def test_preview_for_a_correction(api: Api, precision: Setup) -> None:
    sid = await one_start(api, precision)
    path = api.start_path(precision.tid, sid)
    state = await api.shoot(precision.tid, sid, shots([10] * 5, [9] * 5))
    fixed = shots([10] * 5, [10] * 5)
    preview = await api.ok("POST", f"{path}/preview", json={"raw": fixed})
    assert (preview["complete"], preview["score"], preview["seq"]) == (True, "100", state["seq"])
    assert preview["status"] == "final"
    assert (await api.ok("GET", f"{path}/form"))["current"]["score"] == "95"
    await api.fail("POST", f"{path}/preview", 422, json={"raw": fixed, "extra": 1})


# --- Einspruchsfrist bei einer Korrektur ---------------------------------------------------


async def _corrected(api: Api, **settings: object) -> tuple[dict, dict, Setup]:
    tid = await api.tournament(protest_minutes=30, **settings)
    range_id = await api.range(tid)
    class_id = await api.klass(tid)
    cid = (await api.competition(tid, range_id, definition=precision_definition()))["id"]
    setup = Setup(tid, range_id, class_id, cid)
    sid = await one_start(api, setup)
    final = await api.shoot(tid, sid, shots([10] * 5, [9] * 5))
    corrected = await api.ok(
        "POST",
        f"{api.start_path(tid, sid)}/correct",
        json={"raw": shots([10] * 5, [10] * 5), "reason": "Ablesefehler", "base_seq": 2},
    )
    return final, corrected, setup


async def test_correction_restarts_protest_period_by_default(api: Api) -> None:
    final, corrected, _ = await _corrected(api)
    assert corrected["finalized_at"] > final["finalized_at"]
    finalized = datetime.fromisoformat(corrected["finalized_at"])
    until = datetime.fromisoformat(corrected["provisional_until"])
    assert until - finalized == timedelta(minutes=30)


async def test_correction_keeps_protest_period_when_configured(api: Api) -> None:
    final, corrected, setup = await _corrected(api, protest_restart_on_correction=False)
    assert corrected["score"] == "100"
    assert corrected["finalized_at"] == final["finalized_at"]
    assert corrected["provisional_until"] == final["provisional_until"]
    sid = corrected["start_id"]
    events = await api.ok("GET", f"{api.start_path(setup.tid, sid)}/events")
    assert events[-1]["type"] == "corrected"
    assert events[-1]["provisional_until"] == final["provisional_until"]

    # Der Neuaufbau aus den Ereignissen kommt zum selben Stand.
    await api.ok("POST", f"/tournaments/{setup.tid}/competitions/{setup.cid}/recompute")
    form = await api.ok("GET", f"{api.start_path(setup.tid, sid)}/form")
    assert form["current"]["finalized_at"] == final["finalized_at"]
    assert form["current"]["provisional_until"] == final["provisional_until"]


async def test_protest_restart_setting_is_validated(api: Api) -> None:
    body = await api.fail(
        "POST",
        "/tournaments",
        422,
        json={
            "name": "X",
            "date_from": "2027-03-06",
            "settings": {"protest_restart_on_correction": "nein"},
        },
    )
    assert body["errors"][0]["field"] == "settings.protest_restart_on_correction"
    tid = await api.tournament()
    tournament = await api.ok("GET", f"/tournaments/{tid}")
    assert tournament["settings"]["protest_restart_on_correction"] is True


# --- Fortschritt ----------------------------------------------------------------------


def test_progress_of_computed() -> None:
    assert progress_of(None) is None
    assert progress_of({}) is None
    computed = {
        "complete": False,
        "sections": [
            {"id": "a", "complete": True, "series": [{"complete": True}]},
            {"id": "b", "complete": False, "series": [{"complete": True}, {"complete": False}]},
        ],
    }
    progress = progress_of(computed)
    assert progress is not None
    assert progress.model_dump() == {
        "section_id": "b",
        "series_done": 1,
        "series_total": 2,
        "complete": False,
        "section_number": 2,
        "section_count": 2,
        "series_done_overall": 2,
        "series_total_overall": 3,
    }
    computed["sections"][1]["complete"] = True
    computed["complete"] = True
    progress = progress_of(computed)
    assert progress is not None
    assert (progress.section_id, progress.complete) == ("b", True)
