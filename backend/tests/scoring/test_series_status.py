"""Optionale Regeln: `ringwerte`, nicht beendete Speed-Serie, Abbruch und Störung bei Fallscheibe.

Die Definitionen setzen die Felder selbst, damit die Tests nicht vom Katalogstand abhängen.
"""

import copy
import random
from decimal import Decimal

import pytest

from app.scoring import DefinitionError, Issue, compute, describe_form, rank_key, validate_raw
from app.scoring.form import FieldSpec
from tests.scoring import definitions
from tests.scoring.support import series_of

SPEED_PLAIN = definitions.speed()
SPEED = copy.deepcopy(SPEED_PLAIN)
SPEED["variant"]["abschnitte"][0]["ringwerte"] = [10, 7, 0]
SPEED["scoring"]["unbeendete_serie"] = "ringe_bis_dahin_zeit_letzter_schuss"

GK_PLAIN = definitions.fallscheibe()
GK = copy.deepcopy(GK_PLAIN)
GK["variant"]["abschnitte"][0].update(
    zeit_bei_abbruch_s=60, zuschlag_stoerung_vor_erstem_schuss_s=50
)
GK_ABORT_ONLY = copy.deepcopy(GK)
del GK_ABORT_ONLY["variant"]["abschnitte"][0]["zuschlag_stoerung_vor_erstem_schuss_s"]


def first_field(data: dict, capture_mode: str, key: str) -> FieldSpec:
    fields = describe_form(data, capture_mode).sections[0].series[0].fields
    return next(field for field in fields if field.key == key)


def speed(*series: dict) -> dict:
    return series_of(*series, section="speed")


def fallscheibe(*series: dict) -> dict:
    return series_of(*series, section="fallscheibe")


# --- ringwerte ----------------------------------------------------------------


def test_ring_values_restrict_form_and_input() -> None:
    assert first_field(SPEED, "shot", "shots").allowed_values == [10, 7, 0]
    assert describe_form(SPEED, "shot").max_rings == 200
    assert first_field(SPEED, "series", "sum").max == 50

    issues = validate_raw(SPEED, "shot", speed({"shots": [10, 9, "X"], "time_cs": 900}))
    assert issues == [
        Issue(
            path="sections.speed.series[0].shots[1]",
            message="Serie 1, Schuss 2: Ringwert 10, 7 oder 0, nicht 9",
        ),
        Issue(
            path="sections.speed.series[0].shots[2]",
            message="Serie 1, Schuss 3: Ringwert 10, 7 oder 0, nicht 'X'",
        ),
    ]


def test_without_ring_values_every_ring_is_allowed() -> None:
    field = first_field(SPEED_PLAIN, "shot", "shots")
    assert field.allowed_values == ["X", 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
    assert validate_raw(SPEED_PLAIN, "shot", speed({"shots": [9, "X"], "time_cs": 900})) == []


# --- nicht beendete Speed-Serie -------------------------------------------------

FULL_SPEED = [
    {"shots": [10, 10, 7, 10, 0], "time_cs": 853},
    {"shots": [10, 10, 10, 10, 10], "time_cs": 1021},
    {"status": "unfinished", "shots": [10, 7, 10], "time_cs": 4512},
    {"shots": [10, 0, 10, 7, 10], "time_cs": 999},
]


def test_unfinished_series_counts_rings_so_far_and_time_of_last_shot() -> None:
    assert validate_raw(SPEED, "shot", speed(*FULL_SPEED), partial=False) == []

    result = compute(SPEED, "shot", speed(*FULL_SPEED))

    # 37 + 50 + 27 + 37 = 151 Ringe; 8,53 + 10,21 + 45,12 + 9,99 = 73,85 s → 73 s
    assert result.score == 151 - 73
    assert result.complete
    third = result.sections[0].series[2]
    assert (third.status, third.complete, third.rings, third.shots_entered) == (
        "unfinished",
        True,
        27,
        3,
    )
    assert result.steps[2] == (
        "Serie 3: Serie nicht beendet → 10 + 7 + 10 = 27 Ringe (3 von 5 Schuss), "
        "Zeit des letzten Schusses 45,12 s"
    )


def test_series_with_too_few_shots_without_status_stays_incomplete() -> None:
    plain = [*FULL_SPEED[:2], {"shots": [10, 7, 10], "time_cs": 4512}, FULL_SPEED[3]]
    assert validate_raw(SPEED, "shot", speed(*plain), partial=False) == [
        Issue(path="sections.speed.series[2].shots", message="Serie 3: 3 von 5 Schuss erfasst")
    ]
    assert not compute(SPEED, "shot", speed(*plain)).complete


@pytest.mark.parametrize(
    ("series", "path", "message"),
    [
        (
            {"status": "unfinished", "shots": [10, 10, 10, 10, 10], "time_cs": 900},
            "shots",
            "Serie 1: als nicht beendet erfasst, aber alle 5 Schuss erfasst",
        ),
        (
            {"status": "unfinished", "sum": 30, "time_cs": 900},
            "",
            "Serie 1: nicht beendete Serie nur mit Einzelschüssen",
        ),
        (
            {"status": "unfinished", "shots": [10]},
            "time_cs",
            "Serie 1: Zeit fehlt",
        ),
        (
            {"status": "time_limit", "shots": [10], "time_cs": 900},
            "status",
            "Serie 1: für diese Disziplin nicht vorgesehener Status 'time_limit'; erlaubt: "
            "„normal“ (regulär), „unfinished“ (Serie nicht beendet)",
        ),
    ],
)
def test_invalid_unfinished_series(series: dict, path: str, message: str) -> None:
    full_path = "sections.speed.series[0]" + (f".{path}" if path else "")
    issues = validate_raw(SPEED, "shot", speed(series), partial=False)
    assert Issue(path=full_path, message=message) in issues


def test_unfinished_needs_the_scoring_rule() -> None:
    issues = validate_raw(SPEED_PLAIN, "shot", speed({"status": "unfinished", "shots": [10]}))
    assert issues == [
        Issue(
            path="sections.speed.series[0].status",
            message="Serie 1: für diese Disziplin nicht vorgesehener Status 'unfinished'; "
            "erlaubt: „normal“ (regulär)",
        )
    ]


def test_speed_form_offers_unfinished_status() -> None:
    status = describe_form(SPEED, "shot").sections[0].series[0].fields[0]
    assert status.key == "status"
    assert status.kind == "choice"
    assert not status.required
    assert [o.model_dump() for o in status.options or []] == [
        {"key": "normal", "label": "regulär", "required_fields": ["shots", "time_cs"]},
        {
            "key": "unfinished",
            "label": "Serie nicht beendet",
            "required_fields": ["shots", "time_cs"],
        },
    ]
    assert all(
        f.key != "status" for f in describe_form(SPEED_PLAIN, "shot").sections[0].series[0].fields
    )


# --- Fallscheibe: Abbruch und Störung -------------------------------------------

FALLSCHEIBE_SERIES = [
    {"time_cs": 1284, "standing": 1},
    {"status": "time_limit", "time_cs": 6120, "standing": 2},
    {"status": "aborted_by_shooter", "standing": 2},
    {"status": "malfunction_before_first_shot"},
]


def test_abort_and_malfunction_use_fixed_series_time() -> None:
    raw = fallscheibe(*FALLSCHEIBE_SERIES)
    assert validate_raw(GK, "shot", raw, partial=False) == []

    result = compute(GK, "shot", raw)

    # 22,84 + (60 + 20) + (60 + 20) + (60 + 50) = 292,84 s
    assert str(result.score) == "292.84"
    assert result.complete
    assert result.warnings == []  # die gemessene 61,20 s zählt nicht, also keine Warnung
    assert [
        (s.status, s.measured_time_cs, s.time_cs, s.total_cs) for s in result.sections[0].series
    ] == [
        ("normal", 1284, 1284, 2284),
        ("time_limit", 6120, 6000, 8000),
        ("aborted_by_shooter", None, 6000, 8000),
        ("malfunction_before_first_shot", None, 6000, 11000),
    ]
    assert result.steps == [
        "Serie 1: 12,84 s + 1 stehende Scheibe × 10 s = 22,84 s",
        "Serie 2: Zeitlimit erreicht (Abbruch durch den Schießleiter) → 60,00 s + 2 stehende "
        "Scheiben × 10 s = 80,00 s; gemessene Zeit 61,20 s wird nicht gewertet",
        "Serie 3: Abbruch durch den Schützen → 60,00 s + 2 stehende Scheiben × 10 s = 80,00 s",
        "Serie 4: Waffenstörung vor dem ersten Wertungsschuss → 60,00 s + 50 s Zuschlag = 110,00 s",
        "Ergebnis: 22,84 s + 80,00 s + 80,00 s + 110,00 s = 292,84 s",
    ]


def test_aborted_series_needs_standing_targets_malfunction_does_not() -> None:
    raw = fallscheibe({"status": "aborted_by_shooter"}, {"status": "malfunction_before_first_shot"})
    issues = validate_raw(GK, "shot", raw, partial=False)
    assert issues[0] == Issue(
        path="sections.fallscheibe.series[0].standing",
        message="Serie 1: Anzahl stehender Scheiben fehlt",
    )
    assert all("series[1]" not in issue.path for issue in issues)

    partial = compute(GK, "shot", raw)
    assert partial.steps[0] == (
        "Serie 1: Abbruch durch den Schützen → 60,00 s (stehende Scheiben noch nicht erfasst)"
    )
    assert not partial.sections[0].series[0].complete
    assert partial.sections[0].series[1].complete


def test_standing_targets_are_ignored_after_malfunction() -> None:
    result = compute(
        GK, "shot", fallscheibe({"status": "malfunction_before_first_shot", "standing": 5})
    )
    assert result.sections[0].series[0].total_cs == 11000
    assert result.steps[0].endswith("= 110,00 s; stehende Scheiben werden nicht gewertet")


def test_regular_series_over_limit_recommends_time_limit_status() -> None:
    result = compute(GK, "shot", fallscheibe({"time_cs": 6120, "standing": 0}))
    assert result.score == Decimal("61.20")
    assert result.warnings == [
        Issue(
            path="sections.fallscheibe.series[0].time_cs",
            message="Serie 1: 61,20 s liegt über dem Zeitlimit von 60 s. Wurde die Serie beim "
            "Zeitlimit abgebrochen, den Status „Zeitlimit erreicht“ wählen; sonst geht die "
            "gemessene Zeit unverändert ein.",
        )
    ]
    plain = compute(GK_PLAIN, "shot", fallscheibe({"time_cs": 6120, "standing": 0}))
    assert "Der Katalog legt dafür keine Wertung fest" in plain.warnings[0].message


def test_statuses_need_the_catalog_fields() -> None:
    raw = fallscheibe({"status": "aborted_by_shooter", "standing": 1})
    assert validate_raw(GK_PLAIN, "shot", raw) == [
        Issue(
            path="sections.fallscheibe.series[0].status",
            message="Serie 1: für diese Disziplin nicht vorgesehener Status 'aborted_by_shooter'; "
            "erlaubt: „normal“ (regulär)",
        )
    ]
    malfunction = fallscheibe({"status": "malfunction_before_first_shot"})
    assert validate_raw(GK_ABORT_ONLY, "shot", malfunction)[0].path.endswith(".status")
    assert validate_raw(GK_ABORT_ONLY, "shot", raw) == []
    assert validate_raw(GK, "shot", fallscheibe({"status": "pause"}))[0].message.startswith(
        "Serie 1: unbekannter Status 'pause'"
    )


def test_fallscheibe_form_lists_statuses_with_required_fields() -> None:
    fields = describe_form(GK, "shot").sections[0].series[0].fields
    assert [f.key for f in fields] == ["status", "time_cs", "standing"]
    assert [(o.key, o.label, o.required_fields) for o in fields[0].options or []] == [
        ("normal", "regulär", ["time_cs", "standing"]),
        ("time_limit", "Zeitlimit erreicht (Abbruch durch den Schießleiter)", ["standing"]),
        ("aborted_by_shooter", "Abbruch durch den Schützen", ["standing"]),
        ("malfunction_before_first_shot", "Waffenstörung vor dem ersten Wertungsschuss", []),
    ]
    abort_only = describe_form(GK_ABORT_ONLY, "shot").sections[0].series[0].fields[0]
    assert [o.key for o in abort_only.options or []] == [
        "normal",
        "time_limit",
        "aborted_by_shooter",
    ]
    assert [f.key for f in describe_form(GK_PLAIN, "shot").sections[0].series[0].fields] == [
        "time_cs",
        "standing",
    ]


# --- Definition -----------------------------------------------------------------


def section_with(base: dict, **fields: object) -> dict:
    data = copy.deepcopy(base)
    data["variant"]["abschnitte"][0].update(fields)
    return data


PRAEZISION_UNFINISHED = definitions.praezision()
PRAEZISION_UNFINISHED["scoring"]["unbeendete_serie"] = "ringe_bis_dahin_zeit_letzter_schuss"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            section_with(GK_PLAIN, zuschlag_stoerung_vor_erstem_schuss_s=50),
            "braucht zeit_bei_abbruch_s",
        ),
        (section_with(GK_PLAIN, ringwerte=[10, 0]), "ringwerte braucht schuss_je_serie"),
        (section_with(SPEED_PLAIN, ringwerte=[10, 10]), "ringwerte enthält einen Wert mehrfach"),
        (section_with(SPEED_PLAIN, ringwerte=[11]), "ringwerte"),
        (section_with(SPEED_PLAIN, ringwerte=[]), "ringwerte"),
        (
            section_with(SPEED_PLAIN, zeit_bei_abbruch_s=60),
            "zeit_bei_abbruch_s wird vom Modell „ringe_minus_zeit“ nicht ausgewertet",
        ),
        (
            PRAEZISION_UNFINISHED,
            "scoring.unbeendete_serie: wird vom Modell „ringe“ nicht ausgewertet",
        ),
    ],
)
def test_invalid_rule_fields(data: dict, message: str) -> None:
    with pytest.raises(DefinitionError) as caught:
        describe_form(data, "shot")
    assert any(message in problem for problem in caught.value.problems), caught.value.problems


# --- Eigenschaft ----------------------------------------------------------------


@pytest.mark.parametrize("seed", range(40))
def test_abort_is_never_better_than_regular_series_within_limit(seed: int) -> None:
    rng = random.Random(seed)
    others = [{"time_cs": rng.randint(300, 6000), "standing": rng.randint(0, 5)} for _ in range(3)]
    time_cs, standing = rng.randint(1, 6000), rng.randint(0, 5)
    regular = rank_key(
        GK, compute(GK, "shot", fallscheibe({"time_cs": time_cs, "standing": standing}, *others))
    )

    for status in ("time_limit", "aborted_by_shooter"):
        series = {"status": status, "standing": standing}
        aborted = rank_key(GK, compute(GK, "shot", fallscheibe(series, *others)))
        assert aborted <= regular, status
    malfunction = {"status": "malfunction_before_first_shot"}
    assert rank_key(GK, compute(GK, "shot", fallscheibe(malfunction, *others))) <= regular
