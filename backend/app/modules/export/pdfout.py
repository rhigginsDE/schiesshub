"""Ausgabe eines `Report` als PDF (reportlab), schlicht und gut lesbar als Aushang.

- A4 hoch; ist eine Tabelle dafür zu breit, wird das ganze Dokument quer gesetzt (und erst wenn
  auch das nicht reicht, die Schrift dieser Tabelle verkleinert, höchstens auf `MIN_SIZE`).
- Kopf auf der ersten Seite: Titel, Turniername, Veranstalter, Datum; bei vollen Namen ein
  deutlicher Hinweis „interne Liste“. Folgeseiten: Kurzkopf. Fußzeile: Erstellzeit,
  „erstellt mit Schiesshub“, „Seite x von y“.
- Tabellenkopf wiederholt sich auf Folgeseiten; Zeilen werden nie zerrissen (reportlab teilt
  Tabellen nur zwischen Zeilen), Überschriften bleiben bei ihrer Tabelle.
"""

import io
from collections.abc import Sequence
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.modules.export import tables as t
from app.modules.export.fonts import PdfFonts, pdf_fonts
from app.modules.export.formatting import date_range_de, moment_de

MARGIN_X = 14 * mm
MARGIN_TOP = 20 * mm
MARGIN_BOTTOM = 18 * mm
BODY_SIZE = 11.0
HEAD_SIZE = 10.0
MIN_SIZE = 7.5
CELL_PAD_X = 4.0
CELL_PAD_Y = 3.0
WRAP_MIN = 22 * mm
WRAP_MAX = 75 * mm
# Platz, der für eine Überschrift samt ersten Zeilen mindestens frei sein muss.
SECTION_ROOM = 55 * mm
TABLE_ROOM = 40 * mm
# Tabellen bis zu so vielen Zeilen bleiben auf einer Seite.
KEEP_ROWS = 15

GRID = colors.HexColor("#9a9a9a")
HEAD_BG = colors.HexColor("#e3e3e3")
ZEBRA = colors.HexColor("#f4f4f4")
MUTED = colors.HexColor("#666666")

_ALIGN = {"left": TA_LEFT, "right": TA_RIGHT, "center": TA_CENTER}


# --- Breiten -----------------------------------------------------------------------------


def _text_width(text: str, font: str, size: float) -> float:
    return max((stringWidth(line, font, size) for line in text.split("\n")), default=0.0)


def _column_widths(
    columns: Sequence[t.Column], rows: Sequence[t.Row], fonts: PdfFonts, size: float, avail: float
) -> tuple[list[float], float]:
    """Breiten der Spalten und die mindestens nötige Gesamtbreite.

    Feste Spalten bekommen ihre natürliche Breite; umbrechende (Name, Verein) teilen sich den
    Rest, mindestens so breit wie ihr längstes Wort.
    """
    head = size * HEAD_SIZE / BODY_SIZE
    natural: list[float] = []
    minimum: list[float] = []
    for index, column in enumerate(columns):
        cells = [row.cells[index] for row in rows]
        width = max(
            [_text_width(column.title, fonts.bold, head)]
            + [_text_width(cell, fonts.regular, size) for cell in cells]
        )
        width += 2 * CELL_PAD_X + 1
        if column.wrap:
            words = [word for cell in cells for word in cell.split()] + column.title.split()
            longest = max((stringWidth(word, fonts.regular, size) for word in words), default=0)
            low = max(WRAP_MIN * size / BODY_SIZE, longest + 2 * CELL_PAD_X + 1)
            natural.append(max(low, min(width, WRAP_MAX)))
            minimum.append(low)
        else:
            natural.append(width)
            minimum.append(width)
    needed = sum(minimum)
    wrap = [i for i, column in enumerate(columns) if column.wrap]
    total = sum(natural)
    widths = list(natural)
    if wrap and total < avail:
        # Rest auf die umbrechenden Spalten verteilen: Tabellen über die volle Breite.
        extra = (avail - total) / len(wrap)
        for i in wrap:
            widths[i] += extra
    elif wrap and total > avail and needed <= avail:
        flexible = sum(natural[i] - minimum[i] for i in wrap)
        ratio = (avail - needed) / flexible if flexible else 0
        for i in wrap:
            widths[i] = minimum[i] + (natural[i] - minimum[i]) * ratio
    return widths, needed


def _section_rows(section: t.Section) -> list[t.Row]:
    return [row for table in section.tables for row in table.rows]


def _fits(report: t.Report, fonts: PdfFonts, avail: float) -> bool:
    for section in report.sections:
        rows = _section_rows(section)
        for table in section.tables:
            _, needed = _column_widths(table.columns, rows, fonts, BODY_SIZE, avail)
            if needed > avail + 0.5:
                return False
    return True


# --- Stile ---------------------------------------------------------------------------------


def _styles(fonts: PdfFonts) -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title", fontName=fonts.bold, fontSize=22, leading=26, spaceAfter=4
        ),
        "tournament": ParagraphStyle(
            "tournament", fontName=fonts.bold, fontSize=15, leading=19, spaceAfter=2
        ),
        "meta": ParagraphStyle("meta", fontName=fonts.regular, fontSize=11, leading=15),
        "internal": ParagraphStyle(
            "internal",
            fontName=fonts.bold,
            fontSize=11,
            leading=15,
            borderColor=colors.black,
            borderWidth=1,
            borderPadding=5,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "section": ParagraphStyle(
            "section",
            fontName=fonts.bold,
            fontSize=15,
            leading=19,
            spaceBefore=14,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName=fonts.regular,
            fontSize=10.5,
            leading=14,
            textColor=MUTED,
            spaceAfter=4,
        ),
        "note": ParagraphStyle(
            "note",
            fontName=fonts.bold,
            fontSize=11,
            leading=15,
            spaceBefore=2,
            spaceAfter=4,
        ),
        "table_title": ParagraphStyle(
            "table_title",
            fontName=fonts.bold,
            fontSize=12.5,
            leading=16,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "empty": ParagraphStyle(
            "empty", fontName=fonts.regular, fontSize=11, leading=15, textColor=MUTED
        ),
        "legend": ParagraphStyle(
            "legend", fontName=fonts.regular, fontSize=9.5, leading=13, textColor=MUTED
        ),
    }


def _cell_style(fonts: PdfFonts, size: float, align: str, *, bold: bool, muted: bool) -> Any:
    return ParagraphStyle(
        f"cell-{size}-{align}-{bold}-{muted}",
        fontName=fonts.bold if bold else fonts.regular,
        fontSize=size,
        leading=size * 1.22,
        alignment=_ALIGN[align],
        textColor=MUTED if muted else colors.black,
    )


# --- Tabellen ------------------------------------------------------------------------------


def _table(table: t.Table, widths: Sequence[float], fonts: PdfFonts, size: float) -> list[Flowable]:
    head = size * HEAD_SIZE / BODY_SIZE
    header = [
        Paragraph(
            escape(column.title), _cell_style(fonts, head, column.align, bold=True, muted=False)
        )
        for column in table.columns
    ]
    data: list[list[Any]] = [header]
    for row in table.rows:
        data.append(
            [
                Paragraph(
                    escape(cell),
                    _cell_style(fonts, size, column.align, bold=False, muted=row.muted),
                )
                if column.wrap
                else cell
                for column, cell in zip(table.columns, row.cells, strict=True)
            ]
        )
    style: list[tuple[Any, ...]] = [
        ("FONT", (0, 1), (-1, -1), fonts.regular, size, size * 1.22),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), CELL_PAD_X),
        ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PAD_X),
        ("TOPPADDING", (0, 0), (-1, -1), CELL_PAD_Y),
        ("BOTTOMPADDING", (0, 0), (-1, -1), CELL_PAD_Y),
    ]
    for index, column in enumerate(table.columns):
        style.append(("ALIGN", (index, 1), (index, -1), column.align.upper()))
    for index, row in enumerate(table.rows, start=1):
        if row.muted:
            style.append(("TEXTCOLOR", (0, index), (-1, index), MUTED))
    flowable = Table(
        data, colWidths=list(widths), repeatRows=1, hAlign="LEFT", style=TableStyle(style)
    )
    return [flowable]


def _section(
    section: t.Section, styles: dict[str, ParagraphStyle], fonts: PdfFonts, avail: float
) -> list[Flowable]:
    # Überschriften nie allein unten auf der Seite: vorher Seitenwechsel, wenn wenig Platz ist.
    story: list[Flowable] = [
        CondPageBreak(SECTION_ROOM),
        Paragraph(escape(section.title), styles["section"]),
    ]
    if section.subtitle:
        story.append(Paragraph(escape(section.subtitle), styles["subtitle"]))
    story.extend(Paragraph(escape(note), styles["note"]) for note in section.notes)
    rows = _section_rows(section)
    for table in section.tables:
        block: list[Flowable] = []
        if table.title:
            block.append(Paragraph(escape(table.title), styles["table_title"]))
        if not table.rows:
            block.append(Paragraph(escape(table.empty_text or t.NO_RESULTS), styles["empty"]))
            story.append(KeepTogether(block))
            continue
        size = BODY_SIZE
        widths, needed = _column_widths(table.columns, rows, fonts, size, avail)
        if needed > avail:
            size = max(MIN_SIZE, BODY_SIZE * avail / needed)
            widths, _ = _column_widths(table.columns, rows, fonts, size, avail)
        block.extend(_table(table, widths, fonts, size))
        if len(table.rows) <= KEEP_ROWS:
            # Kurze Tabellen (eine Klasse mit wenigen Startern) nicht über zwei Seiten verteilen.
            story.append(KeepTogether(block))
        else:
            story.append(CondPageBreak(TABLE_ROOM))
            story.extend(block)
    return story


def _front(report: t.Report, styles: dict[str, ParagraphStyle]) -> list[Flowable]:
    meta = report.meta
    story: list[Flowable] = [
        Paragraph(escape(report.title), styles["title"]),
        Paragraph(escape(meta.tournament_name), styles["tournament"]),
    ]
    facts = [date_range_de(meta.date_from, meta.date_to)]
    if meta.organizer:
        facts.insert(0, f"Veranstalter: {meta.organizer}")
    story.append(Paragraph(escape(" · ".join(facts)), styles["meta"]))
    if meta.names == "full":
        story.append(
            Paragraph(
                "Interne Liste mit vollen Namen – nicht zum Aushang oder zur Weitergabe.",
                styles["internal"],
            )
        )
    story.append(Spacer(1, 4))
    return story


# --- Kopf, Fuß, Seitenzahlen ----------------------------------------------------------------


def _decorate(
    pdf: canvas.Canvas,
    report: t.Report,
    fonts: PdfFonts,
    size: tuple[float, float],
    page: int,
    total: int,
) -> None:
    width, height = size
    meta = report.meta
    pdf.saveState()
    pdf.setFillColor(MUTED)
    pdf.setStrokeColor(GRID)
    pdf.setLineWidth(0.4)
    if page > 1:
        y = height - MARGIN_TOP + 7 * mm
        pdf.setFont(fonts.bold, 9)
        pdf.drawString(MARGIN_X, y, f"{report.title} – {meta.tournament_name}")
        pdf.setFont(fonts.regular, 9)
        pdf.drawRightString(width - MARGIN_X, y, date_range_de(meta.date_from, meta.date_to))
        pdf.line(MARGIN_X, y - 2.5 * mm, width - MARGIN_X, y - 2.5 * mm)
    y = MARGIN_BOTTOM - 9 * mm
    pdf.line(MARGIN_X, y + 4 * mm, width - MARGIN_X, y + 4 * mm)
    pdf.setFont(fonts.regular, 8.5)
    pdf.drawString(
        MARGIN_X,
        y,
        f"Erstellt am {moment_de(meta.generated_at, meta.tz)} · erstellt mit Schiesshub",
    )
    pdf.drawRightString(width - MARGIN_X, y, f"Seite {page} von {total}")
    pdf.restoreState()


def _canvas_class(report: t.Report, fonts: PdfFonts, size: tuple[float, float]) -> type:
    class NumberedCanvas(canvas.Canvas):
        """Merkt sich die Seiten und zeichnet Kopf und Fuß erst, wenn die Seitenzahl feststeht."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._page_states: list[dict[str, Any]] = []

        def showPage(self) -> None:  # Name von reportlab vorgegeben
            self._page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._page_states)
            for state in self._page_states:
                self.__dict__.update(state)
                _decorate(self, report, fonts, size, self._pageNumber, total)
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

    return NumberedCanvas


# --- Ganzes Dokument ---------------------------------------------------------------------


def render_pdf(report: t.Report) -> bytes:
    fonts = pdf_fonts()
    styles = _styles(fonts)
    page = A4
    if not _fits(report, fonts, A4[0] - 2 * MARGIN_X):
        page = landscape(A4)
    avail = page[0] - 2 * MARGIN_X

    story = _front(report, styles)
    if not report.sections:
        story.append(Spacer(1, 10))
        story.append(Paragraph(escape(report.empty_text), styles["empty"]))
    for section in report.sections:
        story.extend(_section(section, styles, fonts, avail))
    if report.legend:
        story.append(Spacer(1, 10))
        story.extend(Paragraph(escape(line), styles["legend"]) for line in report.legend)

    buffer = io.BytesIO()
    meta = report.meta
    document = BaseDocTemplate(
        buffer,
        pagesize=page,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=f"{report.title} – {meta.tournament_name}",
        author=meta.organizer or "",
        creator="Schiesshub",
        subject=report.title,
    )
    frame = Frame(
        MARGIN_X,
        MARGIN_BOTTOM,
        page[0] - 2 * MARGIN_X,
        page[1] - MARGIN_TOP - MARGIN_BOTTOM,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="body",
    )
    document.addPageTemplates([PageTemplate(id="page", frames=[frame])])
    document.build(story, canvasmaker=_canvas_class(report, fonts, page))
    return buffer.getvalue()
