"""Ablauf-Kurzform der Ausschreibung: Zeitangaben stehen so drin, wie die Definition sie nennt."""

from typing import Any

import yaml

from app.modules.turnier.announcement import _sections
from app.modules.turnier.schemas import CompetitionDefinition
from tests.conftest import REAL_CATALOG_DIR


def _definition(abschnitt: dict[str, Any], **scoring: Any) -> CompetitionDefinition:
    return CompetitionDefinition.model_validate(
        {
            "variant": {"id": "v", "name": "V", "abschnitte": [abschnitt]},
            "scoring": {"modell": "ringe", "rangfolge": "absteigend", "geprueft": False, **scoring},
        }
    )


def test_fallscheibe_from_catalog_names_time_limit_and_penalties() -> None:
    group = yaml.safe_load(
        (REAL_CATALOG_DIR / "bds" / "gruppen" / "flinte-15m-fallscheibe.yaml").read_text("utf-8")
    )
    variant = group["ablaeufe"]["fallscheibe-max6"]["varianten"][0]
    definition = CompetitionDefinition.model_validate(
        {"variant": variant, "scoring": group["wertung"]}
    )
    (section,) = _sections(definition)
    assert section.summary == (
        "Fallscheibe: 4 Serien, höchstens 1 Min. je Serie, Zuschlag 10 s je stehender Scheibe, "
        "Serienzeit bei Zeitlimit oder Abbruch 1 Min."
    )


def test_only_values_from_the_definition_are_printed() -> None:
    (section,) = _sections(
        _definition({"id": "a", "name": "Lauf", "serien": 3, "schuss_je_serie": 5})
    )
    assert section.summary == "Lauf: 3 Serien à 5 Schuss"
    # Eine feste Zeit je Serie geht vor der Höchstzeit; beide zugleich wären doppelt.
    (section,) = _sections(
        _definition(
            {
                "id": "a",
                "name": "Speed",
                "serien": 2,
                "schuss_je_serie": 5,
                "zeit_je_serie_s": 90,
                "max_zeit_je_serie_s": 120,
            }
        )
    )
    assert section.summary == "Speed: 2 Serien à 5 Schuss, je 1 Min. 30 s"


def test_series_words_come_from_the_federation_terms() -> None:
    """„Serie“ aus dem Begriffssatz; BDS (SHB K 3.03) und DSB (SpO 0.12.1) sagen im Ablauf
    beide „Serie“. Eine Serie steht in der Einzahl."""
    from app.core.begriffe import begriffe_fuer

    single = _definition({"id": "a", "name": "Lauf", "serien": 1, "schuss_je_serie": 10})
    (section,) = _sections(single, begriffe_fuer("dsb"))
    assert section.summary == "Lauf: 1 Serie à 10 Schuss"
    many = _definition({"id": "a", "name": "Lauf", "serien": 6, "schuss_je_serie": 10})
    assert _sections(many, begriffe_fuer("bds"))[0].summary == "Lauf: 6 Serien à 10 Schuss"
