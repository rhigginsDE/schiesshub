"""Eigenschaften für beliebige Rohwerte (Zufall mit festem Startwert, reproduzierbar)."""

import random
from decimal import Decimal

import pytest

from app.scoring import ComputedResult, Contender, compute, rank, rank_key
from tests.scoring import definitions

PRAEZISION = definitions.praezision()
SPEED = definitions.speed()
FALLSCHEIBE = definitions.fallscheibe()
MEHRDISTANZ = definitions.mehrdistanz_kw()

SEEDS = range(40)
FIELD_SIZE = 8


def shots(rng: random.Random, count: int) -> list:
    return [rng.choice(["X", 10, 10, 9, 9, 9, 8, 8, 7, 6, 5, 0]) for _ in range(count)]


def praezision_raw(rng: random.Random) -> dict:
    return {"sections": {"praezision": {"series": [{"shots": shots(rng, 10)} for _ in range(2)]}}}


def speed_raw(rng: random.Random) -> dict:
    series = [
        {"shots": [rng.choice([10, 7, 0]) for _ in range(5)], "time_cs": rng.randint(300, 6000)}
        for _ in range(4)
    ]
    return {"sections": {"speed": {"series": series}}}


def fallscheibe_raw(rng: random.Random) -> dict:
    series = [{"time_cs": rng.randint(300, 6000), "standing": rng.randint(0, 4)} for _ in range(4)]
    return {"sections": {"fallscheibe": {"series": series}}}


def mehrdistanz_raw(rng: random.Random) -> dict:
    return {
        "sections": {
            "fertigkeit": {"series": [{"shots": shots(rng, 5)} for _ in range(4)]},
            "parcours": {
                "series": [{"shots": shots(rng, 5)} for _ in range(4)],
                "time_cs": rng.randint(5000, 15000),
            },
        }
    }


def better(shot: int | str) -> int | str:
    """Der nächsthöhere Ringwert; über der 10 kommt der Innenzehner."""
    return "X" if shot in (10, "X") else int(shot) + 1


def place_of(definition_: dict, raws: list[dict], index: int) -> int:
    contenders = [
        Contender(id=str(i), key=rank_key(definition_, compute(definition_, "shot", raw)))
        for i, raw in enumerate(raws)
    ]
    placement = next(p for p in rank(contenders) if p.id == str(index))
    assert placement.place is not None
    return placement.place


@pytest.mark.parametrize("seed", SEEDS)
def test_more_rings_never_worsen_the_place(seed: int) -> None:
    rng = random.Random(seed)
    field = [praezision_raw(rng) for _ in range(FIELD_SIZE)]
    before = place_of(PRAEZISION, field, 0)

    series = field[0]["sections"]["praezision"]["series"][rng.randint(0, 1)]["shots"]
    position = rng.randrange(10)
    series[position] = better(series[position])

    assert place_of(PRAEZISION, field, 0) <= before


@pytest.mark.parametrize("seed", SEEDS)
def test_extra_standing_target_never_improves_the_place(seed: int) -> None:
    rng = random.Random(seed)
    field = [fallscheibe_raw(rng) for _ in range(FIELD_SIZE)]
    before = place_of(FALLSCHEIBE, field, 0)

    field[0]["sections"]["fallscheibe"]["series"][rng.randrange(4)]["standing"] += 1

    assert place_of(FALLSCHEIBE, field, 0) >= before


@pytest.mark.parametrize("seed", SEEDS)
def test_more_time_never_improves_speed_or_fallscheibe(seed: int) -> None:
    rng = random.Random(seed)
    for definition_, raw, section in (
        (SPEED, speed_raw(rng), "speed"),
        (FALLSCHEIBE, fallscheibe_raw(rng), "fallscheibe"),
    ):
        before = rank_key(definition_, compute(definition_, "shot", raw))
        raw["sections"][section]["series"][rng.randrange(4)]["time_cs"] += rng.randint(1, 500)
        assert rank_key(definition_, compute(definition_, "shot", raw)) <= before


@pytest.mark.parametrize("seed", SEEDS)
def test_parcours_time_never_helps_and_result_never_below_fertigkeit(seed: int) -> None:
    rng = random.Random(seed)
    raw = mehrdistanz_raw(rng)
    before = compute(MEHRDISTANZ, "shot", raw)
    raw["sections"]["parcours"]["time_cs"] += rng.randint(1, 3000)
    after = compute(MEHRDISTANZ, "shot", raw)

    assert after.score <= before.score
    assert after.sections[1].result >= Decimal(0)
    assert after.score >= after.sections[0].result


@pytest.mark.parametrize("seed", SEEDS)
def test_shot_order_does_not_matter_and_json_round_trip_keeps_the_key(seed: int) -> None:
    rng = random.Random(seed)
    raw = praezision_raw(rng)
    shuffled = {
        "sections": {
            "praezision": {
                "series": [
                    {"shots": rng.sample(s["shots"], len(s["shots"]))}
                    for s in raw["sections"]["praezision"]["series"]
                ]
            }
        }
    }
    result = compute(PRAEZISION, "shot", raw)

    assert compute(PRAEZISION, "shot", shuffled).score == result.score
    stored = ComputedResult.model_validate(result.model_dump(mode="json"))
    assert rank_key(PRAEZISION, stored) == rank_key(PRAEZISION, result)


@pytest.mark.parametrize("seed", SEEDS)
def test_series_sum_gives_same_score_as_single_shots(seed: int) -> None:
    rng = random.Random(seed)
    raw = praezision_raw(rng)
    summed = {
        "sections": {
            "praezision": {
                "series": [
                    {
                        "sum": sum(10 if v == "X" else v for v in s["shots"]),
                        "tens": sum(v in (10, "X") for v in s["shots"]),
                        "inner_tens": s["shots"].count("X"),
                    }
                    for s in raw["sections"]["praezision"]["series"]
                ]
            }
        }
    }
    by_shot = compute(PRAEZISION, "shot", raw)
    by_sum = compute(PRAEZISION, "series", summed)

    assert (by_sum.score, by_sum.tens, by_sum.inner_tens) == (
        by_shot.score,
        by_shot.tens,
        by_shot.inner_tens,
    )
    assert rank_key(PRAEZISION, by_sum)[:3] == rank_key(PRAEZISION, by_shot)[:3]
