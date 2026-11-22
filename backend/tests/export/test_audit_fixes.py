"""Befunde aus dem Audit (22.11.2026): abgebrochene Starts in der Siegerliste, Spalten bei
Zeitwertung, deutsche Texte statt interner Schlüssel. Alle Namen sind erfunden."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.export.conftest import Api, Setup, as_dicts, make_setup, read_csv, shots
from tests.export.pdftext import read_pdf
from tests.export.test_api import export, person_start


def falls(*series: dict[str, Any]) -> dict[str, Any]:
    return {"sections": {"fallscheibe": {"series": list(series)}}}


def serie(seconds: int, standing: int = 0, **extra: Any) -> dict[str, Any]:
    return {"time_cs": seconds * 100, "standing": standing, **extra}


async def give_up(api: Api, tid: str, sid: str, raw: dict[str, Any]) -> None:
    path = f"/tournaments/{tid}/starts/{sid}"
    await api.ok("POST", f"{path}/call")
    await api.ok("PUT", f"{path}/raw", json={"raw": raw, "base_seq": 0})
    await api.ok("POST", f"{path}/result/abort", json={"abort_reason": "dnf"})


async def fallscheibe(api: Api) -> Setup:
    return await make_setup(
        api, catalog_federation="bds", catalog_code="4401", capture_mode="series"
    )


async def test_winners_dnf_with_smaller_time_is_not_first(api: Api) -> None:
    setup = await fallscheibe(api)
    alone_class = await api.klass(setup.tid, "alters")
    bernd = await person_start(api, setup, "Bernd Beispiel")
    dieter = await person_start(api, setup, "Dieter Beispiel")
    emil = await person_start(api, setup, "Emil Beispiel")
    allein = await person_start(api, setup, "Anton Allein", class_id=alone_class)
    await api.shoot(setup.tid, bernd, falls(serie(12), serie(12), serie(12), serie(12)))
    await give_up(api, setup.tid, dieter, falls(serie(20), serie(20)))
    await api.abort(setup.tid, emil, "dns")
    await give_up(api, setup.tid, allein, falls(serie(10), serie(10)))

    rows = as_dicts(read_csv((await api.get(export(setup, "winners.csv"))).content))
    assert [(r["Platz"], r["Name"], r["Status"], r["Ergebnis"]) for r in rows] == [
        ("1", "Bernd Beispiel", "endgültig", "48,00"),
        ("", "Dieter Beispiel", "aufgegeben", ""),
        ("", "Emil Beispiel", "nicht angetreten", ""),
        ("", "Anton Allein", "aufgegeben", ""),
    ]
    # Reine Zeitwertung: keine Spalten für Zehner.
    assert "Zehner" not in rows[0]
    assert "Innenzehner" not in rows[0]

    only_ranked = as_dicts(
        read_csv((await api.get(export(setup, "winners.csv"), include_aborted="false")).content)
    )
    assert [r["Name"] for r in only_ranked] == ["Bernd Beispiel"]

    text = read_pdf((await api.get(export(setup, "winners.pdf"))).content).text
    lines = text.splitlines()
    assert lines.count("1.") == 1
    assert lines.index("Bernd Beispiel") < lines.index("Dieter Beispiel")
    assert "aufgegeben" in text
    without = read_pdf(
        (await api.get(export(setup, "winners.pdf"), include_aborted="false")).content
    ).text
    assert "Dieter Beispiel" not in without


async def test_ring_scoring_keeps_tens_columns(api: Api) -> None:
    setup = await make_setup(api)
    a = await person_start(api, setup, "Anna Beispiel")
    await api.shoot(setup.tid, a, shots([10] * 5, [9] * 5))
    (row,) = as_dicts(read_csv((await api.get(export(setup, "winners.csv"))).content))
    assert (row["Zehner"], row["Innenzehner"]) == ("5", "0")
    (raw,) = as_dicts(read_csv((await api.get(export(setup, "results.csv"))).content))
    assert raw["Zehner"] == "5"


async def test_series_status_and_states_in_german(api: Api) -> None:
    setup = await fallscheibe(api)
    gustav = await person_start(api, setup, "Gustav Beispiel")
    await api.shoot(
        setup.tid,
        gustav,
        falls(
            serie(10),
            {"status": "time_limit", "standing": 2},
            {"status": "malfunction_before_first_shot"},
            serie(10),
        ),
    )
    emil = await person_start(api, setup, "Emil Beispiel")
    await api.abort(setup.tid, emil, "dns")

    results = (await api.get(export(setup, "results.csv"))).content.decode("utf-8-sig")
    for key in ("time_limit", "malfunction", "aborted", "final", ";dns", "normal"):
        assert key not in results, key
    rows = as_dicts(read_csv((await api.get(export(setup, "results.csv"))).content))
    assert rows[0]["Serienstatus"] == (
        "2: Zeitlimit erreicht (Abbruch durch den Schießleiter); "
        "3: Waffenstörung vor dem ersten Wertungsschuss"
    )
    assert (rows[0]["Status"], rows[1]["Status"], rows[1]["Abbruchgrund"]) == (
        "abgeschlossen",
        "abgebrochen",
        "nicht angetreten",
    )
    assert "Zehner" not in rows[0]

    winners = as_dicts(read_csv((await api.get(export(setup, "winners.csv"))).content))
    assert winners[0]["Serienstatus"] == rows[0]["Serienstatus"]
    pdf = read_pdf((await api.get(export(setup, "winners.pdf"))).content).text
    flowing = " ".join(pdf.split())
    assert "S3: Waffenstörung vor dem ersten Wertungsschuss" in flowing, flowing
    assert "malfunction" not in pdf


async def test_old_settings_without_timezone(api: Api, engine: AsyncEngine) -> None:
    setup = await fallscheibe(api)
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE tournament SET settings = '{}'::jsonb WHERE id = :id"), {"id": setup.tid}
        )
    for name in ("winners.csv", "winners.pdf", "startlist.csv", "startlist.pdf", "results.csv"):
        await api.get(export(setup, name))
