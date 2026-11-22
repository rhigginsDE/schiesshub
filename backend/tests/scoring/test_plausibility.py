"""Plausibilität gemessener Zeiten (`validate_raw`).

Eine gemessene Zeit über dem Plausibilitätsgrenzwert ist ein Fehler, keine Warnung: Standard
das Dreifache des Zeitlimits (`max_zeit_je_serie_s` bzw. `max_gesamtzeit_s`), ohne Limit eine
Stunde. Überschreibbar je Abschnitt mit `zeit_plausibel_faktor` und `zeit_plausibel_max_s`.
"""

import copy

import pytest

from app.scoring import DefinitionError, compute, validate_raw
from app.scoring.errors import InvalidRawError
from tests.scoring import definitions


def fallscheibe(**section: object) -> dict:
    data = definitions.fallscheibe()
    data["variant"]["abschnitte"][0].update(section)
    return data


def raw(*times: int | None, status: str | None = None) -> dict:
    series = []
    for time_cs in times:
        item: dict = {"standing": 0}
        if time_cs is not None:
            item["time_cs"] = time_cs
        if status is not None:
            item["status"] = status
        series.append(item)
    return {"sections": {"fallscheibe": {"series": series}}}


def messages(issues: list) -> list[tuple[str, str]]:
    return [(issue.path, issue.message) for issue in issues]


def test_series_time_far_over_limit_is_an_error() -> None:
    issues = validate_raw(fallscheibe(zeit_bei_abbruch_s=60), "series", raw(1000, 999900))
    assert messages(issues) == [
        (
            "sections.fallscheibe.series[1].time_cs",
            "Serie 2: 9999,00 s ist unplausibel – höchstens 180 s; bei überschrittenem "
            "Zeitlimit den Status „Zeitlimit erreicht“ wählen",
        )
    ]
    with pytest.raises(InvalidRawError):
        compute(fallscheibe(zeit_bei_abbruch_s=60), "series", raw(1000, 999900))


def test_limit_without_time_limit_status_has_a_neutral_hint() -> None:
    (issue,) = validate_raw(definitions.fallscheibe(), "series", raw(18001))
    assert issue.message == (
        "Serie 1: 180,01 s ist unplausibel – höchstens 180 s; bitte die Zeit prüfen"
    )


def test_up_to_the_plausibility_limit_only_a_warning() -> None:
    assert validate_raw(definitions.fallscheibe(), "series", raw(18000)) == []
    result = compute(definitions.fallscheibe(), "series", raw(18000))
    assert [w.path for w in result.warnings] == ["sections.fallscheibe.series[0].time_cs"]


def test_factor_and_absolute_limit_can_be_overridden() -> None:
    assert validate_raw(fallscheibe(zeit_plausibel_faktor=5), "series", raw(29000)) == []
    (issue,) = validate_raw(fallscheibe(zeit_plausibel_max_s=90), "series", raw(9001))
    assert "höchstens 90 s" in issue.message


def test_without_time_limit_one_hour_is_the_maximum() -> None:
    data = definitions.fallscheibe()
    del data["variant"]["abschnitte"][0]["max_zeit_je_serie_s"]
    assert validate_raw(data, "series", raw(360000)) == []
    (issue,) = validate_raw(data, "series", raw(360001))
    assert "höchstens 3600 s" in issue.message


def test_section_time_is_checked_against_its_limit() -> None:
    data = definitions.mehrdistanz_kw()  # Parcours: max_gesamtzeit_s 160
    section = {"series": [None] * 4, "time_cs": 48001}
    issues = validate_raw(data, "shot", {"sections": {"parcours": section}})
    assert messages(issues) == [
        (
            "sections.parcours.time_cs",
            "Parcours: Gesamtzeit 480,01 s ist unplausibel – höchstens 480 s; bitte die Zeit "
            "prüfen",
        )
    ]


def test_zero_and_negative_times() -> None:
    (zero,) = validate_raw(definitions.fallscheibe(), "series", raw(0))
    assert zero.message == "Serie 1: Zeit: in Hundertstelsekunden als ganze Zahl größer 0"
    assert validate_raw(definitions.fallscheibe(), "series", raw(-5))
    # Status ohne gemessene Zeit (Zeitlimit erreicht): eine 0 im Zeitfeld stört nicht.
    data = fallscheibe(zeit_bei_abbruch_s=60)
    assert validate_raw(data, "series", raw(0, 0, 0, 0, status="time_limit"), partial=False) == []
    assert validate_raw(data, "series", raw(-1, status="time_limit"))


def test_invalid_override_is_a_definition_error() -> None:
    data = copy.deepcopy(definitions.fallscheibe())
    data["variant"]["abschnitte"][0]["zeit_plausibel_faktor"] = 0
    with pytest.raises(DefinitionError):
        validate_raw(data, "series", raw(1000))
