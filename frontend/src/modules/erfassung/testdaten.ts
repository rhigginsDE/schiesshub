/** Formulare und Stände für Tests, nach dem Muster echter Antworten des Servers. */
import type { ErgebnisStand, FeldBeschreibung, Formular, Maske, SerieForm, Wertung } from "./api";

const STATUS_FELD: FeldBeschreibung = {
  key: "status",
  label: "Ablauf der Serie",
  kind: "choice",
  required: false,
  options: [
    {
      key: "normal",
      label: "regulär",
      required_fields: ["time_cs", "standing"],
      optional_fields: [],
      unscored_fields: [],
    },
    {
      key: "time_limit",
      label: "Zeitlimit erreicht (Abbruch durch den Schießleiter)",
      required_fields: ["standing"],
      optional_fields: [],
      unscored_fields: ["time_cs"],
    },
    {
      key: "aborted_by_shooter",
      label: "Abbruch durch den Schützen",
      required_fields: ["standing"],
      optional_fields: [],
      unscored_fields: ["time_cs"],
    },
    {
      key: "malfunction_before_first_shot",
      label: "Waffenstörung vor dem ersten Wertungsschuss",
      required_fields: [],
      optional_fields: [],
      unscored_fields: ["time_cs", "standing"],
    },
  ],
};

const ZEIT: FeldBeschreibung = {
  key: "time_cs",
  label: "Zeit",
  kind: "time",
  required: true,
  min: 1,
  // Plausibilitätsgrenze des Servers: 3 × Zeitlimit (60 s), in Hundertstel
  max: 18000,
  unit: "cs",
};

const STEHEND: FeldBeschreibung = {
  key: "standing",
  label: "Stehende Scheiben",
  kind: "integer",
  required: true,
  min: 0,
  max: 5,
};

function serie(
  index: number,
  felder: FeldBeschreibung[],
  teil: Partial<SerieForm> = {},
): SerieForm {
  return {
    index,
    number: index + 1,
    label: `Serie ${index + 1}`,
    path: `sections.x.series[${index}]`,
    fields: felder,
    shots: null,
    distance_m: null,
    time_limit_s: null,
    max_time_s: "60",
    position: null,
    struck: false,
    scoring_break_after: false,
    max_rings: null,
    hints: [],
    hint_items: [],
    ...teil,
  };
}

function abschnitt(id: string, name: string, series: SerieForm[]): Formular["sections"][number] {
  return {
    id,
    name,
    path: `sections.${id}`,
    fields: [],
    series: series.map((s) => ({ ...s, path: `sections.${id}.series[${s.index}]` })),
    series_counted: series.filter((s) => !s.struck).length,
    targets: null,
    max_shots_per_series: null,
    penalty_per_standing_s: null,
    target_time_s: null,
    max_total_time_s: null,
    time_per_shot_s: null,
    pause_between_shots_s: null,
    max_rings: null,
    hints: [],
    hint_items: [],
    aufgelegt: false,
  };
}

function formular(teil: Partial<Formular>): Formular {
  return {
    note_items: [],
    ring_decimals: 0,
    tie_breakers_evaluated: [],
    variant_id: "standard",
    variant_name: "Standard",
    model: "x",
    direction: "absteigend",
    unit: "Ringe",
    capture_mode: "series",
    tie_breakers: [],
    sections: [],
    shots_expected: 0,
    series_expected: 0,
    max_rings: null,
    notes: [],
    ...teil,
  };
}

/** Fallscheibe: zwei Serien mit Status, Zeit und stehenden Scheiben, eine dritte gestrichen. */
export const FALLSCHEIBE: Formular = formular({
  model: "zeit_plus_zuschlaege",
  direction: "aufsteigend",
  unit: "s",
  sections: [
    abschnitt("fallscheibe", "Fallscheibe", [
      serie(0, [STATUS_FELD, ZEIT, STEHEND]),
      serie(1, [STATUS_FELD, ZEIT, STEHEND], { scoring_break_after: true }),
      serie(2, [STATUS_FELD, { ...ZEIT, required: false }, { ...STEHEND, required: false }], {
        struck: true,
      }),
    ]),
  ],
  series_expected: 2,
});

const SCHUESSE: FeldBeschreibung = {
  key: "shots",
  label: "Schüsse",
  kind: "shots",
  required: true,
  count: 3,
  allowed_values: ["X", 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
};

/** Präzision im Einzelschuss: zwei Serien zu je drei Schuss. */
export const PRAEZISION: Formular = formular({
  capture_mode: "shot",
  sections: [
    abschnitt("praezision", "Präzision", [
      serie(0, [SCHUESSE], { shots: 3, max_time_s: null }),
      serie(1, [SCHUESSE], { shots: 3, max_time_s: null }),
    ]),
  ],
  shots_expected: 6,
  series_expected: 2,
  max_rings: 60,
});

/** Präzision als Seriensumme mit freiwilligen Zehnern. */
export const SERIENSUMME: Formular = formular({
  sections: [
    abschnitt("praezision", "Präzision", [
      serie(
        0,
        [
          { key: "sum", label: "Seriensumme", kind: "integer", required: true, min: 0, max: 100 },
          { key: "tens", label: "Zehner", kind: "integer", required: false, min: 0, max: 10 },
        ],
        { shots: 10, max_time_s: null },
      ),
    ]),
  ],
});

export function wertung(teil: Partial<Wertung> = {}): Wertung {
  return {
    tie_breakers_missing_items: [],
    decimals: 0,
    model: "x",
    direction: "aufsteigend",
    unit: "s",
    score: "0.00",
    score_text: "0,00 s",
    complete: false,
    rings: null,
    tens: null,
    inner_tens: null,
    ring_counts: null,
    time_cs: 0,
    penalty_cs: 0,
    deduction: null,
    parcours_time_cs: null,
    tie_breakers_missing: [],
    sections: [],
    progress: {
      shots_entered: 0,
      shots_expected: 0,
      series_complete: 0,
      series_expected: 2,
      section_times_entered: 0,
      section_times_expected: 0,
    },
    steps: [],
    warnings: [],
    ...teil,
  };
}

export function stand(teil: Partial<ErgebnisStand> = {}): ErgebnisStand {
  return {
    start_id: "s-1",
    status: "called",
    abort_reason: null,
    seq: 0,
    raw: {},
    computed: wertung(),
    score: "0.00",
    is_final: false,
    finalized_at: null,
    provisional_until: null,
    is_provisional: false,
    needs_review: false,
    review_reason: null,
    definition_revision: 1,
    ...teil,
  };
}

export function maske(form: Formular, aktuell: ErgebnisStand): Maske {
  return {
    derived_values: [],
    header: {
      start_number: 7,
      display_name: "Markus Brandt",
      full_name_shown: true,
      club: "SV Tell Musterstadt",
      class_id: "k",
      class_name: "Schützenklasse",
      class_short: "S",
      competition_id: "w",
      competition_name: "Selbstladeflinte",
      competition_code: null,
      range_id: "r",
      range_name: "Stand 1",
      attempt: 1,
      attempts_booked: 2,
      max_starts: 3,
      lane: 1,
    },
    competition_capture_mode: form.capture_mode,
    form,
    current: aktuell,
  };
}
