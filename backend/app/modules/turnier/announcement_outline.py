"""Standardgliederung der Ausschreibung, die ein neues Turnier mitbekommt.

Nur Überschriften, alle Texte leer: Inhalte schreibt der Verein selbst. Automatische Bausteine
(`kind` ≠ `text`) füllt die Druckansicht aus den Turnierdaten.
"""

from app.modules.turnier.schemas import Announcement, AnnouncementBlock

# (id, kind, Überschrift) in der Reihenfolge der Ausschreibung.
DEFAULT_OUTLINE: tuple[tuple[str, str, str], ...] = (
    ("begruessung", "text", "Begrüßung"),
    ("veranstalter-und-ort", "text", "Veranstalter und Ort"),
    ("termine", "dates", "Termine"),
    ("teilnahmeberechtigung", "text", "Teilnahmeberechtigung"),
    ("wettbewerbe", "competitions", "Wettbewerbe"),
    ("schiessstaende", "ranges", "Schießstände"),
    ("klassen", "classes", "Klassen"),
    ("startgeld", "fees", "Startgeld"),
    ("anmeldung", "text", "Anmeldung"),
    ("ablauf", "text", "Ablauf"),
    ("sicherheit", "text", "Sicherheit und Waffenkontrolle"),
    ("wertung", "text", "Wertung und Siegerehrung"),
    ("einsprueche", "text", "Einsprüche"),
    ("datenschutz", "text", "Datenschutz"),
    ("kontakt", "text", "Kontakt"),
)

# Abweichende Überschriften je Vorlage (Baustein-ID → Überschrift).
TEMPLATE_HEADINGS: dict[str, dict[str, str]] = {
    "club_championship": {
        "wettbewerbe": "Disziplinen der Vereinsmeisterschaft",
        "wertung": "Wertung, Vereinsmeistertitel und Siegerehrung",
    },
}


def default_blocks(template: str) -> list[AnnouncementBlock]:
    headings = TEMPLATE_HEADINGS.get(template, {})
    return [
        AnnouncementBlock.model_validate(
            {"id": block_id, "kind": kind, "heading": headings.get(block_id, heading)}
        )
        for block_id, kind, heading in DEFAULT_OUTLINE
    ]


def missing_default_blocks(announcement: Announcement, template: str) -> list[AnnouncementBlock]:
    """Abschnitte der Standardgliederung, die in `announcement` fehlen: automatische nach Art
    (jede Art gibt es nur einmal), Textabschnitte nach ID."""
    kinds = {block.kind for block in announcement.blocks}
    ids = {block.id for block in announcement.blocks}
    return [
        block
        for block in default_blocks(template)
        if (block.kind not in kinds if block.kind != "text" else block.id not in ids)
    ]


def default_announcement(template: str) -> Announcement:
    return Announcement(blocks=default_blocks(template))
