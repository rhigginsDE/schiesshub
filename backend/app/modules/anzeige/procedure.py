"""Ablauf einer Disziplin für die Standanzeige: Abschnitte, Serien, Positionen und Abweichungen.

Quelle ist die Definition des Wettbewerbs (die Kopie im Turnier, nicht der Katalog). Abweichungen
vom Sporthandbuch liefert `turnier.service.catalog_diff_of`.
"""

from app.modules.anzeige.schemas import (
    FeedPosition,
    FeedProcedure,
    FeedSection,
    FeedSeriesStep,
    FeedStance,
)
from app.modules.katalog.fileformat import Abschnitt, Anschlag, Position, Wertung
from app.modules.turnier.models import Competition
from app.modules.turnier.schemas import CatalogDiffOut, CompetitionDefinition

HAND_TEXT = {
    "beidhaendig": "beidhändig",
    "einhaendig": "einhändig (Hand frei wählbar)",
    "starke_hand": "nur starke Hand",
    "schwache_hand": "nur schwache Hand",
}
MODEL_TEXT = {
    "ringe": "Ringe",
    "ringe_minus_zeit": "Ringe minus Zeit",
    "ringe_mit_zeitabzug": "Ringe mit Zeitabzug",
    "zeit_plus_zuschlaege": "Zeit plus Zuschläge",
}
DIRECTION_TEXT = {"absteigend": "höher ist besser", "aufsteigend": "niedriger ist besser"}


def number(value: float) -> str:
    """150 → „150“, 1.5 → „1,5“."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).replace(".", ",")


def enumerate_de(values: list[int]) -> str:
    """[2] → „2“, [2, 4] → „2 und 4“, [1, 2, 4] → „1, 2 und 4“."""
    items = [str(value) for value in values]
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} und {items[-1]}"


def _stance(anschlag: Anschlag) -> FeedStance:
    text = anschlag.haltung
    if anschlag.hand is not None:
        text = f"{text}, {HAND_TEXT[anschlag.hand]}"
    return FeedStance(haltung=anschlag.haltung, hand=anschlag.hand, text=text)


def _position(position: Position, distance: float | None) -> FeedPosition:
    stances = [_stance(anschlag) for anschlag in position.anschlaege]
    return FeedPosition(
        nr=position.nr,
        distance_m=position.distanz_m if position.distanz_m is not None else distance,
        stances=stances,
        target=position.scheibe,
        text=" oder ".join(stance.text for stance in stances),
    )


def _summary(section: Abschnitt) -> str:
    parts = [f"{section.serien} {'Serie' if section.serien == 1 else 'Serien'}"]
    if section.schuss_je_serie is not None:
        parts.append(f"je {section.schuss_je_serie} Schuss")
    elif section.max_schuss_je_serie is not None:
        parts.append(f"je höchstens {section.max_schuss_je_serie} Schuss")
    if section.ziele_je_serie is not None:
        parts.append(f"je {section.ziele_je_serie} Ziele")
    if section.zeit_je_serie_s is not None:
        parts.append(f"je {number(section.zeit_je_serie_s)} s")
    elif section.zeiten_s is not None:
        parts.append(f"Zeiten {', '.join(number(value) for value in section.zeiten_s)} s")
    elif section.max_zeit_je_serie_s is not None:
        parts.append(f"höchstens {number(section.max_zeit_je_serie_s)} s je Serie")
    if section.zeit_wird_gemessen:
        parts.append("auf Zeit")
    if section.sollzeit_s is not None:
        parts.append(f"Sollzeit {number(section.sollzeit_s)} s")
    if section.distanzen_m is not None and section.positionen is None:
        parts.append(f"Distanzen {', '.join(number(value) for value in section.distanzen_m)} m")
    if section.serien_gewertet is not None and section.serien_gewertet < section.serien:
        counted = section.serien_gewertet
        parts.append(
            "gewertet wird die erste Serie"
            if counted == 1
            else f"gewertet werden die ersten {counted} Serien"
        )
    if section.trefferaufnahme_nach:
        parts.append(f"Trefferaufnahme nach Serie {enumerate_de(section.trefferaufnahme_nach)}")
    return " · ".join(parts)


def _series(section: Abschnitt) -> list[FeedSeriesStep]:
    steps = []
    reviews = set(section.trefferaufnahme_nach or [])
    for index in range(section.serien):
        distance = section.distanzen_m[index] if section.distanzen_m is not None else None
        position = (
            _position(section.positionen[index], distance)
            if section.positionen is not None
            else None
        )
        if position is not None and distance is None:
            distance = position.distance_m
        if section.zeiten_s is not None:
            time_s = section.zeiten_s[index]
        else:
            time_s = section.zeit_je_serie_s
        steps.append(
            FeedSeriesStep(
                number=index + 1,
                counted=section.serien_gewertet is None or index < section.serien_gewertet,
                shots=section.schuss_je_serie,
                time_s=time_s,
                distance_m=distance,
                position=position,
                hit_review_after=index + 1 in reviews,
            )
        )
    return steps


def _notes(scoring: Wertung) -> list[str]:
    notes = []
    if scoring.abzug_je_voller_sekunde_ueber_sollzeit is not None:
        notes.append(
            f"−{number(scoring.abzug_je_voller_sekunde_ueber_sollzeit)} Ring je volle Sekunde "
            "über der Sollzeit"
        )
    return notes


def build_procedure(competition: Competition, diff: CatalogDiffOut) -> FeedProcedure:
    definition = CompetitionDefinition.model_validate(competition.definition)
    scoring = definition.scoring
    by_section: dict[str, list[str]] = {}
    for deviation in diff.differences:
        if deviation.section_id is not None:
            by_section.setdefault(deviation.section_id, []).append(deviation.text)
    sections = [
        FeedSection(
            id=section.id,
            name=section.name,
            series_count=section.serien,
            counted_series=section.serien_gewertet,
            shots_per_series=section.schuss_je_serie,
            time_per_series_s=section.zeit_je_serie_s,
            target_time_s=section.sollzeit_s,
            time_measured=bool(section.zeit_wird_gemessen),
            summary=_summary(section),
            deviations=by_section.get(section.id, []),
            series=_series(section),
        )
        for section in definition.variant.abschnitte
    ]
    return FeedProcedure(
        competition_id=competition.id,
        competition_name=competition.name,
        catalog_code=competition.catalog_code,
        variant_name=definition.variant.name,
        description=definition.ablauf_beschreibung,
        scoring=f"{MODEL_TEXT[scoring.modell]}, {DIRECTION_TEXT[scoring.rangfolge]}",
        notes=_notes(scoring),
        deviates=diff.deviates,
        deviations=[deviation.text for deviation in diff.differences],
        sections=sections,
    )
