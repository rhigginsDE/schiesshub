"""Wörter je Verband in der Rangliste, Höchstergebnis, Einheit „Treffer“ und die Bemerkung zum
Abbruch (`abort_remark`, nur für die Bedienung)."""

import uuid
from typing import Any

from app.core.begriffe import begriffe_fuer
from app.modules.ergebnisse import abort_remarks, begriffe
from tests.ergebnisse.conftest import Api, make_setup, precision_definition, shots

DSB_LG = "1.10"  # Luftgewehr (DSB), erste Variante: 60 Schuss in 6 × 10, Zehntelwertung


# --- reine Wortwahl -------------------------------------------------------------------


def test_abort_label_per_federation() -> None:
    bds, dsb, standard = begriffe_fuer("bds"), begriffe_fuer("dsb"), begriffe_fuer(None)
    assert begriffe.abort_label("dnf", bds) == "Abbruch (AB)"
    assert begriffe.abort_label("dnf", standard) == "Abbruch (AB)"
    # DSB: keine Kurzform in der SpO → nur das Wort des Begriffssatzes
    assert begriffe.abort_label("dnf", dsb) == dsb.abbruch
    assert "(" not in (begriffe.abort_label("dnf", dsb) or "")
    assert begriffe.abort_label("dns", dsb) == "nicht angetreten"
    assert begriffe.abort_label("dsq", bds) == "disqualifiziert"
    assert begriffe.abort_label("xyz", bds) == "abgebrochen"
    assert begriffe.abort_label(None, bds) is None


def test_tie_word_per_federation() -> None:
    bds, dsb, standard = begriffe_fuer("bds"), begriffe_fuer("dsb"), begriffe_fuer(None)
    assert begriffe.tie_word("ringe", (), bds) == "Ringgleichheit"
    assert begriffe.tie_word("ringe", (), standard) == "Ringgleichheit"
    assert begriffe.tie_word("ringe_mit_zeitabzug", ("parcours_zeit",), bds) == (
        "Treffergleichheit"
    )
    assert begriffe.tie_word("ringe", (), dsb) == "Ergebnisgleichheit"
    assert begriffe.tie_word("ringe", (), dsb, hits_only=True) == "Treffergleichheit"
    assert begriffe.tie_word("zeit_plus_zuschlaege", (), bds) == "gleiches Ergebnis"


def test_document_terms_common_or_standard() -> None:
    assert begriffe.document_terms(["dsb", "DSB "]) == begriffe_fuer("dsb")
    assert begriffe.document_terms(["dsb", None]) == begriffe_fuer("dsb")
    assert begriffe.document_terms(["dsb", "bds"]) == begriffe_fuer(None)
    assert begriffe.document_terms([None]) == begriffe_fuer(None)


def test_tie_notes_use_plain_criterion_text() -> None:
    note = begriffe.tie_note("manual", "trefferfolge_rueckwaerts", 1, "Treffergleichheit")
    assert note == (
        "Treffergleichheit: nach Sportordnung manuell entscheiden (nächstes Kriterium: "
        "Trefferfolge ab der letzten Scheibe rückwärts bis zum ersten Fehler)"
    )
    assert "„Anzahl der Zehner“" in (begriffe.tie_note("missing_data", "zehner", 1, "X") or "")
    assert begriffe.tie_note("max_score", None, 1, "X") == "Höchstergebnis: gleicher Platz"


# --- Rangliste über die API -------------------------------------------------------------


def _row(ranking: dict[str, Any], sid: str) -> dict[str, Any]:
    return next(row for g in ranking["groups"] for row in g["rows"] if row["start_id"] == sid)


async def test_dsb_ranking_uses_dsb_words_and_remark(api: Api) -> None:
    setup = await make_setup(
        api, catalog_federation="dsb", catalog_code=DSB_LG, capture_mode="series"
    )
    tid, cid = setup.tid, setup.cid
    sids = []
    for _ in range(3):
        entry = await api.entry(tid, setup.class_id)
        sids += await api.starts(tid, entry, cid)
    sums = {"sections": {"wertung": {"series": [{"sum": "100.5"} for _ in range(6)]}}}
    await api.shoot(tid, sids[0], sums)
    await api.shoot(tid, sids[1], sums)
    await api.call(tid, sids[2])
    await api.ok(
        "POST",
        f"/tournaments/{tid}/starts/{sids[2]}/abort",
        json={"abort_reason": "dns", "note": "Krank gemeldet"},
    )

    ranking = await api.ranking(tid, cid)
    assert ranking["federation"] == "dsb"
    assert ranking["result_list_title"] == "Ergebnisliste"
    assert ranking["tie_word"] == "Ergebnisgleichheit"
    first = _row(ranking, sids[0])
    assert (first["place"], first["tie_reason"], first["tie_criterion"]) == (
        1,
        "missing_data",
        "zehner",
    )
    # letzte_serie_rueckwaerts ließ sich aus den 10er-Seriensummen rechnen; dann fehlen Zehner.
    assert first["tie_note"].startswith("Ergebnisgleichheit nicht auflösbar: Angaben für „Anzahl")
    assert first["abort_remark"] is None
    aborted = _row(ranking, sids[2])
    assert aborted["abort_label"] == "nicht angetreten"
    assert aborted["abort_remark"] == "Krank gemeldet"

    form = await api.ok("GET", f"{api.start_path(tid, sids[2])}/form")
    assert form["current"]["abort_remark"] == "Krank gemeldet"


async def test_bds_like_own_competition_keeps_standard_words(api: Api) -> None:
    setup = await make_setup(api, definition=precision_definition(), capture_mode="shot")
    tid, cid = setup.tid, setup.cid
    entry = await api.entry(tid, setup.class_id)
    (sid,) = await api.starts(tid, entry, cid)
    await api.call(tid, sid)
    await api.ok(
        "POST",
        f"{api.start_path(tid, sid)}/result/abort",
        json={"abort_reason": "dnf"},
    )
    ranking = await api.ranking(tid, cid)
    assert ranking["federation"] is None
    assert ranking["tie_word"] == "Ringgleichheit"
    row = _row(ranking, sid)
    assert row["abort_label"] == "Abbruch (AB)"
    assert row["abort_remark"] is None  # ohne Bemerkung


async def test_max_score_place_in_ranking(api: Api) -> None:
    definition = precision_definition(series=1)
    definition["scoring"]["hoechstergebnis_gleicher_rang"] = True
    setup = await make_setup(api, definition=definition, capture_mode="shot")
    tid, cid = setup.tid, setup.cid
    sids = []
    for _ in range(2):
        entry = await api.entry(tid, setup.class_id)
        sids += await api.starts(tid, entry, cid)
    await api.shoot(tid, sids[0], shots(["X", "X", 10, 10, 10]))
    await api.shoot(tid, sids[1], shots([10, 10, 10, 10, 10]))
    ranking = await api.ranking(tid, cid)
    rows = [_row(ranking, sid) for sid in sids]
    assert [row["place"] for row in rows] == [1, 1]
    assert all(row["tie_reason"] == "max_score" for row in rows)
    assert not any(row["tie_unresolved"] for row in rows)
    assert rows[0]["tie_note"] == "Höchstergebnis: gleicher Platz"


async def test_abort_remarks_reads_latest_aborted_event(api: Api, precision: Any) -> None:
    tid, cid = precision.tid, precision.cid
    entry = await api.entry(tid, precision.class_id)
    (sid,) = await api.starts(tid, entry, cid)
    await api.call(tid, sid)
    await api.ok(
        "POST",
        f"{api.start_path(tid, sid)}/result/abort",
        json={"abort_reason": "dnf", "reason": "Waffendefekt"},
    )
    async with api.app.state.session_factory() as session:
        found = await abort_remarks(session, [uuid.UUID(sid), uuid.uuid4()])
        assert await abort_remarks(session, []) == {}
    assert found == {uuid.UUID(sid): "Waffendefekt"}
