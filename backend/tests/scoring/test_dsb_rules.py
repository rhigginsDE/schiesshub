"""DSB-Regeln der Wertung: Höchstergebnis ohne Unterscheidung (SpO 0.12.1 Satz 1), letzte
Zehnerserie rückwärts in 10-Schuss-Blöcken (SpO 0.12.1 Nr. 1, 9.4.1), Einheit „Treffer“,
Klartext der Gleichstandskriterien und Felder der Eingabemaske.

Handgerechnete Beispiele; die Definitionen sind eigene Testdaten, keine Katalogkopie.
"""

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from app.scoring import DefinitionError, compute, describe_form, load_definition, tie_rules
from app.scoring.criteria import criterion_text, criterion_texts
from app.scoring.tiebreak import criterion_values
from tests.conftest import REAL_CATALOG_DIR
from tests.scoring.test_dsb_fields import (
    DSB_TIES,
    ranked,
    raw_shots,
    raw_sums,
    ring_definition,
    tenths,
)

# --- Höchstergebnis (SpO 0.12.1 Satz 1) --------------------------------------------------


def test_max_score_shares_the_place_without_chain() -> None:
    definition = ring_definition(
        serien=2, schuss=2, gleichstand=DSB_TIES, hoechstergebnis_gleicher_rang=True
    )
    raws = {
        "a": raw_shots(["X", 10], [10, 10]),  # 40 = Höchstergebnis, ein Innenzehner
        "b": raw_shots([10, 10], [10, 10]),  # 40, ohne Innenzehner
        "c": raw_shots(["X", 9], [10, 10]),  # 39: Kette trennt weiter (Innenzehner)
        "d": raw_shots([10, 10], [9, 10]),  # 39
    }
    places = ranked(definition, raws)
    assert [places[i].place for i in "abcd"] == [1, 1, 3, 4]
    for ident in "ab":
        placement = places[ident]
        assert placement.tied
        assert placement.tie_reason == "max_score"
        assert not placement.tie_unresolved
        assert not placement.needs_shootoff
        assert placement.tie_criterion is None
        assert placement.tie_note == "Höchstergebnis: gleicher Platz"
    assert not places["c"].tied


def test_without_flag_max_score_is_separated_by_the_chain() -> None:
    definition = ring_definition(serien=2, schuss=2, gleichstand=DSB_TIES)
    raws = {"a": raw_shots(["X", 10], [10, 10]), "b": raw_shots([10, 10], [10, 10])}
    places = ranked(definition, raws)
    assert (places["a"].place, places["b"].place) == (1, 2)


def test_max_score_comes_before_shootoff_and_manual() -> None:
    definition = ring_definition(
        serien=1,
        schuss=2,
        gleichstand=["stechen", "letzte_serie_rueckwaerts"],
        stechen_bis_platz=3,
        hoechstergebnis_gleicher_rang=True,
    )
    raws = {
        "a": raw_shots([10, 10]),
        "b": raw_shots([10, 10]),
        "c": raw_shots([9, 10]),
        "d": raw_shots([10, 9]),
    }
    places = ranked(definition, raws)
    assert places["a"].tie_reason == "max_score"
    assert not places["a"].needs_shootoff
    assert places["c"].place == 3
    assert places["c"].tie_reason == "shootoff"  # 19 auf Platz 3: Stechen wie bisher


@pytest.mark.parametrize(
    ("definition", "expected"),
    [
        (ring_definition(serien=6, schuss=10), Decimal(600)),
        # gestrichene Serien zählen nicht
        (ring_definition(serien=3, schuss=10, section={"serien_gewertet": 2}), Decimal(200)),
        (tenths(serien=6, schuss=10), Decimal("654.0")),
        (ring_definition(serien=1, schuss=3, section={"ringwerte": [11, 10, 8, 5, 0]}), 33),
        (ring_definition(serien=2, schuss=5, section={"ringwerte": [1, 0]}), 10),
    ],
)
def test_max_score_per_variant(definition: dict, expected: Decimal) -> None:
    defn = load_definition(definition)
    assert defn.max_score == expected


def test_max_score_in_tenths() -> None:
    definition = tenths(serien=1, schuss=2, hoechstergebnis_gleicher_rang=True)
    assert tie_rules(definition).max_score_key == 2180
    places = ranked(
        definition,
        {"a": raw_shots(["10.9", "10.9"]), "b": raw_shots(["10.9", "10.9"])},
    )
    assert places["a"].tie_reason == "max_score"
    form = describe_form(definition, "shot")
    assert "Höchstergebnis (21,8 Ringe): bei Ergebnisgleichheit gleicher Platz" in form.notes[-1]


def test_max_score_flag_only_for_rings_model() -> None:
    definition = {
        "variant": {
            "id": "s",
            "name": "S",
            "abschnitte": [
                {"id": "wk", "name": "W", "serien": 1, "schuss_je_serie": 5, "sollzeit_s": 60}
            ],
        },
        "scoring": {
            "modell": "ringe_mit_zeitabzug",
            "rangfolge": "absteigend",
            "abzug_je_voller_sekunde_ueber_sollzeit": 1,
            "hoechstergebnis_gleicher_rang": True,
        },
    }
    definition["variant"]["abschnitte"][0]["zeit_wird_gemessen"] = True
    with pytest.raises(DefinitionError) as error:
        load_definition(definition)
    assert any("hoechstergebnis_gleicher_rang" in p for p in error.value.problems)
    # `false` ist bei jedem Modell erlaubt
    definition["scoring"]["hoechstergebnis_gleicher_rang"] = False
    load_definition(definition)


# --- Letzte Zehnerserie rückwärts (SpO 0.12.1 Nr. 1, 9.4.1) -----------------------------


def _blocks(definition: dict, raw: dict, mode: str = "shot") -> list[int | None]:
    defn = load_definition(definition)
    return criterion_values(defn, compute(definition, mode, raw), "letzte_serie_rueckwaerts")


def test_blocks_from_single_shots_ignore_series_length() -> None:
    # 3 Serien zu 4 Schuss = 12 Schuss: Blöcke vom Ende her 10 + 2 (Annahme: vorn kürzer).
    definition = ring_definition(serien=3, schuss=4, gleichstand=["letzte_serie_rueckwaerts"])
    raw = raw_shots([1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 10, 9])
    assert _blocks(definition, raw) == [(3 + 4 + 5 + 6 + 7 + 8 + 9 + 10 + 10 + 9) * 100, 300]


def test_blocks_from_ten_shot_series_sums() -> None:
    definition = ring_definition(serien=3, schuss=10, gleichstand=["letzte_serie_rueckwaerts"])
    raw = raw_sums({"sum": 91}, {"sum": 92}, {"sum": 93})
    assert _blocks(definition, raw, "series") == [9300, 9200, 9100]


def test_blocks_from_five_shot_series_sums_in_pairs_from_the_end() -> None:
    definition = ring_definition(serien=6, schuss=5, gleichstand=["letzte_serie_rueckwaerts"])
    raw = raw_sums(*({"sum": value} for value in (41, 42, 43, 44, 45, 46)))
    assert _blocks(definition, raw, "series") == [9100, 8700, 8300]
    assert describe_form(definition, "series").notes == []


def test_series_sums_that_do_not_fit_blocks_are_missing() -> None:
    # 4 Serien zu 3 Schuss: Serie 4 = Schuss 10–12 liegt im letzten Block, Serie 3 (7–9) auch,
    # Serie 2 (4–6) teils im letzten (5, 6), teils im ersten Block → beide fehlen.
    definition = ring_definition(serien=4, schuss=3, gleichstand=["letzte_serie_rueckwaerts"])
    raw = raw_sums(*({"sum": 27} for _ in range(4)))
    assert _blocks(definition, raw, "series") == [None, None]
    places = ranked(definition, {"a": raw, "b": raw}, mode="series")
    assert places["a"].tie_reason == "missing_data"
    assert places["a"].tie_criterion == "letzte_serie_rueckwaerts"
    assert "Zehnerserie" in (places["a"].tie_note or "")
    notes = describe_form(definition, "series").notes
    assert any("nicht nach Zehnerserien auflösen" in note for note in notes)


def test_blocks_across_sections() -> None:
    definition = ring_definition(serien=1, schuss=5, gleichstand=["letzte_serie_rueckwaerts"])
    second = {"id": "b", "name": "B", "serien": 1, "schuss_je_serie": 5}
    definition["variant"]["abschnitte"].append(second)
    raw = {
        "sections": {
            "wk": {"series": [{"shots": [10, 10, 10, 10, 10]}]},
            "b": {"series": [{"shots": [9, 9, 9, 9, 9]}]},
        }
    }
    assert _blocks(definition, raw) == [9500]


def test_unfinished_block_is_missing() -> None:
    definition = ring_definition(serien=2, schuss=10, gleichstand=["letzte_serie_rueckwaerts"])
    raw = raw_shots([10] * 10, [10] * 4)
    assert _blocks(definition, raw) == [None, 10000]


def test_hits_only_keep_series_as_defined() -> None:
    # Wurfscheibe (SpO 3.9.1.2): letzte Serie (25 Scheiben), dann rückwärts.
    definition = ring_definition(
        serien=2, schuss=25, section={"ringwerte": [1, 0]}, gleichstand=["letzte_serie_rueckwaerts"]
    )
    raw = raw_shots([1] * 20 + [0] * 5, [1] * 24 + [0])
    assert _blocks(definition, raw) == [2400, 2000]


# --- Einheit „Treffer“ --------------------------------------------------------------------


def test_unit_hits_when_ring_values_only_count_hits() -> None:
    definition = ring_definition(serien=1, schuss=5, section={"ringwerte": [1, 0]})
    result = compute(definition, "shot", raw_shots([1, 1, 0, 1, 1]))
    assert (result.unit, result.score_text) == ("Treffer", "4 Treffer")
    assert result.steps[-1] == "Ergebnis: 4 Treffer"
    assert describe_form(definition, "shot").unit == "Treffer"


@pytest.mark.parametrize(
    "section", [{}, {"ringwerte": [10, 7, 0]}, {"ringwerte": [11, 10, 8, 5, 0]}]
)
def test_unit_rings_otherwise(section: dict) -> None:
    definition = ring_definition(serien=1, schuss=2, section=section)
    assert describe_form(definition, "shot").unit == "Ringe"


# --- Klartext der Kriterien ---------------------------------------------------------------


def _catalog_criteria() -> set[str]:
    found: set[str] = set()
    for path in sorted(Path(REAL_CATALOG_DIR).glob("*/gruppen/*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        wertung = data.get("wertung") or {}
        found.update(wertung.get("gleichstand") or [])
    return found


def test_every_catalog_criterion_has_a_text() -> None:
    criteria = _catalog_criteria()
    assert "letzte_serie_rueckwaerts" in criteria  # der echte Katalog ist da
    missing = sorted(criteria - set(criterion_texts()))
    assert missing == [], f"Klartext fehlt in app/scoring/kriterien.yaml: {missing}"


def test_unknown_criterion_is_made_readable() -> None:
    assert criterion_text("abstand_zum_rand") == "abstand zum rand"
    assert criterion_text("trefferfolge_rueckwaerts") == (
        "Trefferfolge ab der letzten Scheibe rückwärts bis zum ersten Fehler"
    )
    assert criterion_text(None) is None


def test_form_note_names_manual_criterion_in_plain_text() -> None:
    definition = ring_definition(gleichstand=["zehner", "trefferfolge_rueckwaerts"])
    notes = describe_form(definition, "shot").notes
    assert any("Trefferfolge ab der letzten Scheibe" in note for note in notes)
    assert not any("trefferfolge_rueckwaerts" in note for note in notes)


# --- Eingabemaske -------------------------------------------------------------------------


def test_tenths_series_sum_starts_at_one_with_zero_allowed() -> None:
    form = describe_form(tenths(serien=1, schuss=10), "series").model_dump(mode="json")
    (field,) = form["sections"][0]["series"][0]["fields"]
    assert (field["key"], field["value_min"], field["value_max"]) == ("sum", "1.0", "109.0")
    assert field["zero_allowed"] is True


def test_hint_items_carry_a_kind() -> None:
    definition = ring_definition(
        serien=2,
        schuss=5,
        section={
            "wettkampfzeit_s": 3000,
            "vorbereitung_probe_s": 900,
            "probeschuesse": "unbegrenzt",
            "serien_gewertet": 1,
            "trefferaufnahme_nach": [1],
        },
    )
    section = describe_form(definition, "shot").sections[0]
    # `hints` bleibt unverändert; `hint_items` sind dieselben Texte mit Art.
    assert section.hints == [item.text for item in section.hint_items]
    assert [item.kind for item in section.hint_items] == [
        "competition_time",
        "preparation_time",
        "sighters",
    ]
    assert (section.competition_time_s, section.sighters) == (Decimal(3000), "unbegrenzt")
    first, struck = section.series
    assert [item.kind for item in first.hint_items] == ["shots", "scoring_break"]
    assert [item.kind for item in struck.hint_items] == ["struck", "shots"]
    assert struck.hints == [item.text for item in struck.hint_items]


def _positions(*aufgelegt: bool | None) -> dict:
    return {
        "positionen": [
            {"nr": index + 1, "anschlaege": [{"haltung": "sitzend", "aufgelegt": value}]}
            for index, value in enumerate(aufgelegt)
        ]
    }


@pytest.mark.parametrize(
    ("section", "expected"),
    [
        ({}, False),
        (_positions(True, True), True),
        (_positions(True, None), False),
    ],
)
def test_section_aufgelegt(section: dict, expected: bool) -> None:
    serien = len(section.get("positionen", [])) or 1
    definition = ring_definition(serien=serien, schuss=5, section=section)
    form = describe_form(definition, "shot").model_dump(mode="json")
    assert form["sections"][0]["aufgelegt"] is expected
