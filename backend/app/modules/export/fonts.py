"""Schrift für die PDF-Listen.

Die eingebauten PDF-Schriften (Helvetica …) kennen nur westeuropäische Zeichen; „Yılmaz“,
„Łukasz“ oder „Čapek“ kämen als Kästchen heraus. Deshalb wird eine freie TrueType-Schrift
eingebettet: DejaVu Sans aus dem Debian-Paket `fonts-dejavu-core` (im Backend-Image installiert,
siehe `deploy/backend.Dockerfile`).

Rückfall, falls die Datei fehlt (mit Warnung im Log): erst Bitstream Vera, die reportlab
mitbringt (eingebettet, aber ohne z. B. „ł“ und „č“), dann Helvetica.
"""

import logging
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

DEJAVU_DIR = Path("/usr/share/fonts/truetype/dejavu")
REPORTLAB_FONTS = Path(reportlab.__file__).parent / "fonts"

# (Name, Datei normal, Datei fett), in der Reihenfolge der Bevorzugung.
CANDIDATES: tuple[tuple[str, Path, Path], ...] = (
    ("DejaVuSans", DEJAVU_DIR / "DejaVuSans.ttf", DEJAVU_DIR / "DejaVuSans-Bold.ttf"),
    ("Vera", REPORTLAB_FONTS / "Vera.ttf", REPORTLAB_FONTS / "VeraBd.ttf"),
)


@dataclass(frozen=True, slots=True)
class PdfFonts:
    regular: str
    bold: str
    # True, wenn eine TrueType-Schrift eingebettet wird.
    embedded: bool
    # True, wenn alle üblichen Zeichen europäischer Namen vorhanden sind.
    full_coverage: bool


@cache
def pdf_fonts() -> PdfFonts:
    for index, (name, regular, bold) in enumerate(CANDIDATES):
        if not (regular.is_file() and bold.is_file()):
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, str(regular)))
            pdfmetrics.registerFont(TTFont(f"{name}-Bold", str(bold)))
        except Exception:  # beschädigte Datei: nächste Schrift versuchen
            logger.warning("Schrift %s ließ sich nicht laden.", regular, exc_info=True)
            continue
        if index > 0:
            logger.warning(
                "Schrift %s fehlt; die PDF-Listen nutzen %s. Zeichen wie „ł“ oder „č“ "
                "erscheinen dann nicht. Abhilfe: Paket fonts-dejavu-core installieren.",
                CANDIDATES[0][1],
                name,
            )
        return PdfFonts(name, f"{name}-Bold", embedded=True, full_coverage=index == 0)
    logger.warning(
        "Keine TrueType-Schrift gefunden; die PDF-Listen nutzen Helvetica. Zeichen außerhalb "
        "von Westeuropa erscheinen dann nicht. Abhilfe: Paket fonts-dejavu-core installieren."
    )
    return PdfFonts("Helvetica", "Helvetica-Bold", embedded=False, full_coverage=False)
