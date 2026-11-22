"""Uhrzeiten in Listen stehen in der Ortszeit des Turniers (`settings.timezone`)."""

from dataclasses import replace
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.modules.export import tables
from app.modules.export.formatting import clock, iso_local, moment_de
from app.modules.export.records import Meta
from tests.export.conftest import (
    Api,
    as_dicts,
    make_setup,
    precision_definition,
    read_csv,
    shots,
)
from tests.export.pdftext import read_pdf

NOW = datetime(2027, 3, 6, 13, 35, tzinfo=UTC)
NEW_YORK = ZoneInfo("America/New_York")


def test_formatting_uses_given_zone_and_berlin_by_default() -> None:
    assert clock(NOW) == "14:35"
    assert clock(NOW, NEW_YORK) == "08:35"
    assert iso_local(NOW, NEW_YORK) == "2027-03-06 08:35"
    assert moment_de(NOW, ZoneInfo("UTC")) == "06.03.2027, 13:35 Uhr"


def test_provisional_note_in_tournament_zone() -> None:
    meta = Meta("Pokal", None, date(2027, 3, 6), date(2027, 3, 6), NOW, "public")
    assert str(meta.tz) == "Europe/Berlin"
    assert tables.provisional_note(NOW, meta) == (
        "Vorläufig – Einspruchsfrist läuft bis 14:35 Uhr."
    )
    tokyo = replace(meta, tz=ZoneInfo("Asia/Tokyo"))
    # 22:35 in Tokio, aber am Turniertag: kein Datum nötig.
    assert tables.provisional_note(NOW, tokyo) == (
        "Vorläufig – Einspruchsfrist läuft bis 22:35 Uhr."
    )
    late = datetime(2027, 3, 6, 16, 0, tzinfo=UTC)
    # 01:00 am Folgetag in Tokio: mit Datum.
    assert tables.provisional_note(late, tokyo) == (
        "Vorläufig – Einspruchsfrist läuft bis 07.03.2027, 01:00 Uhr."
    )


async def test_startlist_csv_and_pdf_use_tournament_zone(api: Api) -> None:
    tid = await api.tournament(timezone="America/New_York")
    range_id = await api.range(tid)
    class_id = await api.klass(tid)
    cid = await api.competition(
        tid,
        range_id,
        definition=precision_definition(),
        capture_mode="shot",
        planning="schedule",
        heat_minutes=20,
    )
    heat = await api.ok(
        "POST",
        f"/tournaments/{tid}/ranges/{range_id}/heats",
        201,
        json={"starts_at": "2027-03-06T15:00:00Z", "ends_at": "2027-03-06T15:20:00Z"},
    )
    eid = await api.entry(tid, class_id, "Anna Beispiel", display_mode="full")
    await api.starts(tid, eid, cid, heat_id=heat["id"])

    response = await api.get(f"/tournaments/{tid}/export/startlist.csv")
    rows = as_dicts(read_csv(response.content))
    assert rows[0]["Beginn"] == "2027-03-06 10:00"
    text = read_pdf((await api.get(f"/tournaments/{tid}/export/startlist.pdf")).content).text
    assert "1 (10:00)" in text

    await api.ok("PATCH", f"/tournaments/{tid}", json={"settings": {"timezone": "UTC"}})
    rows = as_dicts(read_csv((await api.get(f"/tournaments/{tid}/export/startlist.csv")).content))
    assert rows[0]["Beginn"] == "2027-03-06 15:00"


async def test_winners_provisional_until_in_tournament_zone(api: Api) -> None:
    setup = await make_setup(api, tournament={"protest_minutes": 30, "timezone": "UTC"})
    eid = await api.entry(setup.tid, setup.class_id, "Anna Beispiel")
    sid = (await api.starts(setup.tid, eid, setup.cid))[0]
    await api.shoot(setup.tid, sid, shots([9] * 5, [9] * 5))
    form = await api.ok("GET", f"/tournaments/{setup.tid}/starts/{sid}/form")
    until = datetime.fromisoformat(form["current"]["provisional_until"]).astimezone(UTC)
    rows = as_dicts(
        read_csv((await api.get(f"/tournaments/{setup.tid}/export/winners.csv")).content)
    )
    assert rows[0]["Vorläufig bis"] == until.strftime("%Y-%m-%d %H:%M")
