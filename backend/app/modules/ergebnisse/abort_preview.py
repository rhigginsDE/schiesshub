"""Vorabauskunft beim Aufgeben: Würde der Start jetzt (Abbruchgrund `dnf`) platziert?

Gerechnet mit derselben Funktion wie die Rangliste (`rules.aborted_for_raw`, dahinter
`app.scoring.compute_aborted`), damit Maske und Liste nie auseinanderlaufen. Die Wörter des
Verbands („Abbruch (AB)“, beim DSB nur „Abbruch“) kommen aus `begriffe.py`.

`reason_code`:

- `placed` – würde nach dem bisherigen Ergebnis platziert (`score_text`); offene Serien zählen
  nach der Regel der Wertung;
- `no_values` – noch kein Wertungswert erfasst (Abbruch im Probeschießen): ohne Platz;
- `incomplete_series` – eine Serie ist nur teilweise erfasst und lässt sich so nicht werten;
- `no_rule` – für nicht geschossene Serien gibt die Wertung keine Regel vor;
- `missing_section_time` – die Gesamtzeit eines Abschnitts fehlt;
- `invalid` – die Rohwerte lassen sich nicht werten.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from app.modules.ergebnisse import begriffe
from app.modules.ergebnisse.rules import aborted_for_raw, scoring_definition
from app.modules.ergebnisse.schemas import AbortPreview
from app.modules.turnier.models import Competition
from app.scoring import DefinitionError, InvalidRawError, compute, load_definition
from app.scoring.definition import Definition
from app.scoring.raw import series_label
from app.scoring.status import ABORTED_BY_SHOOTER, STATUS_LABELS

# Nur aus diesen Status lässt sich ein Start abbrechen (`starts.rules.TRANSITIONS`).
ABORTABLE = frozenset({"registered", "called", "captured"})


def abort_preview(
    competition: Competition, raw: Mapping[str, Any] | None, status: str
) -> AbortPreview | None:
    """Auskunft für „jetzt aufgeben“; None, wenn sich der Start nicht abbrechen lässt."""
    if status not in ABORTABLE:
        return None
    word = begriffe.abort_word(begriffe.terms_for(competition.catalog_federation))
    evaluation = aborted_for_raw(competition.definition, competition.capture_mode, raw)
    defn = _definition(competition)
    numbers, labels = _open_series(defn, competition.capture_mode, raw)
    if evaluation.placed:
        assert evaluation.computed is not None
        score_text = evaluation.computed.score_text
        message = f"Würde nach dem bisherigen Ergebnis platziert ({score_text})."
        if labels:
            message += (
                f" {_join(labels)} {'zählt' if len(labels) == 1 else 'zählen'} nach der Regel "
                "der Wertung."
            )
        return AbortPreview(
            would_place=True,
            reason_code="placed",
            message_de=message,
            open_series=numbers,
            score_text=score_text,
        )
    if not evaluation.has_values:
        return AbortPreview(
            would_place=False,
            reason_code="no_values",
            message_de=f"Noch kein Wertungsschuss erfasst: {word} ohne Platz.",
            open_series=numbers,
            score_text=None,
        )
    reason = evaluation.reason or "invalid"
    listed = _join(evaluation.labels)
    match reason:
        case "incomplete_series":
            verb = "ist" if len(evaluation.labels) <= 1 else "sind"
            subject = listed or "Eine Serie"
            if defn is not None and _offers_shooter_abort(defn):
                status_text = STATUS_LABELS[ABORTED_BY_SHOOTER]
                message = (
                    f"{subject} {verb} unvollständig erfasst – ohne Serienstatus "
                    f"‚{status_text}‘ bleibt der Start ohne Platz."
                )
            else:
                message = f"{subject} {verb} unvollständig erfasst: {word} ohne Platz."
        case "no_rule":
            message = (
                f"Für nicht geschossene Serien ({listed}) gibt die Wertung keine Regel vor: "
                f"{word} ohne Platz."
            )
        case "missing_section_time":
            message = f"Gesamtzeit {listed} fehlt: {word} ohne Platz.".replace("  ", " ")
        case _:
            reason = "invalid"
            message = f"Die Rohwerte lassen sich nicht werten: {word} ohne Platz."
    return AbortPreview(
        would_place=False,
        reason_code=reason,
        message_de=message,
        open_series=numbers,
        score_text=None,
    )


def _definition(competition: Competition) -> Definition | None:
    try:
        return load_definition(scoring_definition(competition.definition))
    except DefinitionError, KeyError, TypeError:
        return None


def _open_series(
    defn: Definition | None, capture_mode: str, raw: Mapping[str, Any] | None
) -> tuple[list[int], list[str]]:
    """Gewertete Serien, die noch nicht vollständig erfasst sind: Nummern und Bezeichnungen."""
    if defn is None:
        return [], []
    try:
        computed = compute(defn, capture_mode, raw or {})
    except InvalidRawError:
        return [], []
    numbers: list[int] = []
    labels: list[str] = []
    for plan, section in zip(defn.sections, computed.sections, strict=True):
        for series_plan, series in zip(plan.series, section.series, strict=True):
            if series_plan.struck or series.complete:
                continue
            numbers.append(series.number)
            labels.append(series_label(defn, plan, series_plan))
    return numbers, labels


def _offers_shooter_abort(defn: Definition) -> bool:
    return any(ABORTED_BY_SHOOTER in defn.series_statuses(plan) for plan in defn.sections)


def _join(labels: Sequence[str]) -> str:
    """[„Serie 3“, „Serie 4“] → „Serie 3 und 4“."""
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    prefix = "Serie "
    if all(label.startswith(prefix) for label in labels):
        numbers = [label[len(prefix) :] for label in labels]
        return f"{prefix}{', '.join(numbers[:-1])} und {numbers[-1]}"
    return f"{', '.join(labels[:-1])} und {labels[-1]}"
