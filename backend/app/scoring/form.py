"""Beschreibung der Eingabemaske für das Erfassungsterminal.

`describe_form(...).model_dump(mode="json")` geht unverändert als JSON an das Frontend. Die
Feldschlüssel (`key`) sind die Schlüssel der Rohwerte, `path` der Pfad bis zur Serie.
"""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.scoring.criteria import criterion_text
from app.scoring.definition import Definition, check_capture_mode, load_definition
from app.scoring.numbers import TENTH, format_number, format_seconds_value, plural
from app.scoring.plan import MAX_TENTHS, MIN_TENTHS, SectionPlan, SeriesPlan
from app.scoring.raw import plausible_max_s
from app.scoring.spec import CaptureMode, Direction, PositionSpec
from app.scoring.status import STATUS_LABELS, SeriesStatus, field_role
from app.scoring.tiebreak import series_sums_fit_blocks

HAND = {
    "beidhaendig": "beidhändig",
    "einhaendig": "einhändig",
    "starke_hand": "starke Hand",
    "schwache_hand": "schwache Hand",
}


# Kriterien, die Einzelschüsse brauchen (Hinweis bei Seriensumme; `neuner_abwaerts` hat einen
# eigenen, älteren Hinweis).
SHOT_ONLY_CRITERIA = {
    "schuesse_rueckwaerts": "Schüssen rückwärts",
    "mehr_treffer": "Treffern",
    "elfer": "Elfern",
    "neuner": "Neunern",
    "sechser": "Sechsern",
    "fuenfer": "Fünfern",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class StatusOption(_Frozen):
    """Ein möglicher Ablauf der Serie und die Felder, die er verlangt."""

    """Jedes Wertfeld der Serie (alle `fields` außer `status`) steht in genau einer der drei
    Listen (`status.field_role`). Die Maske schickt beim Speichern alle schon erfassten
    Schlüssel mit, unabhängig vom Status; der Server nimmt sie an, speichert sie unverändert
    und wertet nur, was der Status vorsieht."""

    key: SeriesStatus
    label: str
    required_fields: list[str]
    """Gewertet und für ein vollständiges Ergebnis nötig."""
    optional_fields: list[str] = []
    """Gewertet, wenn erfasst, aber nicht nötig (Zehner/Innenzehner bei Seriensumme)."""
    unscored_fields: list[str] = []
    """Felder, die bei diesem Status erfasst sein dürfen und in den Rohwerten erhalten bleiben,
    aber nicht gewertet werden – z. B. die gemessene Zeit bei „Abbruch durch den Schützen“
    (es zählt `zeit_bei_abbruch_s`). Die Maske soll sie mitsenden, nicht verwerfen
    (Ergebnisse werden nie überschrieben); der Rechenweg nennt sie („gemessene Zeit … wird
    nicht gewertet“)."""


class FieldSpec(_Frozen):
    key: str
    """Schlüssel in den Rohwerten: status, shots, sum, tens, inner_tens, time_cs, standing."""
    label: str
    kind: Literal["shots", "integer", "decimal", "time", "choice"]
    """`decimal`: Kommazahl (Seriensumme bei Zehntelwertung), Grenzen in `value_min`/
    `value_max`, Schritt `step`."""
    required: bool
    """Pflicht im Regelfall (Status „normal“); je Status gilt `options[].required_fields`."""
    options: list[StatusOption] | None = None
    """Auswahl (nur `status`); fehlt der Wert, gilt „normal“."""
    count: int | None = None
    """Anzahl Schüsse (nur `shots`; bei `per_target` Anzahl Ziele)."""
    allowed_values: list[int | str] | None = None
    """Erlaubte Ringwerte; „X“ ist der Innenzehner und zählt 10. None bei Zehntelwertung (dann
    gilt der Bereich `value_min`–`value_max` und, mit `zero_allowed`, die 0)."""
    min: int | None = None
    max: int | None = None
    unit: str | None = None
    """„cs“ = Hundertstelsekunden."""
    decimals: int | None = None
    """Nachkommastellen (Zehntelwertung: 1); None bei ganzen Zahlen."""
    step: Decimal | None = None
    value_min: Decimal | None = None
    value_max: Decimal | None = None
    zero_allowed: bool | None = None
    """Zusätzlich zum Bereich ist 0 erlaubt (Fehlschuss bei Zehntelwertung)."""
    per_target: bool | None = None
    """Ein Wert je Ziel (Wurfscheibe: 1 Treffer, 0 Fehler) statt je Schuss."""


HintKind = Literal[
    "target_time",
    "max_total_time",
    "competition_time",
    "preparation_time",
    "sighters",
    "struck",
    "position",
    "distance",
    "shots",
    "max_shots",
    "targets",
    "fixed_time",
    "time_per_shot",
    "max_time",
    "penalty",
    "scoring_break",
]


class HintItem(_Frozen):
    """Ein Hinweis mit Art, damit das Frontend nicht über den Wortlaut filtern muss.

    Abschnitt: `target_time` (Sollzeit), `max_total_time` (Abbruchzeit), `competition_time`,
    `preparation_time`, `sighters` – die letzten drei stehen auch als Felder
    (`competition_time_s`, `preparation_time_s`, `sighters`). Serie: `struck`, `position`,
    `distance`, `shots`, `max_shots`, `targets`, `fixed_time`, `time_per_shot`, `max_time`,
    `penalty`, `scoring_break`."""

    kind: HintKind
    text: str


class _Hints:
    """Sammelt Hinweise als Text (`hints`, wie bisher) und mit Art (`hint_items`)."""

    def __init__(self) -> None:
        self.items: list[HintItem] = []

    def add(self, kind: HintKind, text: str, *, first: bool = False) -> None:
        self.items.insert(0 if first else len(self.items), HintItem(kind=kind, text=text))

    @property
    def texts(self) -> list[str]:
        return [item.text for item in self.items]


NoteKind = Literal[
    "tenths",
    "tie_break_series_sum",
    "tens_optional",
    "competition_time_total",
    "max_score",
    "shootoff",
    "tie_break_manual",
]


class NoteItem(_Frozen):
    """Hinweis zur ganzen Maske mit Art (`FormDescription.note_items`).

    `tenths` (Zehntelwertung), `tie_break_series_sum` (ein Gleichstandskriterium lässt sich aus
    Seriensummen nicht rechnen), `tens_optional` (Zehner/Innenzehner freiwillig, aber für den
    Gleichstand gebraucht), `competition_time_total` (gemeinsame Wettkampfzeit), `max_score`
    (Höchstergebnis: gleicher Platz), `shootoff` (Stechen bis Platz N), `tie_break_manual`
    (ab einem Kriterium entscheidet ein Mensch)."""

    kind: NoteKind
    text: str


class _Notes:
    """Sammelt Hinweise der Maske als Text (`notes`) und mit Art (`note_items`)."""

    def __init__(self) -> None:
        self.items: list[NoteItem] = []

    def add(self, kind: NoteKind, text: str) -> None:
        self.items.append(NoteItem(kind=kind, text=text))

    @property
    def texts(self) -> list[str]:
        return [item.text for item in self.items]


class StanceForm(_Frozen):
    haltung: str
    hand: str | None
    text: str
    # Nur bei Angabe im Katalog (Auflage); fehlt sonst im JSON.
    aufgelegt: bool | None = Field(default=None, exclude_if=lambda value: value is None)


class PositionForm(_Frozen):
    nr: int
    distance_m: Decimal | None
    target: int | None
    """n-te Scheibe von links."""
    stances: list[StanceForm]


class SeriesForm(_Frozen):
    index: int
    number: int
    label: str
    path: str
    fields: list[FieldSpec]
    shots: int | None
    distance_m: Decimal | None
    time_limit_s: Decimal | None
    """Feste Schießzeit der Serie (Hinweis)."""
    max_time_s: Decimal | None
    """Zeitobergrenze der Serie (Hinweis; Überschreiten ergibt eine Warnung)."""
    position: PositionForm | None
    struck: bool
    """Gestrichen (`serien_gewertet`): darf erfasst werden, zählt nicht; ohne Pflichtfelder."""
    scoring_break_after: bool
    """Nach dieser Serie findet eine Trefferaufnahme statt."""
    max_rings: Decimal | int | None
    """Höchste Seriensumme; bei Zehntelwertung `Decimal` (JSON: Text „32.7“)."""
    hints: list[str]
    hint_items: list[HintItem] = []
    """Dieselben Hinweise wie `hints` (gleiche Reihenfolge), mit Art (`HintItem.kind`)."""


class SectionForm(_Frozen):
    id: str
    name: str
    path: str
    fields: list[FieldSpec]
    """Felder für den ganzen Abschnitt (Gesamtzeit beim Parcours)."""
    series: list[SeriesForm]
    series_counted: int
    """Anzahl gewerteter Serien (die ersten `series_counted`)."""
    targets: int | None
    max_shots_per_series: int | None
    penalty_per_standing_s: Decimal | None
    target_time_s: Decimal | None
    max_total_time_s: Decimal | None
    time_per_shot_s: Decimal | None
    pause_between_shots_s: Decimal | None
    max_rings: Decimal | int | None
    hints: list[str]
    """Hinweise als Text. Wettkampfzeit, Vorbereitung/Probe und Probeschüsse stehen hier und als
    Feld (`competition_time_s`, `preparation_time_s`, `sighters`); wer die Felder zeigt, filtert
    über `hint_items[].kind`, nicht über den Wortlaut."""
    hint_items: list[HintItem] = []
    """Dieselben Hinweise wie `hints` (gleiche Reihenfolge), mit Art (`HintItem.kind`)."""
    aufgelegt: bool = False
    """Alle Anschläge aller Positionen des Abschnitts sind aufgelegt (Auflageschießen); False
    ohne Positionen oder wenn ein Anschlag frei ist."""
    competition_time_s: Decimal | None = None
    """`wettkampfzeit_s`: Gesamtzeit aller Wertungsschüsse des Abschnitts (Hinweis)."""
    preparation_time_s: Decimal | None = None
    """`vorbereitung_probe_s`: Vorbereitungs- und Probezeit (Hinweis)."""
    sighters: int | Literal["unbegrenzt"] | None = None
    """`probeschuesse`: Zahl der Probeschüsse oder „unbegrenzt“ (Hinweis)."""


class FormDescription(_Frozen):
    variant_id: str
    variant_name: str
    model: str
    direction: Direction
    unit: str
    capture_mode: CaptureMode
    tie_breakers: list[str]
    sections: list[SectionForm]
    shots_expected: int
    series_expected: int
    max_rings: Decimal | int | None
    notes: list[str]
    note_items: list[NoteItem] = []
    """Dieselben Hinweise wie `notes` (gleiche Reihenfolge), mit Art (`NoteItem.kind`)."""
    ring_decimals: int = 0
    """Nachkommastellen der Ringwerte (1 bei Zehntelwertung)."""
    competition_time_total_s: Decimal | None = None
    """`wettkampfzeit_gesamt_s` der Variante: gemeinsame Zeit aller Abschnitte (Hinweis)."""
    shootoff_until_place: int | None = None
    """`stechen_bis_platz`: Gleichstand bis zu diesem Platz entscheidet ein Stechen."""
    tie_breakers_evaluated: list[str] = []
    """Gleichstandskriterien, die der Server rechnet (in Reihenfolge)."""
    tie_breakers_manual_from: str | None = None
    """Erstes Kriterium, das der Server nicht rechnet; ab dort entscheidet ein Mensch."""
    tie_breakers_until_place: int | None = None
    """`gleichstand_bis_platz`: `tie_breakers` gilt nur bis zu diesem Platz, danach
    `tie_breakers_after` (leer: gleicher Platz)."""
    tie_breakers_after: list[str] = []
    """`gleichstand_danach` (nur mit `tie_breakers_until_place`)."""
    tie_breakers_after_evaluated: list[str] = []
    """Wie `tie_breakers_evaluated` für `tie_breakers_after`."""
    tie_breakers_after_manual_from: str | None = None
    """Wie `tie_breakers_manual_from` für `tie_breakers_after`."""
    shootoff_at_max_score: bool = False
    """`stechen_bei_hoechstergebnis`: Gleichstand beim Höchstergebnis entscheidet ein Stechen."""


def describe_form(definition: Mapping[str, Any] | Definition, capture_mode: str) -> FormDescription:
    mode = check_capture_mode(capture_mode)
    defn = load_definition(definition)
    sections = [_section_form(defn, plan, mode) for plan in defn.sections]
    ring_sections = [plan for plan in defn.sections if plan.rings]
    evaluated, manual_from = defn.tie_chain
    notes = _Notes()
    if defn.tenths and ring_sections:
        notes.add(
            "tenths",
            "Zehntelwertung: je Schuss 0 oder 1,0 bis 10,9 (Komma oder Punkt); Zehner sind alle "
            "Schüsse ab 10,0.",
        )
    if mode == "series" and ring_sections:
        if "neuner_abwaerts" in defn.tie_breakers:
            notes.add(
                "tie_break_series_sum",
                "Bei Seriensumme lässt sich ein Gleichstand nicht nach Neunern abwärts auflösen.",
            )
        if "letzte_serie_rueckwaerts" in defn.tie_criteria and not series_sums_fit_blocks(defn):
            notes.add(
                "tie_break_series_sum",
                "Bei Seriensumme lässt sich ein Gleichstand nicht nach Zehnerserien auflösen "
                "(die Serien ergeben keine 10-Schuss-Blöcke).",
            )
        shot_only = [c for c in defn.tie_criteria if c in SHOT_ONLY_CRITERIA]
        if shot_only:
            notes.add(
                "tie_break_series_sum",
                "Bei Seriensumme lässt sich ein Gleichstand nicht nach "
                f"{', '.join(SHOT_ONLY_CRITERIA[c] for c in shot_only)} auflösen.",
            )
        if "zehner" in defn.tie_breakers or "innenzehner" in defn.tie_breakers:
            notes.add(
                "tens_optional",
                "Zehner und Innenzehner sind freiwillig, werden aber für den Gleichstand gebraucht."
                if not defn.tenths
                else "Zehner sind freiwillig, werden aber für den Gleichstand gebraucht.",
            )
    if defn.competition_time_total_s is not None:
        notes.add(
            "competition_time_total",
            "Gemeinsame Wettkampfzeit aller Abschnitte: "
            f"{_duration(defn.competition_time_total_s)}",
        )
    if defn.scoring.hoechstergebnis_gleicher_rang and defn.max_score is not None:
        notes.add(
            "max_score",
            f"Höchstergebnis ({format_number(defn.max_score)} {defn.unit}): bei "
            "Ergebnisgleichheit gleicher Platz, ohne Gleichstandsregel und ohne Stechen.",
        )
    if defn.scoring.stechen_bei_hoechstergebnis and defn.max_score is not None:
        notes.add(
            "shootoff",
            f"Höchstergebnis ({format_number(defn.max_score)} {defn.unit}): bei "
            "Ergebnisgleichheit entscheidet ein Stechen, nicht die Gleichstandsregel.",
        )
    if defn.scoring.stechen_bis_platz is not None:
        notes.add(
            "shootoff",
            f"Gleichstand bis Platz {defn.scoring.stechen_bis_platz} entscheidet ein Stechen.",
        )
    until = defn.scoring.gleichstand_bis_platz
    after = defn.tie_chain_after
    if manual_from is not None:
        scope = f" (Plätze bis {until})" if until is not None else ""
        notes.add(
            "tie_break_manual",
            f"Gleichstand{scope} ab „{criterion_text(manual_from)}“ nach Sportordnung manuell "
            "entscheiden (rechnet der Server nicht).",
        )
    if until is not None and after is not None and after[1] is not None:
        notes.add(
            "tie_break_manual",
            f"Gleichstand ab Platz {until + 1} ab „{criterion_text(after[1])}“ nach Sportordnung "
            "manuell entscheiden (rechnet der Server nicht).",
        )
    return FormDescription(
        variant_id=defn.variant_id,
        variant_name=defn.variant_name,
        model=defn.model.name,
        direction=defn.model.direction,
        unit=defn.unit,
        capture_mode=mode,
        tie_breakers=defn.tie_breakers,
        sections=sections,
        shots_expected=sum(plan.shots_expected for plan in defn.sections),
        series_expected=sum(len(plan.counted_series) for plan in defn.sections),
        max_rings=sum((plan.max_rings or 0 for plan in ring_sections), 0)
        if ring_sections
        else None,
        notes=notes.texts,
        note_items=notes.items,
        ring_decimals=1 if defn.tenths else 0,
        competition_time_total_s=defn.competition_time_total_s,
        shootoff_until_place=defn.scoring.stechen_bis_platz,
        tie_breakers_evaluated=evaluated,
        tie_breakers_manual_from=manual_from,
        tie_breakers_until_place=until,
        tie_breakers_after=list(defn.scoring.gleichstand_danach or []) if until else [],
        tie_breakers_after_evaluated=after[0] if after is not None else [],
        tie_breakers_after_manual_from=after[1] if after is not None else None,
        shootoff_at_max_score=bool(defn.scoring.stechen_bei_hoechstergebnis),
    )


def _section_form(defn: Definition, plan: SectionPlan, mode: CaptureMode) -> SectionForm:
    spec = plan.spec
    path = f"sections.{plan.id}"
    fields = []
    hints = _Hints()
    if plan.section_time:
        fields.append(_time_field("Gesamtzeit", plausible_max_s(plan, spec.max_gesamtzeit_s)))
    if spec.sollzeit_s is not None:
        hints.add("target_time", f"Sollzeit {_s(spec.sollzeit_s)}")
    if spec.max_gesamtzeit_s is not None:
        hints.add("max_total_time", f"Abbruchzeit {_s(spec.max_gesamtzeit_s)}")
    if spec.wettkampfzeit_s is not None:
        hints.add("competition_time", f"Wettkampfzeit {_duration(spec.wettkampfzeit_s)}")
    if spec.vorbereitung_probe_s is not None:
        hints.add(
            "preparation_time", f"Vorbereitung und Probe {_duration(spec.vorbereitung_probe_s)}"
        )
    if spec.probeschuesse == "unbegrenzt":
        hints.add("sighters", "Probeschüsse unbegrenzt")
    elif spec.probeschuesse is not None:
        hints.add("sighters", plural(spec.probeschuesse, "Probeschuss", "Probeschüsse"))
    stances = [
        stance
        for series in plan.series
        if series.position is not None
        for stance in series.position.anschlaege
    ]
    return SectionForm(
        id=plan.id,
        name=plan.name,
        path=path,
        fields=fields,
        series=[_series_form(defn, plan, series, mode, path) for series in plan.series],
        series_counted=len(plan.counted_series),
        targets=plan.targets,
        max_shots_per_series=spec.max_schuss_je_serie,
        penalty_per_standing_s=spec.zuschlag_je_stehender_scheibe_s,
        target_time_s=spec.sollzeit_s,
        max_total_time_s=spec.max_gesamtzeit_s,
        time_per_shot_s=spec.zeit_je_schuss_s,
        pause_between_shots_s=spec.pause_zwischen_schuessen_s,
        max_rings=plan.max_rings,
        hints=hints.texts,
        hint_items=hints.items,
        aufgelegt=bool(stances) and all(stance.aufgelegt for stance in stances),
        competition_time_s=spec.wettkampfzeit_s,
        preparation_time_s=spec.vorbereitung_probe_s,
        sighters=spec.probeschuesse,
    )


def _series_form(
    defn: Definition, plan: SectionPlan, series: SeriesPlan, mode: CaptureMode, path: str
) -> SeriesForm:
    spec = plan.spec
    fields = _value_fields(defn, plan, series, mode)
    statuses = defn.series_statuses(plan)
    if len(statuses) > 1:
        keys = [field.key for field in fields]
        status_field = FieldSpec(
            key="status",
            label="Ablauf der Serie",
            kind="choice",
            required=False,
            options=[_status_option(status, keys) for status in statuses],
        )
        fields = [status_field, *fields]

    hints = _Hints()
    position = _position_form(series.position) if series.position else None
    if position is not None:
        hints.add("position", _position_text(position))
    if series.distance_m is not None:
        hints.add("distance", f"Distanz {format_seconds_value(series.distance_m)} m")
    shots = series.shots
    if shots is not None and plan.per_target:
        # „ein Wert je Ziel“ nur, wenn je Ziel erfasst wird; bei Seriensumme nur die Zahl.
        per_target_text = ", ein Wert je Ziel" if mode == "shot" else ""
        hints.add("shots", f"{shots} Ziele{per_target_text}")
    elif shots is not None:
        hints.add("shots", f"{shots} Schuss")
    if spec.max_schuss_je_serie is not None:
        hints.add("max_shots", f"höchstens {spec.max_schuss_je_serie} Schuss")
    if plan.targets is not None:
        hints.add("targets", f"{plan.targets} Scheiben")
    if series.fixed_time_s is not None:
        hints.add("fixed_time", f"Schießzeit {_s(series.fixed_time_s)}")
    if spec.zeit_je_schuss_s is not None or spec.pause_zwischen_schuessen_s is not None:
        parts = []
        if spec.zeit_je_schuss_s is not None:
            parts.append(f"{_s(spec.zeit_je_schuss_s)} Sicht")
        if spec.pause_zwischen_schuessen_s is not None:
            parts.append(f"{_s(spec.pause_zwischen_schuessen_s)} Pause")
        hints.add("time_per_shot", f"je Schuss {', '.join(parts)}")
    if series.max_time_s is not None:
        hints.add("max_time", f"Zeitlimit {_s(series.max_time_s)}")
    if spec.zuschlag_je_stehender_scheibe_s is not None:
        hints.add(
            "penalty", f"{_s(spec.zuschlag_je_stehender_scheibe_s)} Zuschlag je stehender Scheibe"
        )
    if series.scoring_break_after:
        hints.add("scoring_break", "danach Trefferaufnahme")
    if series.struck:
        hints.add("struck", "gestrichen (nicht gewertet)", first=True)
        fields = [field.model_copy(update={"required": False}) for field in fields]

    prefix = f"{plan.name}, " if defn.multi_section else ""
    return SeriesForm(
        index=series.index,
        number=series.number,
        label=f"{prefix}Serie {series.number}",
        path=f"{path}.series[{series.index}]",
        fields=fields,
        shots=shots,
        distance_m=series.distance_m,
        time_limit_s=series.fixed_time_s,
        max_time_s=series.max_time_s,
        position=position,
        struck=series.struck,
        scoring_break_after=series.scoring_break_after,
        max_rings=shots * plan.max_ring if shots is not None else None,
        hints=hints.texts,
        hint_items=hints.items,
    )


def _value_fields(
    defn: Definition, plan: SectionPlan, series: SeriesPlan, mode: CaptureMode
) -> list[FieldSpec]:
    """Wertfelder der Serie (ohne `status`), in der Reihenfolge der Maske."""
    fields: list[FieldSpec] = []
    shots = series.shots
    if shots is not None:
        if mode == "shot" and plan.tenths:
            fields.append(
                FieldSpec(
                    key="shots",
                    label="Schüsse",
                    kind="shots",
                    required=True,
                    count=shots,
                    decimals=1,
                    step=TENTH,
                    value_min=MIN_TENTHS,
                    value_max=MAX_TENTHS,
                    zero_allowed=True,
                )
            )
        elif mode == "shot":
            fields.append(
                FieldSpec(
                    key="shots",
                    label="Treffer je Ziel" if plan.per_target else "Schüsse",
                    kind="shots",
                    required=True,
                    count=shots,
                    allowed_values=list(plan.ring_values),
                    per_target=True if plan.per_target else None,
                )
            )
        elif plan.tenths:
            fields.append(
                FieldSpec(
                    key="sum",
                    label="Seriensumme",
                    kind="decimal",
                    required=True,
                    decimals=1,
                    step=TENTH,
                    # Eine Seriensumme ist 0 oder mindestens 1,0 (jeder Treffer zählt 1,0 bis
                    # 10,9; `validate_raw` lehnt 0,1–0,9 ab): Bereich plus `zero_allowed`.
                    value_min=MIN_TENTHS,
                    value_max=shots * MAX_TENTHS,
                    zero_allowed=True,
                )
            )
        else:
            fields.append(
                FieldSpec(
                    key="sum",
                    label="Treffer" if plan.per_target else "Seriensumme",
                    kind="integer",
                    required=True,
                    min=0,
                    max=int(shots * plan.max_ring),
                )
            )
        if mode == "series":
            if "zehner" in defn.tie_breakers or "innenzehner" in defn.tie_breakers:
                fields.append(
                    FieldSpec(
                        key="tens",
                        label="Zehner (ab 10,0)" if plan.tenths else "Zehner (mit Innenzehnern)",
                        kind="integer",
                        required=False,
                        min=0,
                        max=shots,
                    )
                )
            if "innenzehner" in defn.tie_breakers and not plan.tenths:
                fields.append(
                    FieldSpec(
                        key="inner_tens",
                        label="Innenzehner",
                        kind="integer",
                        required=False,
                        min=0,
                        max=shots,
                    )
                )
    if plan.series_time:
        fields.append(_time_field("Zeit", plausible_max_s(plan, plan.spec.max_zeit_je_serie_s)))
    if plan.standing:
        fields.append(
            FieldSpec(
                key="standing",
                label="Stehende Scheiben",
                kind="integer",
                required=True,
                min=0,
                max=plan.targets,
            )
        )
    return fields


def _duration(seconds: Decimal) -> str:
    """Längere Zeiten in Minuten, wenn sie aufgehen (3000 → „50 min“), sonst Sekunden."""
    if seconds >= 60 and seconds % 60 == 0:
        return f"{format_seconds_value(seconds / 60)} min"
    return _s(seconds)


def _status_option(status: SeriesStatus, keys: list[str]) -> StatusOption:
    """Ordnet jedes Wertfeld der Serie (`keys`, Reihenfolge der Maske) einer Liste zu."""
    roles = {key: field_role(status, key) for key in keys}
    return StatusOption(
        key=status,
        label=STATUS_LABELS[status],
        required_fields=[key for key in keys if roles[key] == "required"],
        optional_fields=[key for key in keys if roles[key] == "optional"],
        unscored_fields=[key for key in keys if roles[key] == "unscored"],
    )


def _time_field(label: str, maximum_s: Decimal) -> FieldSpec:
    """`max`: Plausibilitätsgrenze in cs (darüber lehnt `validate_raw` ab)."""
    return FieldSpec(
        key="time_cs",
        label=label,
        kind="time",
        required=True,
        min=1,
        max=int(maximum_s * 100),
        unit="cs",
    )


def _position_form(position: PositionSpec) -> PositionForm:
    stances = []
    for stance in position.anschlaege:
        text = stance.haltung
        if stance.hand is not None:
            text += f", {HAND[stance.hand]}"
        if stance.aufgelegt:
            text += ", aufgelegt"
        stances.append(
            StanceForm(
                haltung=stance.haltung, hand=stance.hand, text=text, aufgelegt=stance.aufgelegt
            )
        )
    return PositionForm(
        nr=position.nr, distance_m=position.distanz_m, target=position.scheibe, stances=stances
    )


def _position_text(position: PositionForm) -> str:
    text = f"Position {position.nr}: " + " oder ".join(s.text for s in position.stances)
    if position.target is not None:
        text += f", Scheibe {position.target}"
    return text


def _s(seconds: Decimal) -> str:
    return f"{format_seconds_value(seconds)} s"
