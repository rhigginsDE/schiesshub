"""Felder für den DSB-Katalog: Zehntelwertung, Stechen, Gleichstandsketten, Ringwerte über 10,
Zeiten und Anschläge, die nur durchgereicht werden.

Handgerechnete Beispiele; die Definitionen sind eigene Testdaten, keine Katalogkopie.
"""

import copy
from decimal import Decimal
from typing import Any

import pytest

from app.scoring import (
    ComputedResult,
    Contender,
    DefinitionError,
    InvalidRawError,
    compute,
    describe_form,
    load_definition,
    rank,
    rank_key,
    tie_rules,
    validate_raw,
)
from tests.scoring.support import series_of

DSB_TIES = ["letzte_serie_rueckwaerts", "zehner", "neuner_abwaerts", "innenzehner"]


def ring_definition(
    *,
    serien: int = 2,
    schuss: int = 3,
    gleichstand: list[str] | None = None,
    section: dict[str, Any] | None = None,
    variant: dict[str, Any] | None = None,
    **scoring: Any,
) -> dict:
    abschnitt = {
        "id": "wk",
        "name": "Wettkampf",
        "serien": serien,
        "schuss_je_serie": schuss,
        **(section or {}),
    }
    data: dict[str, Any] = {
        "variant": {
            "id": "standard",
            "name": "Standard",
            "abschnitte": [abschnitt],
            **(variant or {}),
        },
        "scoring": {"modell": "ringe", "rangfolge": "absteigend", **scoring},
    }
    if gleichstand is not None:
        data["scoring"]["gleichstand"] = gleichstand
    return data


def tenths(**kwargs: Any) -> dict:
    return ring_definition(zehntelwertung=True, **kwargs)


def raw_shots(*series: list) -> dict:
    return series_of(*({"shots": list(s)} for s in series), section="wk")


def raw_sums(*series: dict) -> dict:
    return series_of(*series, section="wk")


def messages(definition: dict, raw: dict, mode: str = "shot", partial: bool = True) -> list[str]:
    return [issue.message for issue in validate_raw(definition, mode, raw, partial=partial)]


def contender(definition: dict, raw: dict, ident: str, mode: str = "shot") -> Contender:
    result = compute(definition, mode, raw)
    return Contender(id=ident, key=rank_key(definition, result), complete=result.complete)


def ranked(definition: dict, raws: dict[str, dict], mode: str = "shot") -> dict[str, Any]:
    contenders = [contender(definition, raw, ident, mode) for ident, raw in raws.items()]
    return {p.id: p for p in rank(contenders, rules=tie_rules(definition))}


# --- Zehntelwertung: Einzelschuss --------------------------------------------------


def test_tenths_single_shots_are_summed_exactly() -> None:
    result = compute(tenths(), "shot", raw_shots([10.9, "9,8", "10.0"], [0, 1.0, Decimal("7.3")]))
    assert result.score == Decimal("39.0")
    assert result.score_text == "39,0 Ringe"
    assert result.rings == Decimal("39.0")
    assert result.decimals == 1
    assert [s.rings for s in result.sections[0].series] == [Decimal("30.7"), Decimal("8.3")]
    # Zehner: Werte ab 10,0; Innenzehner gibt es bei Zehntelwertung nicht.
    assert (result.tens, result.inner_tens) == (2, None)
    assert result.ring_counts is not None
    assert (result.ring_counts[10], result.ring_counts[9], result.ring_counts[0]) == (2, 1, 1)
    assert result.steps[0] == "Serie 1: 10,9 + 9,8 + 10,0 = 30,7 Ringe"
    assert result.steps[-1] == "Ergebnis: 39,0 Ringe"
    assert result.complete


def test_tenths_result_survives_json_round_trip() -> None:
    definition = tenths()
    result = compute(definition, "shot", raw_shots([10.9, 9.8, 10.0], [0, 1.0, 7.3]))
    stored = ComputedResult.model_validate(result.model_dump(mode="json"))
    assert stored.score == Decimal("39.0")
    assert stored.sections[0].series[0].rings == Decimal("30.7")
    assert rank_key(definition, stored) == rank_key(definition, result)


@pytest.mark.parametrize("value", [10.9, "10,9", "10.9", 1.0, "1,0", 0, "0", 10, "5"])
def test_tenths_boundaries_valid(value: object) -> None:
    assert messages(tenths(serien=1, schuss=1), raw_shots([value])) == []


@pytest.mark.parametrize(
    "value", [0.9, "0,9", 11.0, "11,0", 10.95, "10,55", "9,80", -1, "X", True, "", "zehn", None]
)
def test_tenths_boundaries_invalid(value: object) -> None:
    found = messages(tenths(serien=1, schuss=1), raw_shots([value]))
    assert len(found) == 1
    assert "Bei Zehntelwertung sind Werte von 1,0 bis 10,9 oder 0 erlaubt." in found[0]
    assert found[0].startswith("Serie 1, Schuss 1: ")


def test_tenths_two_decimals_name_the_problem() -> None:
    (message,) = messages(tenths(serien=1, schuss=1), raw_shots(["9,85"]))
    assert "höchstens eine Nachkommastelle" in message


# --- Zehntelwertung: Seriensumme ----------------------------------------------------


def test_tenths_series_sum() -> None:
    definition = tenths(gleichstand=["zehner"])
    raw = raw_sums({"sum": "30,7", "tens": 2}, {"sum": 8.3})
    assert messages(definition, raw, "series", partial=False) == []
    result = compute(definition, "series", raw)
    assert result.score == Decimal("39.0")
    assert result.score_text == "39,0 Ringe"
    assert result.steps[0] == "Serie 1: Seriensumme 30,7 Ringe, 2 Zehner"
    assert result.tens is None  # Serie 2 ohne Zehner
    assert result.ring_counts is None


@pytest.mark.parametrize(
    ("series", "fragment"),
    [
        ({"sum": "32,8"}, "Seriensumme mit höchstens einer Nachkommastelle von 0 bis 32,7"),
        ({"sum": "10,25"}, "Seriensumme mit höchstens einer Nachkommastelle von 0 bis 32,7"),
        ({"sum": "0,5"}, "Seriensumme 0 oder mindestens 1,0"),
        ({"sum": "19,9", "tens": 2}, "2 Zehner ergeben mindestens 20,0"),
        ({"sum": "31,8", "tens": 2}, "mit 2 Zehnern sind höchstens 31,7 Ringe möglich"),
        (
            {"sum": "30,0", "tens": 2, "inner_tens": 1},
            "Bei Zehntelwertung gibt es keine Innenzehner",
        ),
    ],
)
def test_tenths_series_sum_errors(series: dict, fragment: str) -> None:
    found = messages(tenths(serien=1), raw_sums(series), "series")
    assert any(fragment in message for message in found), found


def test_tenths_series_sum_maximum_is_valid() -> None:
    assert messages(tenths(serien=1), raw_sums({"sum": "32,7", "tens": 3}), "series") == []


def test_tenths_definition_rules() -> None:
    with pytest.raises(DefinitionError, match="ringwerte passt nicht zu zehntelwertung"):
        load_definition(tenths(section={"ringwerte": [10, 9, 0]}))
    speed = ring_definition(zehntelwertung=True, section={"zeit_wird_gemessen": True})
    speed["scoring"]["modell"] = "ringe_minus_zeit"
    with pytest.raises(DefinitionError, match="zehntelwertung: wird vom Modell „ringe_minus_zeit“"):
        load_definition(speed)
    # false ist die Grundeinstellung und bei jedem Modell erlaubt.
    speed["scoring"]["zehntelwertung"] = False
    load_definition(speed)


def test_tenths_form() -> None:
    form = describe_form(tenths(), "shot").model_dump(mode="json")
    shots = form["sections"][0]["series"][0]["fields"][0]
    assert shots["key"] == "shots"
    assert shots["allowed_values"] is None
    assert (shots["decimals"], shots["step"], shots["value_min"], shots["value_max"]) == (
        1,
        "0.1",
        "1.0",
        "10.9",
    )
    assert shots["zero_allowed"] is True
    assert form["ring_decimals"] == 1
    assert form["max_rings"] == "65.4"
    assert form["sections"][0]["series"][0]["max_rings"] == "32.7"

    series_form = describe_form(tenths(gleichstand=DSB_TIES), "series").model_dump(mode="json")
    fields = {f["key"]: f for f in series_form["sections"][0]["series"][0]["fields"]}
    assert fields["sum"]["kind"] == "decimal"
    assert (fields["sum"]["decimals"], fields["sum"]["value_max"]) == (1, "32.7")
    assert "tens" in fields
    assert "inner_tens" not in fields


def test_integer_form_is_unchanged_by_new_fields() -> None:
    form = describe_form(ring_definition(), "shot").model_dump(mode="json")
    shots = form["sections"][0]["series"][0]["fields"][0]
    assert shots["allowed_values"] == ["X", 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
    assert shots["decimals"] is None
    assert shots["step"] is None
    assert form["ring_decimals"] == 0
    assert form["max_rings"] == 60


# --- Ringwerte über 10 (Bogen 3D) und Flinte ------------------------------------------


def test_ring_values_above_ten_for_3d() -> None:
    definition = ring_definition(
        serien=1,
        schuss=2,
        section={"ringwerte": [11, 10, 8, 5, 0]},
        gleichstand=["elfer", "zehner"],
    )
    assert messages(definition, raw_shots([11, 8])) == []
    found = messages(definition, raw_shots([9, 11]))
    assert found == ["Serie 1, Schuss 1: Ringwert 11, 10, 8, 5 oder 0, nicht 9"]
    assert messages(definition, raw_shots(["X", 11])) != []
    result = compute(definition, "shot", raw_shots([11, 10]))
    assert result.score == 21
    assert result.ring_counts is not None
    assert result.ring_counts[11] == 1
    assert (result.tens, result.inner_tens) == (1, 0)
    assert describe_form(definition, "series").sections[0].series[0].max_rings == 22

    a = raw_shots([11, 5])
    b = raw_shots([8, 8])
    c = raw_shots([10, 5])
    places = ranked(definition, {"a": a, "b": b, "c": c, "d": raw_shots([11, 5])})
    assert [places[i].place for i in "abcd"] == [1, 3, 4, 1]
    assert places["a"].tied
    assert not places["a"].tie_unresolved


def test_shotgun_hits() -> None:
    definition = ring_definition(
        serien=1, schuss=5, section={"ringwerte": [1, 0]}, gleichstand=["mehr_treffer"]
    )
    assert messages(definition, raw_shots([1, 0, 2, 1, 1])) == [
        "Serie 1, Schuss 3: Ringwert 1 oder 0, nicht 2"
    ]
    result = compute(definition, "shot", raw_shots([1, 0, 1, 1, 1]))
    assert (result.score, result.hits) == (4, 4)


# --- Gleichstand: DSB-Kette -----------------------------------------------------------


def test_dsb_chain_last_series_backwards() -> None:
    # SpO 0.12.1: letzte Zehnerserie, dann in 10-Schuss-Serien zurück – auch bei 5er-Serien
    # (Serie 3+4 sind der letzte Block, Serie 1+2 der vorletzte).
    definition = ring_definition(serien=4, schuss=5, gleichstand=DSB_TIES)
    raws = {
        # alle 180 Ringe
        "a": raw_shots([9] * 5, [9] * 5, [9] * 5, [9] * 5),  # Blöcke 90/90, 0 Zehner
        "b": raw_shots([10] * 5, [8] * 5, [10] * 5, [8] * 5),  # 90/90, 10 Zehner
        "c": raw_shots([8] * 5, [8] * 5, [10] * 5, [10] * 5),  # letzter Block 100
        "d": raw_shots([9] * 5, [9] * 5, [10, 10, 10, 8, 8], [9, 9, 9, 8, 9]),  # 90/90, 3 Zehner
    }
    places = ranked(definition, raws)
    # Nach Serien (5 Schuss) stünde a vor d vor b; nach 10er-Blöcken entscheiden die Zehner.
    assert [places[i].place for i in "cbda"] == [1, 2, 3, 4]
    assert not any(p.tied for p in places.values())


def test_dsb_chain_tens_nines_down_inner_tens() -> None:
    definition = ring_definition(serien=1, schuss=4, gleichstand=DSB_TIES)
    raws = {
        "zehner": raw_shots([10, 10, 8, 8]),  # 36, 2 Zehner
        "neuner": raw_shots([10, 9, 9, 8]),  # 36, 1 Zehner, 2 Neuner
        "innen": raw_shots(["X", 9, 9, 8]),  # wie „neuner“, aber Innenzehner
        "gleich": raw_shots([10, 9, 9, 8]),  # völlig gleich wie „neuner“
    }
    places = ranked(definition, raws)
    assert places["zehner"].place == 1
    assert places["innen"].place == 2
    assert (places["neuner"].place, places["gleich"].place) == (3, 3)
    assert places["neuner"].tied
    assert not places["neuner"].tie_unresolved  # alle Kriterien gerechnet, gleicher Rang
    assert places["neuner"].tie_reason is None


def test_dsb_chain_with_series_sum_stops_at_missing_data() -> None:
    definition = ring_definition(serien=2, schuss=2, gleichstand=DSB_TIES)
    raws = {
        "a": raw_sums({"sum": 18, "tens": 1}, {"sum": 19, "tens": 1}),
        "b": raw_sums({"sum": 18, "tens": 1}, {"sum": 19, "tens": 1}),
    }
    places = ranked(definition, raws, mode="series")
    assert (places["a"].place, places["b"].place) == (1, 1)
    assert places["a"].tie_unresolved
    assert places["a"].tie_reason == "missing_data"
    assert places["a"].tie_criterion == "neuner_abwaerts"
    assert "manuell" in (places["a"].tie_note or "")


def test_unknown_criterion_stops_with_manual_note() -> None:
    definition = ring_definition(
        serien=1, schuss=2, gleichstand=["zehner", "abstand_letzter_schuss", "neuner_abwaerts"]
    )
    load_definition(definition)  # unbekannte IDs werden angenommen
    rules = tie_rules(definition)
    assert rules.criteria == ["zehner"]
    assert rules.manual_from == "abstand_letzter_schuss"
    places = ranked(
        definition,
        {
            "a": raw_shots([10, 8]),
            "b": raw_shots([10, 8]),
            "c": raw_shots([9, 9]),  # 18, weniger Zehner: hinter a und b
            "d": raw_shots([9, 8]),
        },
    )
    assert [places[i].place for i in "abcd"] == [1, 1, 3, 4]
    assert places["a"].tie_unresolved
    assert places["a"].tie_reason == "manual"
    assert places["a"].tie_criterion == "abstand_letzter_schuss"
    # Hinweis im Klartext (`app/scoring/kriterien.yaml`), die ID steht in `tie_criterion`.
    assert places["a"].tie_note == (
        "Gleichstand nach Sportordnung manuell entscheiden (nächstes Kriterium: "
        "Abstand des letzten Schusses vom Zentrum)"
    )
    assert not places["c"].tied
    # c ist im Ergebnis gleich mit a und b, aber durch die Zehner getrennt.
    assert (places["c"].tie_reason, places["c"].tie_criterion) == ("resolved", "zehner")
    assert places["c"].tie_note == "Ringgleichheit, entschieden nach: Anzahl der Zehner"


def test_shots_backwards_and_second_half() -> None:
    definition = ring_definition(
        serien=2, schuss=2, gleichstand=["ergebnis_zweite_haelfte", "schuesse_rueckwaerts"]
    )
    places = ranked(
        definition,
        {
            "a": raw_shots([10, 8], [9, 9]),  # zweite Hälfte 18, letzter Schuss 9
            "b": raw_shots([9, 9], [10, 8]),  # zweite Hälfte 18, letzter Schuss 8
            "c": raw_shots([8, 9], [10, 9]),  # 36, zweite Hälfte 19
        },
    )
    assert [places[i].place for i in "cab"] == [1, 2, 3]
    # Seriensumme: Einzelschüsse fehlen → manuell, nicht geraten.
    sums = ranked(
        definition,
        {"a": raw_sums({"sum": 18}, {"sum": 18}), "b": raw_sums({"sum": 18}, {"sum": 18})},
        mode="series",
    )
    assert sums["a"].tie_reason == "missing_data"
    assert sums["a"].tie_criterion == "schuesse_rueckwaerts"


def test_tenths_total_and_tenths_tie_chain() -> None:
    definition = tenths(serien=1, schuss=2, gleichstand=["zehntel_gesamt", "zehner"])
    places = ranked(
        definition,
        {"a": raw_shots([10.1, 9.9]), "b": raw_shots([9.6, 10.4]), "c": raw_shots([10.0, 9.9])},
    )
    # 20,0 = 20,0 → Zehner 1 = 1 → gleicher Rang; 19,9 dahinter.
    assert [places[i].place for i in "abc"] == [1, 1, 3]
    assert places["a"].tie_reason is None
    # Ohne Zehntelwertung fehlen die Zehntel: manuell.
    whole = ring_definition(serien=1, schuss=2, gleichstand=["zehntel_gesamt"])
    places = ranked(whole, {"a": raw_shots([10, 9]), "b": raw_shots([9, 10])})
    assert places["a"].tie_reason == "missing_data"


def test_tenths_inner_tens_are_not_missing_but_manual() -> None:
    """Innenzehner gibt es bei Zehntelwertung nicht: Sie „fehlen“ nie (die Maske meldete sonst
    dauerhaft „Für einen Gleichstand fehlt: Anzahl Innenzehner“), ein Gleichstand bis dorthin
    ist manuell zu entscheiden."""
    definition = tenths(serien=1, schuss=2, gleichstand=["zehner", "innenzehner"])
    result = compute(definition, "shot", raw_shots([10.5, 9.5]))
    assert result.tie_breakers_missing == []
    assert tie_rules(definition).uncapturable == ["innenzehner"]
    places = ranked(definition, {"a": raw_shots([10.5, 9.5]), "b": raw_shots([9.5, 10.5])})
    assert [places[i].place for i in "ab"] == [1, 1]
    assert (places["a"].tie_reason, places["a"].tie_criterion) == ("manual", "innenzehner")
    assert places["a"].tie_unresolved
    # Zehner fehlen dagegen wirklich, wenn eine Seriensumme ohne Zehner erfasst ist.
    sums = compute(definition, "series", raw_sums({"sum": "20.0"}))
    assert sums.tie_breakers_missing == ["zehner"]


def test_series_capture_does_not_report_shot_criteria_as_missing() -> None:
    definition = ring_definition(serien=2, schuss=5, gleichstand=["zehner", "neuner_abwaerts"])
    result = compute(definition, "series", raw_sums({"sum": 45, "tens": 2}, {"sum": 44, "tens": 1}))
    assert result.tie_breakers_missing == []
    # Mit Einzelschüssen lässt sich „Neuner abwärts“ erfassen; ein Zwischenstand hat die Werte.
    partial = compute(definition, "shot", raw_shots([10, 9]))
    assert partial.tie_breakers_missing == []


def test_hits_only_has_no_tens() -> None:
    definition = ring_definition(
        serien=1, schuss=5, section={"ringwerte": [1, 0]}, gleichstand=["zehner"]
    )
    result = compute(definition, "shot", raw_shots([1, 0, 1, 1, 1]))
    assert (result.tens, result.inner_tens) == (None, None)
    assert result.sections[0].series[0].tens is None
    assert result.tie_breakers_missing == []
    assert tie_rules(definition).uncapturable == ["zehner"]


def test_tie_resolved_by_chain_names_the_criterion() -> None:
    definition = ring_definition(serien=1, schuss=2, gleichstand=["zehner", "neuner_abwaerts"])
    places = ranked(
        definition,
        {
            "a": raw_shots([10, 8]),  # 18, 1 Zehner
            "b": raw_shots([9, 9]),  # 18, 0 Zehner, 2 Neuner
            "c": raw_shots([9, 9]),  # wie b: geteilt
            "d": raw_shots([10, 7]),  # 17: eigenes Ergebnis
            "e": raw_shots([10, 6]),  # 16, 1 Zehner
            "f": raw_shots([9, 7]),  # 16, 0 Zehner
        },
    )
    a, b, d, e = places["a"], places["b"], places["d"], places["e"]
    assert (a.place, a.tied, a.tie_unresolved) == (1, False, False)
    assert (a.tie_reason, a.tie_criterion) == ("resolved", "zehner")
    assert a.tie_note == "Ringgleichheit, entschieden nach: Anzahl der Zehner"
    # b und c bleiben nach allen Kriterien gleich: geteilt, nicht „resolved“.
    assert (b.place, b.tied, b.tie_reason) == (2, True, None)
    assert (d.place, d.tie_reason, d.tie_note) == (4, None, None)
    assert (e.tie_reason, places["f"].tie_reason) == ("resolved", "resolved")
    assert places["f"].tie_criterion == "zehner"


def test_tie_resolved_further_down_the_chain() -> None:
    definition = ring_definition(serien=1, schuss=3, gleichstand=["zehner", "neuner_abwaerts"])
    # 27 = 27 = 27: c hat 2 Zehner (entschieden nach Zehnern); a und b bleiben gleich.
    places = ranked(
        definition,
        {"a": raw_shots([10, 9, 8]), "b": raw_shots([10, 8, 9]), "c": raw_shots([10, 10, 7])},
    )
    assert (places["c"].place, places["c"].tie_criterion) == (1, "zehner")
    assert places["a"].tied
    # Gleich viele Zehner, mehr Neuner: entschieden nach „Neuner abwärts“.
    places = ranked(definition, {"a": raw_shots([10, 9, 7]), "b": raw_shots([10, 8, 8])})
    assert (places["a"].place, places["a"].tie_criterion) == (1, "neuner_abwaerts")
    assert (places["b"].place, places["b"].tie_criterion) == (2, "neuner_abwaerts")


# --- Stechen ---------------------------------------------------------------------------


def test_shootoff_until_place() -> None:
    definition = ring_definition(
        serien=1, schuss=2, gleichstand=["stechen", "zehner"], stechen_bis_platz=2
    )
    rules = tie_rules(definition)
    assert (rules.criteria, rules.manual_from, rules.shootoff_until) == (["zehner"], None, 2)
    places = ranked(
        definition,
        {
            "a": raw_shots([10, 9]),
            "b": raw_shots([10, 8]),  # 18 … Platz 2 mit c: Stechen statt Zehner
            "c": raw_shots([9, 9]),
            "d": raw_shots([10, 6]),  # 16 … Platz 4 mit e: nach Zehnern getrennt
            "e": raw_shots([8, 8]),
        },
    )
    assert [places[i].place for i in "abcde"] == [1, 2, 2, 4, 5]
    assert places["b"].needs_shootoff
    assert places["c"].needs_shootoff
    assert places["b"].tie_reason == "shootoff"
    assert places["b"].tie_unresolved
    assert places["b"].tie_note == "Ringgleichheit auf Platz 2: Stechen"
    assert not places["a"].needs_shootoff
    assert not places["d"].tied
    assert not places["d"].needs_shootoff


def test_shootoff_group_reaching_into_range() -> None:
    definition = ring_definition(serien=1, schuss=1, stechen_bis_platz=1)
    places = ranked(definition, {"a": raw_shots([10]), "b": raw_shots([10]), "c": raw_shots([9])})
    assert places["a"].needs_shootoff
    assert places["a"].tie_note == "Ringgleichheit auf Platz 1: Stechen"
    assert places["c"].place == 3


def test_stechen_without_place_limit_is_manual_everywhere() -> None:
    definition = ring_definition(serien=1, schuss=1, gleichstand=["stechen", "zehner"])
    places = ranked(definition, {"a": raw_shots([9]), "b": raw_shots([9])})
    assert places["a"].tie_reason == "manual"
    assert places["a"].tie_criterion == "stechen"
    assert not places["a"].needs_shootoff


def test_rank_without_rules_is_unchanged() -> None:
    definition = ring_definition(serien=1, schuss=1, gleichstand=["zehner"])
    contenders = [contender(definition, raw_shots([9]), i) for i in "ab"]
    placements = rank(contenders)
    assert [(p.place, p.tied, p.tie_unresolved, p.tie_reason) for p in placements] == [
        (1, True, False, None),
        (1, True, False, None),
    ]


# --- Alle neuen Felder zusammen -------------------------------------------------------


def test_all_new_optional_fields_pass_the_strict_definition() -> None:
    definition = tenths(
        serien=2,
        schuss=2,
        gleichstand=[*DSB_TIES, "zehntel_gesamt", "stechen", "mouchen"],
        stechen_bis_platz=3,
        section={
            "wettkampfzeit_s": 3000,
            "vorbereitung_probe_s": 900,
            "probeschuesse": "unbegrenzt",
            "positionen": [
                {"nr": 1, "anschlaege": [{"haltung": "sitzend", "aufgelegt": True}]},
                {"nr": 2, "anschlaege": [{"haltung": "stehend", "aufgelegt": False}]},
            ],
        },
        variant={"wettkampfzeit_gesamt_s": 4500},
    )
    defn = load_definition(copy.deepcopy(definition))
    assert defn.scoring.zehntelwertung is True
    assert defn.scoring.stechen_bis_platz == 3
    form = describe_form(definition, "shot")
    section = form.sections[0]
    assert (section.competition_time_s, section.preparation_time_s, section.sighters) == (
        Decimal(3000),
        Decimal(900),
        "unbegrenzt",
    )
    assert "Wettkampfzeit 50 min" in section.hints
    assert "Vorbereitung und Probe 15 min" in section.hints
    assert "Probeschüsse unbegrenzt" in section.hints
    assert form.competition_time_total_s == Decimal(4500)
    assert "Gemeinsame Wettkampfzeit aller Abschnitte: 75 min" in form.notes
    assert form.shootoff_until_place == 3
    assert form.tie_breakers_evaluated == [*DSB_TIES, "zehntel_gesamt"]
    assert form.tie_breakers_manual_from == "mouchen"
    stance = section.series[0].position.stances[0]  # type: ignore[union-attr]
    assert (stance.haltung, stance.aufgelegt, stance.text) == (
        "sitzend",
        True,
        "sitzend, aufgelegt",
    )
    assert section.series[1].position.stances[0].text == "stehend"  # type: ignore[union-attr]

    result = compute(definition, "shot", raw_shots([10.9, 10.0], [9.9, 0]))
    assert result.score == Decimal("30.8")


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"section": {"probeschuesse": -1}}, "probeschuesse"),
        ({"section": {"probeschuesse": "viele"}}, "probeschuesse"),
        ({"section": {"wettkampfzeit_s": 0}}, "wettkampfzeit_s"),
        ({"section": {"vorbereitung_probe_s": -5}}, "vorbereitung_probe_s"),
        ({"variant": {"wettkampfzeit_gesamt_s": 0}}, "wettkampfzeit_gesamt_s"),
        ({"stechen_bis_platz": 0}, "stechen_bis_platz"),
        ({"zehntelwertung": "ja"}, "zehntelwertung"),
        ({"gleichstand": ["Zehner"]}, "gleichstand[0]"),
        ({"gleichstand": ["stechen", "stechen"]}, "steht mehrfach"),
    ],
)
def test_new_fields_are_checked(change: dict, fragment: str) -> None:
    with pytest.raises(DefinitionError) as caught:
        load_definition(ring_definition(**change))
    assert any(fragment in problem for problem in caught.value.problems), caught.value.problems


def test_invalid_raw_error_for_tenths_in_compute() -> None:
    with pytest.raises(InvalidRawError):
        compute(tenths(serien=1, schuss=1), "shot", raw_shots([11.5]))


# --- Wurfscheibe: ein Wert je Ziel ----------------------------------------------------


def test_trap_is_captured_per_target() -> None:
    # Trap: bis zu zwei Schuss je Scheibe; erfasst wird Treffer 1/0 je Scheibe.
    definition = ring_definition(
        serien=1,
        gleichstand=["stechen", "letzte_serie_rueckwaerts"],
        stechen_bis_platz=6,
        section={
            "schuss_je_serie": None,
            "max_schuss_je_serie": 50,
            "ziele_je_serie": 25,
            "ringwerte": [1, 0],
        },
    )
    definition["variant"]["abschnitte"][0].pop("schuss_je_serie")
    shot_form = describe_form(definition, "shot").sections[0].series[0]
    (field,) = shot_form.fields
    assert (field.key, field.count, field.allowed_values, field.per_target) == (
        "shots",
        25,
        [1, 0],
        True,
    )
    assert field.label == "Treffer je Ziel"
    assert shot_form.max_rings == 25
    (total,) = describe_form(definition, "series").sections[0].series[0].fields
    assert (total.key, total.label, total.max) == ("sum", "Treffer", 25)
    assert messages(definition, raw_sums({"sum": 26}), "series") == [
        "Serie 1: Seriensumme: ganze Zahl von 0 bis 25"
    ]
    assert messages(definition, raw_shots([1] * 26)) == ["Serie 1: höchstens 25 Ziele, erfasst 26"]
    assert messages(definition, raw_shots([1, 2])) == ["Serie 1, Ziel 2: Wert 1 oder 0, nicht 2"]
    result = compute(definition, "shot", raw_shots([1] * 20 + [0] * 5))
    assert (result.score, result.hits, result.complete) == (20, 20, True)
    # „ein Wert je Ziel“ nur in der Erfassungsart je Ziel.
    assert "25 Ziele, ein Wert je Ziel" in shot_form.hints
    series_form = describe_form(definition, "series").sections[0].series[0]
    assert "25 Ziele" in series_form.hints
    assert not any("je Ziel" in hint for hint in series_form.hints)
    # Hinweise der Maske mit Art.
    notes = describe_form(definition, "shot")
    assert [item.kind for item in notes.note_items] == ["shootoff"]
    assert notes.notes == [item.text for item in notes.note_items]


def test_missing_tie_breakers_with_text() -> None:
    definition = ring_definition(serien=1, schuss=2, gleichstand=["zehner", "innenzehner"])
    result = compute(definition, "series", raw_sums({"sum": 18}))
    assert result.tie_breakers_missing == ["zehner", "innenzehner"]
    dumped = result.model_dump(mode="json")
    assert dumped["tie_breakers_missing_items"] == [
        {"id": "zehner", "text": "Anzahl der Zehner"},
        {"id": "innenzehner", "text": "Anzahl der Innenzehner"},
    ]
    # Gespeicherte Stände (mit oder ohne das Feld) lassen sich wieder einlesen.
    again = ComputedResult.model_validate(dumped)
    assert again.tie_breakers_missing_items == result.tie_breakers_missing_items
    dumped.pop("tie_breakers_missing_items")
    assert ComputedResult.model_validate(dumped).tie_breakers_missing_items[0].id == "zehner"


def test_count_criteria_for_field_archery() -> None:
    definition = ring_definition(
        serien=1, schuss=3, section={"ringwerte": [6, 5, 4, 0]}, gleichstand=["sechser", "fuenfer"]
    )
    places = ranked(
        definition,
        {"a": raw_shots([6, 4, 0]), "b": raw_shots([5, 5, 0]), "c": raw_shots([5, 5, 0])},
    )
    assert [places[i].place for i in "abc"] == [1, 2, 2]


def test_series_sum_with_3d_tens_allows_elevens() -> None:
    definition = ring_definition(
        serien=1, schuss=2, section={"ringwerte": [11, 10, 8, 5, 0]}, gleichstand=["zehner"]
    )
    assert messages(definition, raw_sums({"sum": 21, "tens": 1}), "series") == []
    assert messages(definition, raw_sums({"sum": 22, "tens": 1}), "series") == [
        "Serie 1: mit 1 Zehnern sind höchstens 21 Ringe möglich"
    ]


def test_export_series_text_uses_decimal_comma() -> None:
    from app.modules.export.records import SeriesValue
    from app.modules.export.tables import series_text

    value = SeriesValue("lg", 1, False, "normal", Decimal("20.1"), None, None, None)
    assert series_text(value) == "20,1"
    assert series_text(SeriesValue("p", 1, False, "normal", 92, None, None, None)) == "92"
