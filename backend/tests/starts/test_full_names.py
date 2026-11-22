"""`names=full` in den Stand-Sichten: voller Name nur für das Personal am Stand."""

from collections.abc import Iterator

import pytest
from fastapi import HTTPException, Request

from app.core.security import Actor, reset_permission_checker, set_permission_checker
from tests.starts.conftest import Api, Setup


@pytest.fixture
def grant() -> Iterator:
    def install(*allowed: str) -> None:
        async def checker(request: Request, permission: str) -> Actor:
            if permission not in allowed:
                raise HTTPException(403, f"Dafür fehlt die Berechtigung „{permission}“.")
            return Actor(permissions=frozenset(allowed))

        set_permission_checker(checker)

    yield install
    reset_permission_checker()


async def setup_people(api: Api, queue_setup: Setup) -> tuple[str, str]:
    tid = queue_setup.tid
    club = (await api.ok("POST", "/clubs", 201, json={"name": "SV Nord"}))["id"]
    hidden = await api.person("Geheim Verborgen", display_mode="hidden", club_id=club)
    short = await api.person("Markus Brandt", display_mode="short", club_id=club, show_club=False)
    starts = []
    for person in (hidden, short):
        entry = await api.entry(tid, queue_setup.class_id, person)
        starts.append((await api.book(tid, entry["id"], queue_setup.competition_id))[0]["id"])
    await api.set_status(tid, "active")
    await api.ok("POST", f"/tournaments/{tid}/starts/{starts[1]}/call")
    return starts[0], starts[1]


def views(tid: str, range_id: str) -> list[str]:
    return [
        f"/tournaments/{tid}/startlist",
        f"/tournaments/{tid}/ranges/{range_id}/queue",
        f"/tournaments/{tid}/ranges/{range_id}/now",
    ]


async def test_full_names_for_staff(api: Api, queue_setup: Setup, grant) -> None:
    await setup_people(api, queue_setup)
    for allowed in ("start.call", "result.capture", "entry.read"):
        grant("start.read", allowed)
        for path in views(queue_setup.tid, queue_setup.range_id):
            public = str(await api.ok("GET", path))
            assert "Geheim" not in public
            assert "Markus" not in public
            full = await api.ok("GET", path, params={"names": "full"})
            text = str(full)
            assert "Geheim Verborgen" in text, (allowed, path)
            assert "Markus Brandt" in text
            # Öffentliche Felder bleiben, wie sie sind.
            assert "'display_name': 'M. Brandt'" in text
            assert "'full_club': 'SV Nord'" in text


async def test_without_permission_never_full_names(api: Api, queue_setup: Setup, grant) -> None:
    await setup_people(api, queue_setup)
    grant("start.read")
    for path in views(queue_setup.tid, queue_setup.range_id):
        denied = await api.fail("GET", path, 403, params={"names": "full"})
        assert "start.call" in denied
        public = str(await api.ok("GET", path))
        assert "Geheim" not in public
        assert "Markus" not in public
        assert "'full_name': None" in public or "'full_name'" not in public
