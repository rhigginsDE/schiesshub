"""Gleichstandsfelder für den DSB-Katalog: Serien für `letzte_serie_rueckwaerts`
(`gleichstand_serie`, SpO 0.12.1 Nr. 1 gegen 3.9.1.2), Stechen beim Höchstergebnis
(`stechen_bei_hoechstergebnis`, SpO 9.4.3) und Kette je Platz (`gleichstand_bis_platz`,
`gleichstand_danach`, SpO 9.4.1).

Handgerechnete Beispiele; die Definitionen sind eigene Testdaten, keine Katalogkopie.
"""

from typing import Any

import pytest

from app.modules.ergebnisse import begriffe
from app.scoring import DefinitionError, compute, describe_form, load_definition, rank_key
from app.scoring.tiebreak import criterion_values
from tests.scoring.test_dsb_fields import DSB_TIES, ranked, raw_shots, raw_sums, ring_definition

HITS = {"ringwerte": [1, 0]}


def _blocks(definition: dict, raw: dict, mode: str = "shot") -> list[int | None]:
    defn = load_definition(definition)
    return criterion_values(defn, compute(definition, mode, raw), "letzte_serie_rueckwaerts")


def _hits(*counts: int) -> dict:
    """Serien zu 5 Schuss mit so vielen Treffern (Treffer zuerst)."""
    return raw_shots(*([1] * n + [0] * (5 - n) for n in counts))


# --- `gleichstand_serie` (SpO 0.12.1 Nr. 1, 3.9.1.2) ------------------------------------


def _five_shot_hits(**scoring: Any) -> dict:
    """Treffer/Fehler in Serien zu 5 Schuss (wie 10 m mehrschüssige Luftpistole)."""
    return ring_definition(
        serien=4, schuss=5, section=HITS, gleichstand=["letzte_serie_rueckwaerts"], **scoring
    )


def test_hits_only_without_field_keeps_series_as_defined() -> None:
    # Verhalten vor dem Feld: reine Trefferzählung → je Serie, vom Ende her.
    assert _blocks(_five_shot_hits(), _hits(5, 3, 4, 5)) == [500, 400, 300, 500]


def test_ten_shot_blocks_for_hits_only_when_set() -> None:
    # SpO 0.12.1 Nr. 1: 10-Schuss-Serien, auch bei Treffer/Fehler und 5er-Serien.
    definition = _five_shot_hits(gleichstand_serie="zehn_schuss")
    assert load_definition(definition).tie_series_as_defined is False
    assert _blocks(definition, _hits(5, 3, 4, 5)) == [900, 800]


def test_ten_shot_blocks_change_the_ranking() -> None:
    # Beide 17 Treffer. Je Serie: letzte Serie 5 > 4 → a vorn. In 10er-Blöcken: 9 = 9, 8 = 8.
    raws = {"a": _hits(5, 3, 4, 5), "b": _hits(4, 4, 5, 4)}
    per_series = ranked(_five_shot_hits(), raws)
    assert (per_series["a"].place, per_series["b"].place) == (1, 2)
    assert per_series["a"].tie_reason == "resolved"
    blocks = ranked(_five_shot_hits(gleichstand_serie="zehn_schuss"), raws)
    assert (blocks["a"].place, blocks["b"].place) == (1, 1)
    assert blocks["a"].tied
    assert blocks["a"].tie_reason is None


def test_ten_shot_blocks_for_hits_only_from_series_sums_in_pairs() -> None:
    definition = _five_shot_hits(gleichstand_serie="zehn_schuss")
    raw = raw_sums(*({"sum": value} for value in (5, 3, 4, 5)))
    assert _blocks(definition, raw, "series") == [900, 800]
    assert describe_form(definition, "series").notes == []


def test_series_as_defined_explicitly_for_shotgun() -> None:
    # Wurfscheibe (SpO 3.9.1.2): letzte Serie zu 25 Scheiben, dann rückwärts.
    definition = ring_definition(
        serien=2,
        schuss=25,
        section=HITS,
        gleichstand=["letzte_serie_rueckwaerts"],
        gleichstand_serie="serie",
    )
    raw = raw_shots([1] * 20 + [0] * 5, [1] * 24 + [0])
    assert _blocks(definition, raw) == [2400, 2000]


def test_series_as_defined_also_for_rings() -> None:
    definition = ring_definition(
        serien=3, schuss=4, gleichstand=["letzte_serie_rueckwaerts"], gleichstand_serie="serie"
    )
    raw = raw_shots([1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 10, 9])
    assert _blocks(definition, raw) == [3800, 2600, 1000]


def test_rings_default_is_unchanged() -> None:
    definition = ring_definition(serien=3, schuss=4, gleichstand=["letzte_serie_rueckwaerts"])
    explicit = ring_definition(
        serien=3,
        schuss=4,
        gleichstand=["letzte_serie_rueckwaerts"],
        gleichstand_serie="zehn_schuss",
    )
    raw = raw_shots([1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 10, 9])
    assert _blocks(definition, raw) == _blocks(explicit, raw) == [7100, 300]


def test_tie_series_value_is_checked() -> None:
    with pytest.raises(DefinitionError) as error:
        load_definition(_five_shot_hits(gleichstand_serie="fuenf_schuss"))
    assert any("gleichstand_serie" in p for p in error.value.problems)


def test_short_text_follows_the_series_rule() -> None:
    # „letzte Serie“ nur, wenn Serien wie definiert verglichen werden.
    hits_blocks = load_definition(_five_shot_hits(gleichstand_serie="zehn_schuss"))
    assert hits_blocks.hits_only
    assert not hits_blocks.tie_series_as_defined
    note = begriffe.tie_note(
        "resolved",
        "letzte_serie_rueckwaerts",
        1,
        "Treffergleichheit",
        hits_only=hits_blocks.tie_series_as_defined,
    )
    assert note == "Treffergleichheit, entschieden nach: letzte Zehnerserie"


# --- `stechen_bei_hoechstergebnis` (SpO 9.4.3) ------------------------------------------


def _max_shootoff(**scoring: Any) -> dict:
    return ring_definition(
        serien=2, schuss=2, gleichstand=DSB_TIES, stechen_bei_hoechstergebnis=True, **scoring
    )


MAX_RAWS = {
    "a": raw_shots(["X", 10], [10, 10]),  # 40 = Höchstergebnis, ein Innenzehner
    "b": raw_shots([10, 10], [10, 10]),  # 40, ohne Innenzehner
    "c": raw_shots(["X", 9], [10, 10]),  # 39: Kette trennt weiter (Innenzehner)
    "d": raw_shots([10, 10], [9, 10]),  # 39
}


def test_max_score_shootoff_shares_the_place_with_shootoff_note() -> None:
    places = ranked(_max_shootoff(), MAX_RAWS)
    assert [places[i].place for i in "abcd"] == [1, 1, 3, 4]
    for ident in "ab":
        placement = places[ident]
        assert placement.tied
        assert placement.tie_reason == "max_score_shootoff"
        assert placement.tie_unresolved
        assert placement.needs_shootoff
        assert placement.tie_criterion is None
        assert placement.tie_note == "Höchstergebnis auf Platz 1: Stechen"
    # Unter dem Höchstergebnis gilt die Kette wie bisher.
    assert places["c"].tie_reason == "resolved"
    assert places["c"].tie_criterion == "innenzehner"


def test_without_flag_the_chain_separates_the_max_score() -> None:
    places = ranked(ring_definition(serien=2, schuss=2, gleichstand=DSB_TIES), MAX_RAWS)
    assert (places["a"].place, places["b"].place) == (1, 2)


def test_single_max_score_is_not_a_tie() -> None:
    places = ranked(_max_shootoff(), {"a": MAX_RAWS["a"], "c": MAX_RAWS["c"]})
    assert places["a"].place == 1
    assert not places["a"].tied
    assert places["a"].tie_reason is None
    assert not places["a"].needs_shootoff


def test_max_score_shootoff_comes_before_shootoff_until_place() -> None:
    places = ranked(_max_shootoff(stechen_bis_platz=3), MAX_RAWS)
    assert places["a"].tie_reason == "max_score_shootoff"
    assert places["c"].place == places["d"].place == 3
    assert places["c"].tie_reason == "shootoff"


def test_max_score_rules_exclude_each_other() -> None:
    with pytest.raises(DefinitionError) as error:
        load_definition(_max_shootoff(hoechstergebnis_gleicher_rang=True))
    assert any("schließen sich aus" in p for p in error.value.problems)
    # `false` beim anderen Feld ist erlaubt.
    load_definition(_max_shootoff(hoechstergebnis_gleicher_rang=False))


def test_max_score_shootoff_only_for_rings_model() -> None:
    definition = {
        "variant": {
            "id": "v",
            "name": "V",
            "abschnitte": [
                {"id": "a", "name": "A", "serien": 1, "schuss_je_serie": 5, "sollzeit_s": 10}
            ],
        },
        "scoring": {
            "modell": "ringe_mit_zeitabzug",
            "rangfolge": "absteigend",
            "abzug_je_voller_sekunde_ueber_sollzeit": 1,
            "stechen_bei_hoechstergebnis": True,
        },
    }
    definition["variant"]["abschnitte"][0]["zeit_wird_gemessen"] = True
    with pytest.raises(DefinitionError) as error:
        load_definition(definition)
    assert any("stechen_bei_hoechstergebnis" in p for p in error.value.problems)


def test_max_score_shootoff_in_form_and_terms() -> None:
    form = describe_form(_max_shootoff(), "shot")
    assert form.shootoff_at_max_score
    assert any(
        item.kind == "shootoff" and item.text.startswith("Höchstergebnis (40 Ringe)")
        for item in form.note_items
    )
    assert not describe_form(ring_definition(), "shot").shootoff_at_max_score
    note = begriffe.tie_note("max_score_shootoff", None, 1, "Ergebnisgleichheit")
    assert note == "Höchstergebnis auf Platz 1: Stechen"


# --- `gleichstand_bis_platz` / `gleichstand_danach` (SpO 9.4.1) -------------------------

FULL_RINGS_TOP = [*DSB_TIES, "zehntel_gesamt"]


def _by_place(**scoring: Any) -> dict:
    """Ganze Ringe wie Auflage: bis Platz 2 mit Zehnteln als Nr. 4, danach ohne."""
    return ring_definition(
        serien=2,
        schuss=2,
        gleichstand=FULL_RINGS_TOP,
        gleichstand_bis_platz=2,
        gleichstand_danach=DSB_TIES,
        **scoring,
    )


def test_chain_after_place_ends_with_same_place() -> None:
    same_top = raw_shots([10, 10], [10, 9])  # 39
    same_low = raw_shots([9, 9], [9, 9])  # 36
    raws = {"a": same_top, "b": same_top, "c": same_low, "d": same_low}
    places = ranked(_by_place(), raws)
    assert [places[i].place for i in "abcd"] == [1, 1, 3, 3]
    # Plätze 1–2: Kette bis zu den Zehnteln, die die Wertung nicht erfasst → manuell.
    assert places["a"].tie_reason == "manual"
    assert places["a"].tie_criterion == "zehntel_gesamt"
    assert places["a"].tie_unresolved
    # Ab Platz 3: Kette ohne Zehntel, danach gleicher Rang (entschieden).
    assert places["c"].tied
    assert places["c"].tie_reason is None
    assert not places["c"].tie_unresolved


def test_without_place_limit_every_place_ends_manual() -> None:
    same_low = raw_shots([9, 9], [9, 9])
    definition = ring_definition(serien=2, schuss=2, gleichstand=FULL_RINGS_TOP)
    places = ranked(definition, {"x": raw_shots([10, 10], [10, 10]), "c": same_low, "d": same_low})
    assert places["c"].tie_reason == "manual"


def test_chain_after_place_still_separates() -> None:
    raws = {
        "a": raw_shots([10, 10], [10, 10]),
        "b": raw_shots([10, 10], [10, 9]),
        "c": raw_shots([10, 10], [10, 8]),  # 38, drei Zehner (ein Block: Serie gleich)
        "d": raw_shots([10, 10], [9, 9]),  # 38, zwei Zehner
    }
    places = ranked(_by_place(), raws)
    assert [places[i].place for i in "abcd"] == [1, 2, 3, 4]
    assert places["c"].tie_reason == "resolved"
    assert places["c"].tie_criterion == "zehner"


def test_subset_chain_keeps_the_key() -> None:
    # Die Kette danach steckt in der ersten: Schlüssel wie ohne die Felder.
    plain = ring_definition(serien=2, schuss=2, gleichstand=FULL_RINGS_TOP)
    raw = raw_shots(["X", 10], [9, 8])
    key = rank_key(_by_place(), compute(_by_place(), "shot", raw))
    assert key == rank_key(plain, compute(plain, "shot", raw))


def test_tie_starting_on_the_last_place_of_the_range_uses_the_first_chain() -> None:
    # Annahme wie beim Stechen: Maßgeblich ist der Platz, auf dem die Gleichen beginnen.
    same = raw_shots([9, 9], [9, 9])
    places = ranked(_by_place(), {"x": raw_shots([10, 10], [10, 10]), "a": same, "b": same})
    assert places["a"].place == places["b"].place == 2
    assert places["a"].tie_reason == "manual"
    assert places["a"].tie_criterion == "zehntel_gesamt"


def test_chain_after_with_more_criteria_extends_the_key() -> None:
    # Zehntelwertung: bis Platz 1 nur die letzte Zehnerserie, danach auch Zehner usw.
    definition = ring_definition(
        serien=1,
        schuss=2,
        zehntelwertung=True,
        gleichstand=["letzte_serie_rueckwaerts"],
        gleichstand_bis_platz=1,
        gleichstand_danach=DSB_TIES,
    )
    raws = {
        "a": raw_shots([10.1, 9.9]),  # 20,0; ein Zehner
        "b": raw_shots([10.0, 10.0]),  # 20,0; zwei Zehner
        "c": raw_shots([10.0, 9.0]),  # 19,0; ein Zehner
        "d": raw_shots([9.5, 9.5]),  # 19,0; kein Zehner
    }
    places = ranked(definition, raws)
    # Platz 1: gleiche letzte Serie → gleicher Platz.
    assert places["a"].place == places["b"].place == 1
    assert places["a"].tie_reason is None
    # Ab Platz 2: Zehner trennen.
    assert (places["c"].place, places["d"].place) == (3, 4)
    assert places["c"].tie_criterion == "zehner"
    key = rank_key(definition, compute(definition, "shot", raws["a"]))
    assert len(key) == 1 + 1 + 1 + 9 + 1  # Ergebnis, Serie, Zehner, Neuner abwärts, Innenzehner
    # Innenzehner gibt es bei Zehntelwertung nicht → ab dort manuell.
    same = ranked(definition, {"x": raw_shots([10.9, 10.9]), "c": raws["c"], "e": raws["c"]})
    assert same["c"].tie_reason == "manual"
    assert same["c"].tie_criterion == "innenzehner"


def test_empty_chain_after_means_same_place() -> None:
    definition = ring_definition(
        serien=2, schuss=2, gleichstand=DSB_TIES, gleichstand_bis_platz=1, gleichstand_danach=[]
    )
    raws = {
        "x": raw_shots([10, 10], [10, 10]),
        "a": raw_shots([10, 10], [9, 9]),
        "b": raw_shots([9, 9], [10, 10]),
    }
    places = ranked(definition, raws)
    assert places["a"].place == places["b"].place == 2
    assert places["a"].tie_reason is None


def test_unknown_criterion_after_is_manual() -> None:
    definition = ring_definition(
        serien=2,
        schuss=2,
        gleichstand=DSB_TIES,
        gleichstand_bis_platz=1,
        gleichstand_danach=["letzte_serie_rueckwaerts", "abstand_zum_rand"],
    )
    same = raw_shots([9, 9], [9, 9])
    places = ranked(definition, {"x": raw_shots([10, 10], [10, 10]), "a": same, "b": same})
    assert places["a"].tie_reason == "manual"
    assert places["a"].tie_criterion == "abstand_zum_rand"
    form = describe_form(definition, "shot")
    assert form.tie_breakers_until_place == 1
    assert form.tie_breakers_after == ["letzte_serie_rueckwaerts", "abstand_zum_rand"]
    assert form.tie_breakers_after_evaluated == ["letzte_serie_rueckwaerts"]
    assert form.tie_breakers_after_manual_from == "abstand_zum_rand"
    assert any(
        note.startswith("Gleichstand ab Platz 2 ab „abstand zum rand“") for note in form.notes
    )


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"gleichstand_bis_platz": 6}, "nur zusammen"),
        ({"gleichstand_danach": DSB_TIES}, "nur zusammen"),
        ({"gleichstand_bis_platz": 0, "gleichstand_danach": []}, "gleichstand_bis_platz"),
        (
            {"gleichstand_bis_platz": 6, "gleichstand_danach": ["zehner", "zehner"]},
            "mehrfach",
        ),
        (
            {"gleichstand_bis_platz": 6, "gleichstand_danach": ["parcours_zeit"]},
            "nicht anwendbar",
        ),
        ({"gleichstand_bis_platz": 6, "gleichstand_danach": ["Zehner"]}, "Kleinbuchstaben"),
    ],
)
def test_chain_after_fields_are_checked(change: dict, fragment: str) -> None:
    definition = ring_definition(gleichstand=DSB_TIES, **change)
    with pytest.raises(DefinitionError) as error:
        load_definition(definition)
    assert any(fragment in p for p in error.value.problems), error.value.problems
