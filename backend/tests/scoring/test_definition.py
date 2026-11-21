"""Strenges Einlesen der Definition: Unbekanntes oder Unpassendes ist ein klarer Fehler."""

import copy
from collections.abc import Callable

import pytest

from app.scoring import DefinitionError, describe_form, load_definition, model_names
from tests.scoring import definitions

PRAEZISION = definitions.praezision()
FALLSCHEIBE = definitions.fallscheibe(max_schuss=6)
SPEED = definitions.speed()
MEHRDISTANZ = definitions.mehrdistanz_kw()


def changed(base: dict, change: Callable[[dict], None]) -> dict:
    data = copy.deepcopy(base)
    change(data)
    return data


def section(data: dict) -> dict:
    return data["variant"]["abschnitte"][0]


def test_known_models() -> None:
    assert model_names() == [
        "ringe",
        "ringe_minus_zeit",
        "ringe_mit_zeitabzug",
        "zeit_plus_zuschlaege",
    ]


CASES = [
    (
        PRAEZISION,
        lambda d: d["scoring"].update(modell="treffer"),
        "scoring.modell: unbekanntes Wertungsmodell „treffer“ (bekannt: ringe, ringe_minus_zeit, "
        "ringe_mit_zeitabzug, zeit_plus_zuschlaege)",
    ),
    (
        PRAEZISION,
        lambda d: d["scoring"].update(streichergebnisse=1),
        "scoring.streichergebnisse: unbekanntes Feld",
    ),
    (
        PRAEZISION,
        lambda d: section(d).update(kaliber="9 mm"),
        "variant.abschnitte[0].kaliber: unbekanntes Feld",
    ),
    (PRAEZISION, lambda d: d.update(ablauf="x"), "ablauf: unbekanntes Feld"),
    (PRAEZISION, lambda d: d.pop("scoring"), "scoring: Pflichtfeld fehlt"),
    (
        PRAEZISION,
        lambda d: section(d).update(serien="2"),
        "variant.abschnitte[0].serien: Input should be a valid integer",
    ),
    (
        PRAEZISION,
        lambda d: section(d).update(zeit_je_serie_s=True),
        "variant.abschnitte[0].zeit_je_serie_s: Zahl erwartet",
    ),
    (
        PRAEZISION,
        lambda d: d["scoring"].update(gleichstand=["zehner", "los"]),
        "scoring.gleichstand[1]: unbekanntes Gleichstandskriterium „los“",
    ),
    (
        PRAEZISION,
        lambda d: d["scoring"].update(gleichstand=["parcours_zeit"]),
        "scoring.gleichstand[0]: „parcours_zeit“ ist beim Modell „ringe“ nicht anwendbar",
    ),
    (
        PRAEZISION,
        lambda d: d["scoring"].update(gleichstand=["zehner", "zehner"]),
        "scoring.gleichstand[1]: „zehner“ steht mehrfach in der Liste",
    ),
    (
        FALLSCHEIBE,
        lambda d: d["scoring"].update(gleichstand=["zehner"]),
        "„zehner“ ist beim Modell „zeit_plus_zuschlaege“ nicht anwendbar",
    ),
    (
        PRAEZISION,
        lambda d: d["scoring"].update(rangfolge="aufsteigend"),
        "scoring.rangfolge: Modell „ringe“ wertet „absteigend“, nicht „aufsteigend“",
    ),
    (
        PRAEZISION,
        lambda d: d["scoring"].update(min_teilergebnis=0),
        "scoring.min_teilergebnis: wird vom Modell „ringe“ nicht ausgewertet",
    ),
    (
        FALLSCHEIBE,
        lambda d: d["scoring"].update(zeit_rundung="summe_abrunden"),
        "scoring.zeit_rundung: wird vom Modell „zeit_plus_zuschlaege“ nicht ausgewertet",
    ),
    (
        SPEED,
        lambda d: d["scoring"].update(zeit_rundung="aufrunden"),
        "scoring.zeit_rundung: Input should be 'summe_abrunden'",
    ),
    (
        PRAEZISION,
        lambda d: section(d).update(zeit_wird_gemessen=True),
        "zeit_wird_gemessen: das Modell „ringe“ wertet keine gemessene Zeit",
    ),
    (
        PRAEZISION,
        lambda d: section(d).update(zuschlag_je_stehender_scheibe_s=10, ziele_je_serie=5),
        "zuschlag_je_stehender_scheibe_s wird vom Modell „ringe“ nicht ausgewertet",
    ),
    (
        PRAEZISION,
        lambda d: section(d).pop("schuss_je_serie"),
        "schuss_je_serie fehlt (das Modell wertet Ringe je Schuss)",
    ),
    (
        FALLSCHEIBE,
        lambda d: section(d).update(schuss_je_serie=5),
        "schuss_je_serie und max_schuss_je_serie schließen sich aus",
    ),
    (
        FALLSCHEIBE,
        lambda d: section(d).pop("ziele_je_serie"),
        "zuschlag_je_stehender_scheibe_s braucht ziele_je_serie",
    ),
    (
        FALLSCHEIBE,
        lambda d: section(d).pop("zeit_wird_gemessen"),
        "max_zeit_je_serie_s braucht zeit_wird_gemessen: true",
    ),
    (
        FALLSCHEIBE,
        lambda d: section(d).update(zuschlag_je_stehender_scheibe_s=10.005),
        "nicht auf Hundertstelsekunden genau",
    ),
    (
        SPEED,
        lambda d: [
            (s.pop("zeit_wird_gemessen"), s.pop("max_zeit_je_serie_s"))
            for s in d["variant"]["abschnitte"]
        ],
        "zeit_wird_gemessen: true fehlt (das Modell zieht die Zeit je Serie ab)",
    ),
    (
        PRAEZISION,
        lambda d: section(d).update(zeiten_s=[300]),
        "zeiten_s hat 1 Einträge, erwartet werden 2",
    ),
    (
        PRAEZISION,
        lambda d: d["variant"]["abschnitte"].append(copy.deepcopy(section(d))),
        "Abschnitt-ID mehrfach vergeben: praezision",
    ),
    (
        MEHRDISTANZ,
        lambda d: d["variant"]["abschnitte"][1].pop("sollzeit_s"),
        "sollzeit_s fehlt (Abzug ohne Sollzeit nicht berechenbar)",
    ),
    (
        MEHRDISTANZ,
        lambda d: d["scoring"].update(abzug_je_voller_sekunde_ueber_sollzeit=0.333),
        "abzug_je_voller_sekunde_ueber_sollzeit: höchstens zwei Nachkommastellen",
    ),
]


@pytest.mark.parametrize(("base", "change", "message"), CASES)
def test_definition_error(base: dict, change: Callable[[dict], None], message: str) -> None:
    with pytest.raises(DefinitionError) as caught:
        load_definition(changed(base, change))
    assert any(message in problem for problem in caught.value.problems), caught.value.problems


def test_unknown_capture_mode() -> None:
    with pytest.raises(DefinitionError, match="capture_mode: „scheibe“ unbekannt"):
        describe_form(PRAEZISION, "scheibe")


def test_float_seconds_from_yaml_stay_exact() -> None:
    data = changed(FALLSCHEIBE, lambda d: section(d).update(zuschlag_je_stehender_scheibe_s=2.5))
    plan = load_definition(data).sections[0]
    assert plan.penalty_cs == 250


def test_geprueft_is_accepted_as_information() -> None:
    assert load_definition(PRAEZISION).scoring.geprueft is True
