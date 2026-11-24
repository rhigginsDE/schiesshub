"""Vorabauskunft beim Aufgeben: Würde der Start jetzt (Abbruchgrund `dnf`) platziert?

Gerechnet mit derselben Funktion wie die Rangliste (`rules.aborted_for_raw`, dahinter
`app.scoring.compute_aborted`), damit Maske und Liste nie auseinanderlaufen. Die Wörter des
Verbands („Abbruch (AB)“, beim DSB nur „Abbruch“) kommen aus `begriffe.py`.

Bei einem schon abgebrochenen Start sagt dieselbe Auskunft, wie dieser Abbruch gewertet wird
(`dnf`: dieselbe Rechnung, mit den gespeicherten Rohwerten bzw. denen einer Korrektur-Vorschau;
`dns`/`dsq`: ohne Platz). Bei abgeschlossenen Starts gibt es keine Auskunft.

`reason_code`:

- `placed` – würde nach dem bisherigen Ergebnis platziert (`score_text`); offene Serien zählen
  nach der Regel der Wertung;
- `no_values` – noch kein Wertungswert erfasst (Abbruch im Probeschießen): ohne Platz;
- `incomplete_series` – eine Serie ist angefangen, aber ohne Serienstatus nicht wertbar;
- `missing_values` – der Serienstatus ist gesetzt, aber Pflichtwerte fehlen (`missing_fields`);
- `no_rule` – für nicht geschossene Serien gibt die Wertung keine Regel vor;
- `missing_section_time` – die Gesamtzeit eines Abschnitts fehlt;
- `invalid` – die Rohwerte lassen sich nicht werten;
- `not_started`, `disqualified` – abgebrochen als nicht angetreten bzw. disqualifiziert.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.begriffe import Begriffe
from app.modules.ergebnisse import begriffe
from app.modules.ergebnisse.rules import AbortedEvaluation, aborted_for_raw, scoring_definition
from app.modules.ergebnisse.schemas import (
    AbortPreview,
    AbortPreviewCode,
    MissingField,
    OpenSeriesItem,
)
from app.modules.turnier.models import Competition
from app.scoring import (
    ComputedResult,
    DefinitionError,
    InvalidRawError,
    compute,
    describe_form,
    load_definition,
    validate_raw,
)
from app.scoring.definition import Definition
from app.scoring.plan import SectionPlan, SeriesPlan
from app.scoring.raw import series_label
from app.scoring.results import SeriesResult
from app.scoring.status import ABORTED_BY_SHOOTER, NORMAL, STATUS_LABELS

# Nur aus diesen Status lässt sich ein Start abbrechen (`starts.rules.TRANSITIONS`).
ABORTABLE = frozenset({"registered", "called", "captured"})


@dataclass(frozen=True, slots=True)
class _Open:
    plan: SectionPlan
    series_plan: SeriesPlan
    series: SeriesResult
    label: str

    @property
    def path(self) -> str:
        return f"sections.{self.plan.id}.series[{self.series_plan.index}]"

    def item(self) -> OpenSeriesItem:
        return OpenSeriesItem(
            section_id=self.plan.id,
            section_name=self.plan.name,
            series=self.series_plan.number,
            path=self.path,
            state="started" if self.series.captured else "not_shot",
        )


def abort_preview(
    competition: Competition,
    raw: Mapping[str, Any] | None,
    status: str,
    abort_reason: str | None = None,
) -> AbortPreview | None:
    """Auskunft für „jetzt aufgeben“ bzw. für einen schon abgebrochenen Start; None bei
    abgeschlossenen Starts."""
    aborted = status == "aborted"
    if not aborted and status not in ABORTABLE:
        return None
    terms = begriffe.terms_for(competition.catalog_federation)
    defn = _definition(competition)
    mode = competition.capture_mode
    open_series = _open_series(defn, _computed(defn, mode, raw))
    numbers = [item.series_plan.number for item in open_series]
    items = [item.item() for item in open_series]
    if aborted and abort_reason in ("dns", "dsq"):
        return _without_place(abort_reason, terms, numbers, items)

    word = begriffe.abort_word(terms)
    evaluation = aborted_for_raw(competition.definition, mode, raw)
    if evaluation.placed:
        assert evaluation.computed is not None
        score_text = evaluation.computed.score_text
        if aborted:
            message = f"{word}: kommt nach dem bisherigen Ergebnis in die Rangliste ({score_text})."
        else:
            message = f"Würde nach dem bisherigen Ergebnis platziert ({score_text})."
        labels = [item.label for item in open_series]
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
            open_series_items=items,
        )
    if not evaluation.has_values:
        return AbortPreview(
            would_place=False,
            reason_code="no_values",
            message_de=f"Noch kein Wertungsschuss erfasst: {word} ohne Platz.",
            open_series=numbers,
            score_text=None,
            open_series_items=items,
        )
    reason = evaluation.reason or "invalid"
    listed = _join(evaluation.labels)
    missing: list[MissingField] = []
    match reason:
        case "incomplete_series":
            reason, message, missing = _incomplete(defn, mode, raw, open_series, evaluation, word)
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
        open_series_items=items,
        missing_fields=missing,
    )


def _without_place(
    abort_reason: str, terms: Begriffe, numbers: list[int], items: list[OpenSeriesItem]
) -> AbortPreview:
    """Nicht angetreten bzw. disqualifiziert: nie ein Platz."""
    code: AbortPreviewCode = "not_started" if abort_reason == "dns" else "disqualified"
    word = terms.nicht_angetreten if abort_reason == "dns" else terms.disqualifiziert
    return AbortPreview(
        would_place=False,
        reason_code=code,
        message_de=f"{word[:1].upper()}{word[1:]}: ohne Platz.",
        open_series=numbers,
        score_text=None,
        open_series_items=items,
    )


def _incomplete(
    defn: Definition | None,
    mode: str,
    raw: Mapping[str, Any] | None,
    open_series: Sequence[_Open],
    evaluation: AbortedEvaluation,
    word: str,
) -> tuple[AbortPreviewCode, str, list[MissingField]]:
    """Angefangene Serien, die sich so nicht werten lassen: ohne Serienstatus (a) oder mit
    gesetztem Serienstatus, aber fehlenden Pflichtwerten (b, `missing_values`)."""
    started = [
        item
        for item in open_series
        if defn is not None
        and item.series.captured
        and not defn.model.partial_series_counts(item.plan, item.series)
    ]
    without_status = [item for item in started if item.series.status == NORMAL]
    with_status = [item for item in started if item.series.status != NORMAL]
    missing, texts = _missing_fields(defn, mode, raw, with_status)

    parts: list[str] = []
    labels = [item.label for item in without_status] if started else list(evaluation.labels)
    if labels:
        subject = _join(labels)
        verb = "ist" if len(labels) == 1 else "sind"
        if defn is not None and _offers_shooter_abort(defn):
            status_text = STATUS_LABELS[ABORTED_BY_SHOOTER]
            parts.append(
                f"{subject} {verb} unvollständig erfasst – ohne Serienstatus "
                f"‚{status_text}‘ bleibt der Start ohne Platz."
            )
        else:
            parts.append(f"{subject} {verb} unvollständig erfasst: {word} ohne Platz.")
    parts.extend(texts)
    if not parts:
        parts.append(f"Eine Serie ist unvollständig erfasst: {word} ohne Platz.")
    code: AbortPreviewCode = "incomplete_series" if labels or not missing else "missing_values"
    return code, " ".join(parts), missing


def _missing_fields(
    defn: Definition | None, mode: str, raw: Mapping[str, Any] | None, items: Sequence[_Open]
) -> tuple[list[MissingField], list[str]]:
    """Pflichtwerte, die in Serien mit gesetztem Serienstatus fehlen – aus derselben Prüfung wie
    das Abschließen – und ein Satz, der alle nennt: „Es fehlen noch: Serie 2 (Stehende
    Scheiben) und Serie 3 (Zeit, Stehende Scheiben). Ohne diese Werte bleibt der Start ohne
    Platz.“"""
    if defn is None or not items:
        return [], []
    try:
        issues = validate_raw(defn, mode, raw or {}, partial=False)
        form = describe_form(defn, mode)
    except DefinitionError, InvalidRawError:
        return [], []
    labels = {
        series.path: {field.key: field.label for field in series.fields}
        for section in form.sections
        for series in section.series
    }
    ring_key = "shots" if form.capture_mode == "shot" else "sum"
    fields: list[MissingField] = []
    for item in items:
        path = item.path
        for issue in issues:
            if issue.path == path:
                key = ring_key  # „Ringe fehlen“ steht an der Serie
            elif issue.path.startswith(f"{path}."):
                key = issue.path[len(path) + 1 :].split(".")[0].split("[")[0]
            else:
                continue
            label = labels.get(path, {}).get(key, key)
            if all((f.path, f.key) != (path, key) for f in fields):
                fields.append(MissingField(path=path, key=key, label=label))
    if not fields:
        return [], []
    per_series = [
        f"{item.label} ({', '.join(f.label for f in fields if f.path == item.path)})"
        for item in items
        if any(f.path == item.path for f in fields)
    ]
    single = len(fields) == 1
    text = (
        f"Es {'fehlt' if single else 'fehlen'} noch: {_join_all(per_series)}. Ohne "
        f"{'diesen Wert' if single else 'diese Werte'} bleibt der Start ohne Platz."
    )
    return fields, [text]


def _definition(competition: Competition) -> Definition | None:
    try:
        return load_definition(scoring_definition(competition.definition))
    except DefinitionError, KeyError, TypeError:
        return None


def _computed(
    defn: Definition | None, capture_mode: str, raw: Mapping[str, Any] | None
) -> ComputedResult | None:
    if defn is None:
        return None
    try:
        return compute(defn, capture_mode, raw or {})
    except InvalidRawError:
        return None


def _open_series(defn: Definition | None, computed: ComputedResult | None) -> list[_Open]:
    """Gewertete Serien, die noch nicht vollständig erfasst sind."""
    if defn is None or computed is None:
        return []
    return [
        _Open(plan, series_plan, series, series_label(defn, plan, series_plan))
        for plan, section in zip(defn.sections, computed.sections, strict=True)
        for series_plan, series in zip(plan.series, section.series, strict=True)
        if not series_plan.struck and not series.complete
    ]


def _offers_shooter_abort(defn: Definition) -> bool:
    return any(ABORTED_BY_SHOOTER in defn.series_statuses(plan) for plan in defn.sections)


def _join_all(parts: Sequence[str]) -> str:
    """[„a“, „b“, „c“] → „a, b und c“."""
    if len(parts) < 2:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} und {parts[-1]}"


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
