"""Wertung eines Starts, den der Schütze abgebrochen hat (Abbruchgrund „aufgegeben“).

Sporthandbuch K 1.14 / L 1.12: Wer nach dem Kommando „Feuer“ abbricht, wird nach dem bis dahin
erzielten Ergebnis platziert. Wer vor dem ersten Wertungsschuss abbricht (Probeschießen,
K 1.07 / L 1.05), bleibt ohne Platz („AB“).

`compute_aborted` rechnet das Ergebnis eines abgebrochenen Starts so, dass es mit regulären
Ergebnissen vergleichbar ist. Was mit einer nicht geschossenen oder nur teilweise erfassten Serie
geschieht, entscheidet das Wertungsmodell (`ScoringModel.unshot_series`,
`partial_series_counts`, `missing_section_time_counts`) nach der Definition:

- `ringe`, `ringe_mit_zeitabzug`: nicht abgegebene Schüsse zählen 0 Ringe (kein Nachholen,
  A 9.08). Fehlt die Gesamtzeit eines Abschnitts mit Sollzeit, steht das Teilergebnis nur fest,
  wenn die Ringe nicht über `min_teilergebnis` liegen.
- `zeit_plus_zuschlaege`: eine nicht geschossene Serie zählt wie ein Abbruch durch den Schützen
  (`zeit_bei_abbruch_s` plus Zuschlag je stehender Scheibe, alle Scheiben stehen). Ohne
  `zeit_bei_abbruch_s` fehlt die Regel.
- `ringe_minus_zeit`: Für eine nicht geschossene Serie fehlt die Regel (es gibt keine Zeit des
  letzten Schusses); eine teilweise erfasste Serie zählt, wenn ihre Zeit erfasst ist.

Fehlt eine Regel oder ist eine Serie nur halb erfasst, liefert die Funktion kein Ergebnis,
sondern den Grund (`reason`); erfunden wird nichts.
"""

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from app.scoring.compute import compute
from app.scoring.definition import Definition, load_definition
from app.scoring.raw import series_label
from app.scoring.registry import UNSHOT_RINGS
from app.scoring.results import ComputedResult

AbortedReason = Literal["no_rule", "incomplete_series", "missing_section_time"]


@dataclass(frozen=True)
class AbortedOutcome:
    has_values: bool
    """Mindestens ein Wertungswert ist erfasst (Abbruch nach „Feuer“)."""
    computed: ComputedResult | None
    """Vergleichbares Ergebnis; None ohne Werte oder wenn es sich nicht vergleichen lässt."""
    reason: AbortedReason | None = None
    """Warum es kein vergleichbares Ergebnis gibt (nur mit `has_values`)."""
    unshot: list[str] = field(default_factory=list)
    """Nicht geschossene Serien („Serie 3“), wie gewertet bzw. ohne Regel."""
    incomplete: list[str] = field(default_factory=list)
    """Teilweise erfasste Serien bzw. Abschnitte ohne Gesamtzeit, die sich nicht werten lassen."""


def compute_aborted(
    definition: Mapping[str, Any] | Definition, capture_mode: str, raw: object
) -> AbortedOutcome:
    """Ergebnis eines abgebrochenen Starts; Fehler in den Rohwerten wie bei `compute`."""
    defn = load_definition(definition)
    partial = compute(defn, capture_mode, raw)
    if not _has_values(defn, partial):
        return AbortedOutcome(has_values=False, computed=None)

    model = defn.model
    filled = _copy_raw(raw)
    unshot: list[str] = []
    texts: list[str] = []
    no_rule: list[str] = []
    incomplete: list[str] = []
    missing_time: list[str] = []
    for plan, section in zip(defn.sections, partial.sections, strict=True):
        for series_plan, series in zip(plan.series, section.series, strict=True):
            if series_plan.struck or series.complete:
                continue
            label = series_label(defn, plan, series_plan)
            if series.captured:
                if model.partial_series_counts(plan, series):
                    missing_shots = plan.rings and series.shots_entered < series.shots_expected
                    if missing_shots and UNSHOT_RINGS.text not in texts:
                        texts.append(UNSHOT_RINGS.text)
                    continue
                incomplete.append(label)
                continue
            rule = model.unshot_series(plan)
            if rule is None:
                no_rule.append(label)
                continue
            unshot.append(label)
            if rule.text not in texts:
                texts.append(rule.text)
            if rule.raw is not None:
                _set_series(filled, plan.id, series_plan.index, rule.raw)
        if plan.section_time and section.time_cs is None:
            rings = section.rings if section.rings is not None else 0
            if not model.missing_section_time_counts(defn.scoring, plan, rings):
                missing_time.append(plan.name)

    if no_rule or incomplete or missing_time:
        reason: AbortedReason = (
            "no_rule" if no_rule else "incomplete_series" if incomplete else "missing_section_time"
        )
        return AbortedOutcome(
            has_values=True,
            computed=None,
            reason=reason,
            unshot=no_rule,
            incomplete=[*incomplete, *missing_time],
        )

    computed = compute(defn, capture_mode, filled)
    note = _note(unshot, texts)
    if note:
        computed = computed.model_copy(update={"steps": [note, *computed.steps]})
    return AbortedOutcome(has_values=True, computed=computed, unshot=unshot)


def _has_values(defn: Definition, computed: ComputedResult) -> bool:
    for plan, section in zip(defn.sections, computed.sections, strict=True):
        if plan.section_time and section.time_cs is not None:
            return True
        if any(series.captured and not series.struck for series in section.series):
            return True
    return False


def _copy_raw(raw: object) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {"sections": {}}
    filled = copy.deepcopy(dict(raw))
    if not isinstance(filled.get("sections"), Mapping):
        filled["sections"] = {}
    else:
        filled["sections"] = dict(filled["sections"])
    return filled


def _set_series(raw: dict[str, Any], section_id: str, index: int, value: dict[str, Any]) -> None:
    sections = raw["sections"]
    section = dict(sections.get(section_id) or {})
    series = list(section.get("series") or [])
    while len(series) <= index:
        series.append(None)
    series[index] = dict(value)
    section["series"] = series
    sections[section_id] = section


def _note(unshot: list[str], texts: list[str]) -> str | None:
    """„Abbruch (AB): Serie 3 und 4 nicht geschossen – gewertet als …“."""
    if not unshot and not texts:
        return None
    parts = []
    if unshot:
        parts.append(f"{_join(unshot)} nicht geschossen")
    parts.extend(texts)
    return "Abbruch (AB): " + " – ".join(parts)


def _join(labels: list[str]) -> str:
    """[„Serie 3“, „Serie 4“] → „Serie 3 und 4“ (gleiches Präfix zusammengefasst)."""
    if len(labels) == 1:
        return labels[0]
    prefix = "Serie "
    if all(label.startswith(prefix) for label in labels):
        numbers = [label[len(prefix) :] for label in labels]
        return f"{prefix}{', '.join(numbers[:-1])} und {numbers[-1]}"
    return f"{', '.join(labels[:-1])} und {labels[-1]}"
