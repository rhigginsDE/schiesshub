"""PDF-Ausgabe direkt aus einem `Report`: Seiten, Kopf je Seite, Querformat, Schrift, Rückfall."""

import re
from datetime import UTC, date, datetime

import pytest

from app.modules.export import fonts as font_module
from app.modules.export import pdfout
from app.modules.export.records import Meta
from app.modules.export.tables import Column, Report, Row, Section, Table
from tests.export.pdftext import read_pdf

META = Meta(
    "Vereinspokal 2027",
    "SV Musterstadt",
    date(2027, 3, 6),
    date(2027, 3, 6),
    datetime(2027, 3, 6, 15, 0, tzinfo=UTC),
    "public",
)


def report(rows: int, series: int = 2, names: str = "Person") -> Report:
    columns = (
        Column("Platz", "right"),
        Column("Nr.", "right"),
        Column("Name", wrap=True),
        Column("Verein", wrap=True),
        Column("Ergebnis (Ringe)", "right"),
        *(Column(f"S{n}", "right") for n in range(1, series + 1)),
    )
    body = tuple(
        Row(
            (
                f"{i}.",
                str(i),
                f"{names} {i:03d}",
                "Schützenverein Musterstadt 1888 e. V.",
                "95",
                *("48" for _ in range(series)),
            )
        )
        for i in range(1, rows + 1)
    )
    table = Table("Offene Klasse", columns, body)
    return Report("Siegerliste", META, (Section("1001 · Pistole bis 9 mm", tables=(table,)),))


def media_box(content: bytes) -> tuple[float, float]:
    match = re.search(rb"/MediaBox \[ 0 0 ([\d.]+) ([\d.]+) \]", content)
    assert match is not None
    return float(match.group(1)), float(match.group(2))


def test_long_table_repeats_header_and_numbers_pages() -> None:
    content = pdfout.render_pdf(report(120))
    pdf = read_pdf(content)
    total = len(pdf.pages)
    assert total >= 3
    width, height = media_box(content)
    assert width < height  # hoch
    seen = []
    for number, page in enumerate(pdf.pages, start=1):
        lines = page.splitlines()
        assert f"Seite {number} von {total}" in lines
        assert any("erstellt mit Schiesshub" in line for line in lines)
        # Tabellenkopf auf jeder Seite
        assert "Platz" in lines
        assert "Ergebnis (Ringe)" in lines
        if number > 1:
            assert "Siegerliste – Vereinspokal 2027" in lines
        seen += [line for line in lines if line.startswith("Person ")]
    # Jede Zeile genau einmal, keine zerrissen
    assert seen == [f"Person {i:03d}" for i in range(1, 121)]
    assert "Erstellt am 06.03.2027, 16:00 Uhr · erstellt mit Schiesshub" in pdf.pages[0]


def test_wide_table_turns_landscape() -> None:
    portrait = pdfout.render_pdf(report(3, series=2))
    width, height = media_box(portrait)
    assert width < height
    wide = pdfout.render_pdf(report(3, series=12))
    width, height = media_box(wide)
    assert width > height
    text = read_pdf(wide).text
    assert "S12" in text.splitlines()


def test_empty_report_has_hint() -> None:
    empty = Report("Startliste", META, (), empty_text="Für diese Auswahl gibt es keine Starts.")
    pdf = read_pdf(pdfout.render_pdf(empty))
    assert len(pdf.pages) == 1
    assert "Für diese Auswahl gibt es keine Starts." in pdf.text


@pytest.mark.skipif(
    not (font_module.DEJAVU_DIR / "DejaVuSans.ttf").is_file(),
    reason="DejaVu Sans fehlt im Image (Paket fonts-dejavu-core, deploy/backend.Dockerfile)",
)
def test_unicode_names_with_dejavu() -> None:
    names = ("Deniz Yılmaz", "Jürgen Maier", "Łukasz Čapek")
    columns = (Column("Nr.", "right"), Column("Name", wrap=True))
    rows = tuple(Row((str(i), name)) for i, name in enumerate(names, start=1))
    doc = Report("Startliste", META, (Section("Test", tables=(Table(None, columns, rows),)),))
    pdf = read_pdf(pdfout.render_pdf(doc))
    assert font_module.pdf_fonts().full_coverage
    assert any(font.endswith("DejaVuSans") for font in pdf.fonts)
    assert pdf.embedded_fonts == 2  # normal und fett
    for name in names:
        assert name in pdf.text.splitlines()


def test_font_fallback_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    missing = font_module.DEJAVU_DIR / "gibt-es-nicht"
    monkeypatch.setattr(
        font_module,
        "CANDIDATES",
        (("Fehlt", missing / "a.ttf", missing / "b.ttf"), font_module.CANDIDATES[1]),
    )
    font_module.pdf_fonts.cache_clear()
    try:
        with caplog.at_level("WARNING"):
            chosen = font_module.pdf_fonts()
        assert chosen.regular == "Vera"
        assert chosen.embedded
        assert not chosen.full_coverage
        assert "fonts-dejavu-core" in caplog.text
        pdf = read_pdf(pdfout.render_pdf(report(2)))
        assert "Person 001" in pdf.text
        monkeypatch.setattr(font_module, "CANDIDATES", ())
        font_module.pdf_fonts.cache_clear()
        assert font_module.pdf_fonts().regular == "Helvetica"
        assert "Person 002" in read_pdf(pdfout.render_pdf(report(2))).text
    finally:
        font_module.pdf_fonts.cache_clear()
