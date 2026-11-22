"""Löschen im Turnier, wenn Anzeigen darauf verweisen: 409 mit dem Namen der Anzeige."""

from tests.anzeige.conftest import Api


async def test_range_competition_and_class_in_scenes_block_deletion(api: Api) -> None:
    tid = await api.tournament()
    range_id = await api.range(tid)
    spare = await api.range(tid, name="Stand 2")
    class_id = await api.klass(tid)
    cid = (await api.competition(tid, range_id))["id"]
    display = await api.display(
        "Stand-Bildschirm",
        config={
            "scenes": [
                {"id": "stand", "kind": "range", "range_id": range_id},
                {"id": "live", "kind": "live_ranking", "competition_ids": [cid]},
                {"id": "sieger", "kind": "winners", "class_ids": [class_id]},
                {"id": "starts", "kind": "startlist", "range_ids": [spare]},
            ]
        },
    )

    blocked = await api.fail("DELETE", f"/tournaments/{tid}/ranges/{range_id}", 409)
    assert blocked["detail"] == (
        "Der Stand wird auf der Anzeige „Stand-Bildschirm“ gezeigt. "
        "Bitte die Szene dort zuerst anpassen."
    )
    blocked = await api.fail("DELETE", f"/tournaments/{tid}/ranges/{spare}", 409)
    assert "Stand-Bildschirm" in blocked["detail"]
    blocked = await api.fail("DELETE", f"/tournaments/{tid}/competitions/{cid}", 409)
    assert blocked["detail"].startswith("Der Wettbewerb wird auf der Anzeige „Stand-Bildschirm“")
    blocked = await api.fail("DELETE", f"/tournaments/{tid}/classes/{class_id}", 409)
    assert blocked["detail"].startswith("Die Klasse wird auf der Anzeige")
    # Auch das ganze Turnier nicht, solange Szenen auf seine Teile zeigen.
    blocked = await api.fail("DELETE", f"/tournaments/{tid}", 409)
    assert "Stand-Bildschirm" in blocked["detail"]

    await api.ok("PUT", f"/displays/{display['id']}/config", json={"scenes": []})
    await api.ok("DELETE", f"/tournaments/{tid}/ranges/{spare}", 204)
    await api.ok("DELETE", f"/tournaments/{tid}/competitions/{cid}", 204)
    await api.ok("DELETE", f"/tournaments/{tid}/classes/{class_id}", 204)
    await api.ok("DELETE", f"/tournaments/{tid}/ranges/{range_id}", 204)


async def test_pinned_tournament_blocks_deletion_until_set_to_automatic(api: Api) -> None:
    tid = await api.tournament()
    first = await api.display("Saal", tournament_id=tid)
    second = await api.display("Flur", tournament_id=tid)

    blocked = await api.fail("DELETE", f"/tournaments/{tid}", 409)
    assert blocked["detail"] == (
        "Das Turnier wird auf den Anzeigen „Saal“ und „Flur“ gezeigt. Bitte dort zuerst ein "
        "anderes Turnier oder „automatisch“ wählen und die Szenen anpassen."
    )

    for display in (first, second):
        await api.ok("PATCH", f"/displays/{display['id']}", json={"tournament_id": None})
    await api.ok("DELETE", f"/tournaments/{tid}", 204)
    assert {item["tournament_id"] for item in await api.displays()} == {None}


async def test_displays_without_references_do_not_block(api: Api) -> None:
    tid = await api.tournament()
    range_id = await api.range(tid)
    # Die Hauptanzeige (automatisch, ohne Filter) verweist auf nichts.
    await api.ok("DELETE", f"/tournaments/{tid}/ranges/{range_id}", 204)
    await api.ok("DELETE", f"/tournaments/{tid}", 204)
