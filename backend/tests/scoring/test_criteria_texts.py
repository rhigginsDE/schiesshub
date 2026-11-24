"""Kurz- und Langtext der Gleichstandskriterien (`app/scoring/kriterien.yaml`)."""

from pathlib import Path

import pytest
import yaml

from app.modules.ergebnisse import begriffe
from app.scoring import criteria
from app.scoring.criteria import criterion_entries, criterion_short, criterion_text
from tests.conftest import REAL_CATALOG_DIR


def _criteria_in(value: object) -> set[str]:
    """Alle Einträge unter einem Schlüssel `gleichstand`, wo immer er in der Datei steht."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "gleichstand" and isinstance(item, list):
                found.update(str(c) for c in item)
            else:
                found |= _criteria_in(item)
    elif isinstance(value, list):
        for item in value:
            found |= _criteria_in(item)
    return found


def _catalog_criteria() -> set[str]:
    found: set[str] = set()
    for path in sorted(Path(REAL_CATALOG_DIR).glob("*/gruppen/*.yaml")):
        found |= _criteria_in(yaml.safe_load(path.read_text(encoding="utf-8")))
    return found


def test_every_catalog_criterion_has_short_and_long_text() -> None:
    used = _catalog_criteria()
    assert {"zehner", "letzte_serie_rueckwaerts", "trefferfolge_rueckwaerts"} <= used
    entries = criterion_entries()
    missing = sorted(used - set(entries))
    assert missing == [], f"Texte fehlen in app/scoring/kriterien.yaml: {missing}"
    for criterion in used:
        entry = entries[criterion]
        assert entry.long, criterion
        assert entry.short, criterion
        assert entry.short_hits, criterion
        assert len(entry.short) <= len(entry.long), criterion
        assert len(entry.short_hits) <= len(entry.long), criterion


def test_last_series_short_text_follows_the_applied_rule() -> None:
    assert criterion_short("letzte_serie_rueckwaerts") == "letzte Zehnerserie"
    assert criterion_short("letzte_serie_rueckwaerts", hits_only=True) == "letzte Serie"
    assert "Wurfscheibe" in (criterion_text("letzte_serie_rueckwaerts") or "")
    assert criterion_short("zehner", hits_only=True) == criterion_short("zehner")
    assert criterion_short("abstand_zum_rand") == "abstand zum rand"
    assert criterion_short(None) is None


def test_tie_note_short_and_long() -> None:
    args = ("resolved", "letzte_serie_rueckwaerts", 1, "Ringgleichheit")
    assert begriffe.tie_note(*args) == "Ringgleichheit, entschieden nach: letzte Zehnerserie"
    assert begriffe.tie_note(*args, hits_only=True) == (
        "Ringgleichheit, entschieden nach: letzte Serie"
    )
    assert begriffe.tie_note(*args, long=True) == (
        "Ringgleichheit, entschieden nach: letzte Zehnerserie, dann rückwärts in "
        "10-Schuss-Serien (Wurfscheibe: je Serie)"
    )
    manual = ("manual", "trefferfolge_rueckwaerts", 1, "Treffergleichheit")
    assert begriffe.tie_note(*manual) == (
        "Treffergleichheit: nach Sportordnung manuell entscheiden (nächstes Kriterium: "
        "Trefferfolge rückwärts)"
    )


def test_texts_file_needs_both_fassungen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    broken = tmp_path / "kriterien.yaml"
    broken.write_text('kriterien:\n  zehner: "Anzahl der Zehner"\n', encoding="utf-8")
    monkeypatch.setattr(criteria, "TEXTS_FILE", broken)
    criterion_entries.cache_clear()
    try:
        with pytest.raises(ValueError, match=r"lang.*kurz"):
            criterion_entries()
        broken.write_text(
            'kriterien:\n  x:\n    lang: "a"\n    kurz:\n      standard: "a"\n',
            encoding="utf-8",
        )
        criterion_entries.cache_clear()
        with pytest.raises(ValueError, match="je Fall"):
            criterion_entries()
    finally:
        monkeypatch.undo()
        criterion_entries.cache_clear()
    assert criterion_entries()["zehner"].long == "Anzahl der Zehner"
