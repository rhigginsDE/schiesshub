"""Vergleich einer Wettbewerbs-Definition mit der Katalog-Variante, aus der sie stammt.

Der Katalog liefert nur Vorgaben; Vereine ändern Serienzahl, gewertete Serien, Trefferaufnahmen
und mehr je Turnier. Aushang und Anzeige kennzeichnen solche Wettbewerbe als „abweichend vom
Katalog“ und nennen die Abweichungen mit den Texten von hier.

Verglichen werden die Regeln, nicht die Beschriftung: Namen von Variante und Abschnitten, die
Ablauf-Beschreibung, `source` und `scoring.geprueft` (Stand der Katalogpflege) zählen nicht.
Abschnitte werden über ihre `id` zugeordnet.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.modules.katalog.fileformat import Variante, Wertung

# Feld → (Bezeichnung, Einheit). Unbekannte Felder (neue Katalogfelder) erscheinen mit ihrem Namen.
SECTION_LABELS: dict[str, tuple[str, str]] = {
    "serien": ("Serien", ""),
    "schuss_je_serie": ("Schuss je Serie", ""),
    "max_schuss_je_serie": ("Höchstzahl Schuss je Serie", ""),
    "ziele_je_serie": ("Ziele je Serie", ""),
    "zeit_je_serie_s": ("Zeit je Serie", "s"),
    "zeiten_s": ("Zeiten je Serie", "s"),
    "max_zeit_je_serie_s": ("Höchstzeit je Serie", "s"),
    "zeit_wird_gemessen": ("Zeitmessung", ""),
    "zuschlag_je_stehender_scheibe_s": ("Zuschlag je stehender Scheibe", "s"),
    "distanzen_m": ("Distanzen", "m"),
    "zeit_je_schuss_s": ("Sichtzeit je Schuss", "s"),
    "pause_zwischen_schuessen_s": ("Pause zwischen den Schüssen", "s"),
    "sollzeit_s": ("Sollzeit", "s"),
    "max_gesamtzeit_s": ("Abbruchzeit", "s"),
    "positionen": ("Positionen", ""),
    "ringwerte": ("Ringwerte", ""),
    "zeit_bei_abbruch_s": ("Zeit bei Abbruch", "s"),
    "zuschlag_stoerung_vor_erstem_schuss_s": ("Zuschlag bei Störung vor dem ersten Schuss", "s"),
}
SCORING_LABELS: dict[str, tuple[str, str]] = {
    "modell": ("Wertungsmodell", ""),
    "rangfolge": ("Rangfolge", ""),
    "gleichstand": ("Gleichstand", ""),
    "abzug_je_voller_sekunde_ueber_sollzeit": ("Abzug je voller Sekunde über der Sollzeit", ""),
    "min_teilergebnis": ("Mindestwert je Teilergebnis", ""),
    "zeit_rundung": ("Zeitrundung", ""),
    "unbeendete_serie": ("Nicht beendete Serie", ""),
}
IGNORED_SECTION = frozenset({"id", "name"})
IGNORED_SCORING = frozenset({"geprueft"})


@dataclass(frozen=True, slots=True)
class Deviation:
    """Eine Abweichung. `path` zeigt in die Definition des Turniers (bei fehlenden Abschnitten:
    in die des Katalogs). Fehlende Werte sind `None`."""

    path: str
    catalog_value: Any
    tournament_value: Any
    text: str
    section_id: str | None = None


# --- Darstellung ---------------------------------------------------------------


def _number(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).replace(".", ",")


def _show(value: Any, unit: str = "") -> str:
    suffix = f" {unit}" if unit else ""
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if isinstance(value, int | float):
        return f"{_number(value)}{suffix}"
    if isinstance(value, str):
        return f"„{value}“"
    if isinstance(value, list) and all(
        isinstance(item, int | float) and not isinstance(item, bool) for item in value
    ):
        return ", ".join(_number(item) for item in value) + suffix
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ", ".join(value) if value else "keine"
    return "geändert"


def _enumerate(numbers: Sequence[int]) -> str:
    """[2] → „2“, [2, 4] → „2 und 4“, [1, 2, 4] → „1, 2 und 4“."""
    items = [str(number) for number in numbers]
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} und {items[-1]}"


def _generic(prefix: str, label: str, unit: str, catalog: Any, tournament: Any) -> str:
    # Verschachtelte Werte (Positionen) lassen sich nicht in einem Satz zeigen.
    simple = _show(tournament if catalog is None else catalog, unit) != "geändert"
    if catalog is None:
        value = f" {_show(tournament, unit)}" if simple else " festgelegt"
        return f"{prefix}: {label}{value} (im Katalog nicht festgelegt)"
    if tournament is None:
        was = f" (Katalog: {_show(catalog, unit)})" if simple else ""
        return f"{prefix}: {label} entfällt{was}"
    if _show(tournament, unit) == "geändert":
        return f"{prefix}: {label} geändert"
    return f"{prefix}: {label} {_show(tournament, unit)} statt {_show(catalog, unit)}"


def _hit_review_text(prefix: str, catalog: list[int] | None, tournament: list[int] | None) -> str:
    if catalog is None:
        assert tournament is not None
        what = f"nach Serie {_enumerate(tournament)}" if tournament else "keine"
        return f"{prefix}: Trefferaufnahme {what} (im Katalog nicht festgelegt)"
    was = f"nach {_enumerate(catalog)}" if catalog else "keiner"
    if tournament is None:
        return f"{prefix}: Trefferaufnahme nicht festgelegt (Katalog: {was})"
    if not tournament:
        return f"{prefix}: keine Trefferaufnahme statt nach {_enumerate(catalog)}"
    only = "nur " if set(tournament) < set(catalog) else ""
    if not catalog:
        return f"{prefix}: Trefferaufnahme nach Serie {_enumerate(tournament)} statt keiner"
    return f"{prefix}: Trefferaufnahme {only}nach Serie {_enumerate(tournament)} statt {was}"


def _counted_text(
    prefix: str, catalog: int | None, tournament: int | None, series: int, catalog_series: int
) -> str:
    if tournament is None:
        return f"{prefix}: alle {series} Serien gewertet statt {catalog} von {catalog_series}"
    text = f"{prefix}: {tournament} von {series} Serien gewertet"
    return text if catalog is None else f"{text} statt {catalog} von {catalog_series}"


# --- Vergleich -------------------------------------------------------------------


def _counted(section: Mapping[str, Any]) -> int | None:
    """Gewertete Serien; „alle“ ist dasselbe wie nicht gesetzt."""
    value = section.get("serien_gewertet")
    return None if value is None or value == section.get("serien") else value


def _compare_sections(
    index: int, catalog: Mapping[str, Any], tournament: Mapping[str, Any]
) -> list[Deviation]:
    section_id = str(tournament["id"])
    prefix = f"Abschnitt {tournament.get('name') or section_id}"
    base = f"variant.abschnitte[{index}]"
    result: list[Deviation] = []

    catalog_counted, counted = _counted(catalog), _counted(tournament)
    if catalog_counted != counted:
        result.append(
            Deviation(
                path=f"{base}.serien_gewertet",
                catalog_value=catalog_counted,
                tournament_value=counted,
                text=_counted_text(
                    prefix, catalog_counted, counted, tournament["serien"], catalog["serien"]
                ),
                section_id=section_id,
            )
        )

    for key in [*catalog, *(key for key in tournament if key not in catalog)]:
        if key in IGNORED_SECTION or key == "serien_gewertet":
            continue
        catalog_value, value = catalog.get(key), tournament.get(key)
        if catalog_value == value:
            continue
        path = f"{base}.{key}"
        if key == "trefferaufnahme_nach":
            text = _hit_review_text(prefix, catalog_value, value)
        elif (
            key == "positionen"
            and isinstance(catalog_value, list)
            and isinstance(value, list)
            and len(catalog_value) == len(value)
        ):
            for number, (before, after) in enumerate(zip(catalog_value, value, strict=True)):
                if before != after:
                    result.append(
                        Deviation(
                            path=f"{path}[{number}]",
                            catalog_value=before,
                            tournament_value=after,
                            text=f"{prefix}: Position in Serie {number + 1} geändert",
                            section_id=section_id,
                        )
                    )
            continue
        else:
            label, unit = SECTION_LABELS.get(key, (key, ""))
            text = _generic(prefix, label, unit, catalog_value, value)
        result.append(Deviation(path, catalog_value, value, text, section_id))
    return result


def compare(
    catalog_variant: Variante,
    catalog_scoring: Wertung,
    variant: Variante,
    scoring: Wertung,
) -> list[Deviation]:
    """Alle Abweichungen der Turnier-Definition (`variant`, `scoring`) vom Katalog."""
    catalog_sections = [
        section.model_dump(mode="json", exclude_none=True) for section in catalog_variant.abschnitte
    ]
    sections = [
        section.model_dump(mode="json", exclude_none=True) for section in variant.abschnitte
    ]
    by_id = {section["id"]: section for section in catalog_sections}
    own_ids = [section["id"] for section in sections]
    result: list[Deviation] = []

    for index, section in enumerate(sections):
        if section["id"] in by_id:
            result.extend(_compare_sections(index, by_id[section["id"]], section))
        else:
            result.append(
                Deviation(
                    path=f"variant.abschnitte[{index}]",
                    catalog_value=None,
                    tournament_value=section,
                    text=f"Zusätzlicher Abschnitt „{section['name']}“ (nicht im Katalog)",
                    section_id=section["id"],
                )
            )
    for index, section in enumerate(catalog_sections):
        if section["id"] not in own_ids:
            result.append(
                Deviation(
                    path=f"variant.abschnitte[{index}]",
                    catalog_value=section,
                    tournament_value=None,
                    text=f"Abschnitt „{section['name']}“ aus dem Katalog fehlt",
                    section_id=section["id"],
                )
            )
    shared_catalog = [sid for sid in by_id if sid in own_ids]
    shared_own = [sid for sid in own_ids if sid in by_id]
    if shared_catalog != shared_own:
        result.append(
            Deviation(
                path="variant.abschnitte",
                catalog_value=shared_catalog,
                tournament_value=shared_own,
                text="Reihenfolge der Abschnitte weicht vom Katalog ab",
            )
        )

    catalog_rules = catalog_scoring.model_dump(mode="json", exclude_none=True)
    rules = scoring.model_dump(mode="json", exclude_none=True)
    for key in [*catalog_rules, *(key for key in rules if key not in catalog_rules)]:
        if key in IGNORED_SCORING or catalog_rules.get(key) == rules.get(key):
            continue
        label, unit = SCORING_LABELS.get(key, (key, ""))
        result.append(
            Deviation(
                path=f"scoring.{key}",
                catalog_value=catalog_rules.get(key),
                tournament_value=rules.get(key),
                text=_generic("Wertung", label, unit, catalog_rules.get(key), rules.get(key)),
            )
        )
    return result
