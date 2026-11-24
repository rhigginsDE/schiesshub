import type { Feed, FeedPerson, FeedRangliste, FeedSzene, FeedZeile } from "./typen";

/** Beispieldaten für Tests (erfundene Personen). */

export function zeile(teil: Partial<FeedZeile> & Pick<FeedZeile, "start_id" | "place">): FeedZeile {
  return {
    tied: false,
    needs_shootoff: false,
    tie_unresolved: false,
    tie_reason: null,
    group: "ranked",
    start_number: 1,
    attempt: 1,
    display_name: "Anna Beispiel",
    club: "SV Beispiel",
    class_short: "S",
    score_text: "183 Ringe",
    complete: true,
    series: [
      {
        section_id: "praezision",
        number: 1,
        struck: false,
        status: "normal",
        rings: 95,
        time_cs: null,
        standing: null,
        total_cs: null,
      },
      {
        section_id: "praezision",
        number: 2,
        struck: true,
        status: "normal",
        rings: 88,
        time_cs: null,
        standing: null,
        total_cs: null,
      },
    ],
    status: "final",
    running: false,
    provisional: false,
    abort_reason: null,
    ...teil,
  };
}

export function rangliste(): FeedRangliste {
  return {
    competition_id: "w1",
    competition_name: "Pistole bis 9 mm",
    direction: "absteigend",
    unit: "Ringe",
    combined: false,
    tie_word: "gleiches Ergebnis",
    groups: [
      {
        class_id: "k1",
        class_name: "Schützenklasse",
        class_short: "S",
        rows: [
          zeile({ start_id: "s1", place: 1, display_name: "Anna Beispiel" }),
          zeile({
            start_id: "s2",
            place: 2,
            tied: true,
            display_name: "Bernd Muster",
            score_text: "180 Ringe",
          }),
          zeile({
            start_id: "s3",
            place: 2,
            tied: true,
            display_name: null,
            start_number: 17,
            running: true,
            status: "running",
            score_text: "180 Ringe",
          }),
        ],
        more: 2,
        unplaced: [],
      },
      {
        class_id: "k2",
        class_name: "Damenklasse",
        class_short: "D1",
        rows: [zeile({ start_id: "s4", place: 1, display_name: "Clara Probe" })],
        more: 0,
        unplaced: [],
      },
    ],
  };
}

/**
 * Rangliste mit Abbrüchen wie vom Server seit dem Sporthandbuch-Abgleich: Abbruch nach „Feuer“ mit
 * Platz und gewertetem Ergebnis in `rows`; ohne Platz in `unplaced` mit fertigem Kennzeichen und
 * Begründung. Gleichstand mit dem formellen Wort im Hinweis.
 */
export function abbruchRangliste(): FeedRangliste {
  return {
    competition_id: "w9",
    competition_name: "Fallscheibe",
    competition_code: "1901",
    direction: "aufsteigend",
    unit: "s",
    combined: false,
    tie_word: "gleiches Ergebnis",
    groups: [
      {
        class_id: "k1",
        class_name: "Schützenklasse",
        class_short: "S",
        rows: [
          zeile({ start_id: "f1", place: 1, display_name: "Anna Beispiel", score_text: "21,40 s" }),
          zeile({
            start_id: "f2",
            place: 2,
            display_name: "Egon Abbruch",
            status: "aborted",
            abort_reason: "dnf",
            abort_label: "Abbruch (AB)",
            score_text: "25,10 s",
          }),
          zeile({
            start_id: "f3",
            place: 3,
            tied: true,
            needs_shootoff: true,
            tie_unresolved: true,
            tie_reason: "shootoff",
            tie_note: "gleiches Ergebnis auf Platz 3: Stechen",
            display_name: "Bernd Muster",
            score_text: "26,00 s",
          }),
          zeile({
            start_id: "f4",
            place: 3,
            tied: true,
            needs_shootoff: true,
            tie_unresolved: true,
            tie_reason: "shootoff",
            tie_note: "gleiches Ergebnis auf Platz 3: Stechen",
            display_name: "Clara Probe",
            score_text: "26,00 s",
          }),
        ],
        more: 0,
        unplaced: [
          zeile({
            start_id: "f5",
            place: null,
            group: "unranked",
            status: "aborted",
            abort_reason: "dnf",
            abort_label: "Abbruch (AB)",
            abort_note: "Ergebnis nicht vergleichbar: Serie 2 unvollständig erfasst",
            display_name: "Rita Fern",
            score_text: null,
          }),
          zeile({
            start_id: "f6",
            place: null,
            group: "unranked",
            status: "aborted",
            abort_reason: "dsq",
            abort_label: "disqualifiziert",
            display_name: "Karl Weiß",
            score_text: null,
          }),
        ],
      },
    ],
  };
}

/**
 * Rangliste mit Ringgleichheit, die die Gleichstandskette entschieden hat (wie der Server seit
 * Commit 3ba1bc4): beide mit `tie_reason` „resolved“, Kriterium und Hinweis, aber `tied` false –
 * Platz 2 und 3, kein geteilter Platz. Ohne Zehner (`tens` liefert der Feed nicht).
 */
export function getrenntRangliste(): FeedRangliste {
  const hinweis = "Ringgleichheit, entschieden nach: letzte Zehnerserie";
  return {
    competition_id: "w10",
    competition_name: "Luftgewehr",
    competition_code: "1.10",
    direction: "absteigend",
    unit: "Ringe",
    combined: false,
    tie_word: "Ringgleichheit",
    federation: "dsb",
    groups: [
      {
        class_id: "k1",
        class_name: "Schützenklasse",
        class_short: "S",
        rows: [
          zeile({
            start_id: "g1",
            place: 1,
            display_name: "Anna Beispiel",
            score_text: "390 Ringe",
          }),
          zeile({
            start_id: "g2",
            place: 2,
            tie_reason: "resolved",
            tie_criterion: "letzte_serie_rueckwaerts",
            tie_note: hinweis,
            display_name: "Bernd Muster",
            score_text: "385 Ringe",
          }),
          zeile({
            start_id: "g3",
            place: 3,
            tie_reason: "resolved",
            tie_criterion: "letzte_serie_rueckwaerts",
            tie_note: hinweis,
            display_name: "Clara Probe",
            score_text: "385 Ringe",
          }),
        ],
        more: 0,
        unplaced: [],
      },
    ],
  };
}

function person(teil: Partial<FeedPerson> & Pick<FeedPerson, "start_id">): FeedPerson {
  return {
    start_number: 5,
    display_name: "Jürgen Beispiel",
    club: "SV Beispiel",
    class_short: "S",
    competition_id: "w1",
    competition_name: "Pistole bis 9 mm",
    attempt: 1,
    status: "registered",
    lane: null,
    heat_number: null,
    heat_starts_at: null,
    heat_starts_at_local: null,
    ...teil,
  };
}

export const szenen: Record<FeedSzene["kind"], FeedSzene> = {
  live_ranking: {
    kind: "live_ranking",
    scene_id: "live",
    seconds: 20,
    title: "Live-Wertung",
    part: 1,
    parts: 1,
    ranking: rangliste(),
  },
  winners: {
    kind: "winners",
    scene_id: "sieger",
    seconds: 20,
    title: "Ergebnisliste",
    part: 1,
    parts: 1,
    ranking: rangliste(),
  },
  startlist: {
    kind: "startlist",
    scene_id: "start",
    seconds: 15,
    title: "Startliste",
    part: 1,
    parts: 1,
    startlist: {
      competition_id: "w1",
      competition_name: "Pistole bis 9 mm",
      range_id: "r1",
      range_name: "Schießstand Kurzwaffe 25 m",
      starts: [
        person({
          start_id: "p1",
          status: "called",
          lane: 2,
          heat_number: 3,
          heat_starts_at: "2026-11-22T13:00:00Z",
        }),
        person({ start_id: "p2", start_number: 6, display_name: null, club: null }),
      ],
      more: 4,
    },
  },
  range: {
    kind: "range",
    scene_id: "stand",
    seconds: 20,
    title: "Schießstand Kurzwaffe 25 m",
    part: 1,
    parts: 1,
    range: {
      range_id: "r1",
      range_name: "Schießstand Kurzwaffe 25 m",
      lane_count: 2,
      procedures: [
        {
          competition_id: "w2",
          competition_name: "Pistole bis 9 mm",
          catalog_code: "1201",
          competition_code: "1201",
          variant_name: "Variante 1",
          description: null,
          scoring: "Ringe, höher ist besser",
          notes: ["−1 Ring je volle Sekunde über der Sollzeit"],
          current: [],
          sections: [
            {
              id: "parcours",
              name: "Parcours",
              series_count: 2,
              counted_series: null,
              shots_per_series: 5,
              time_per_series_s: null,
              target_time_s: 60,
              time_measured: true,
              summary: "2 Serien · je 5 Schuss",
              series: [1, 2].map((nr) => ({
                number: nr,
                counted: true,
                shots: 5,
                time_s: null,
                distance_m: 20 - nr * 5,
                hit_review_after: nr === 1,
                position: {
                  nr,
                  distance_m: 20 - nr * 5,
                  target: nr,
                  text: "stehend, beidhändig",
                  stances: [{ haltung: "stehend", hand: "beidhaendig", text: "stehend" }],
                },
              })),
            },
            {
              id: "praezision",
              name: "Präzision",
              series_count: 3,
              counted_series: 2,
              shots_per_series: 10,
              time_per_series_s: 300,
              target_time_s: null,
              time_measured: false,
              summary: "3 Serien · je 10 Schuss · je 300 s",
              series: [1, 2, 3].map((nr) => ({
                number: nr,
                counted: nr <= 2,
                shots: 10,
                time_s: 300,
                distance_m: 25,
                hit_review_after: false,
                position: null,
              })),
            },
          ],
        },
      ],
      lanes: [
        { lane: 1, start: null },
        { lane: 2, start: person({ start_id: "p3", status: "called", lane: 2 }) },
      ],
      upcoming: [
        {
          kind: "schedule",
          competition_id: "w3",
          competition_name: "Pistole bis 9 mm",
          competition_code: "1001",
          more: 0,
          heat_number: 4,
          starts_at: "2026-11-22T13:20:00Z",
          ends_at: "2026-11-22T13:35:00Z",
          starts_at_local: "2026-11-22T14:20:00+01:00",
          ends_at_local: "2026-11-22T14:35:00+01:00",
          entries: [
            {
              start_id: "p4",
              start_number: 4,
              display_name: "Dora Nächste",
              club: "SV Beispiel",
              class_short: "S",
              attempt: 1,
              busy: false,
              heat_number: 4,
              starts_at: "2026-11-22T13:20:00Z",
              starts_at_local: "2026-11-22T14:20:00+01:00",
              lane: 3,
            },
          ],
        },
        {
          kind: "queue",
          competition_id: "w2",
          competition_name: "Pistole bis 9 mm",
          competition_code: "1201",
          more: 2,
          entries: [
            {
              start_id: "p5",
              start_number: 2,
              display_name: "Karl Weiß",
              club: "SV Beispiel",
              class_short: "S",
              attempt: 1,
              busy: true,
              busy_range_id: "r2",
              busy_range_name: "Schießstand Flinte 15 m",
              busy_lane: 1,
              position: 1,
            },
          ],
        },
      ],
      // Veraltet, nicht mehr gezeigt
      next_heat: null,
      next: [],
    },
  },
  notice: {
    kind: "notice",
    scene_id: "hinweis",
    seconds: 20,
    title: "Siegerehrung",
    part: 1,
    parts: 1,
    heading: "Siegerehrung um 16:00 Uhr",
    text: "Im Schützenhaus.",
  },
  idle: {
    kind: "idle",
    scene_id: "ruhe",
    seconds: 60,
    title: "Ruhe",
    part: 1,
    parts: 1,
    heading: "Gleich geht es los",
    text: "Startliste und Ergebnisse erscheinen hier, sobald es losgeht.",
  },
};

export function beispielFeed(teil: Partial<Feed> = {}): Feed {
  return {
    display_id: "a1",
    display_name: "Hauptanzeige",
    version: "v1",
    server_time: "2026-11-22T12:42:00Z",
    theme: "dark",
    header: {
      tournament_id: "t1",
      title: "Herbstpokal 2026",
      organizer: "SV Beispiel",
      date_from: "2026-11-22",
      date_to: "2026-11-22",
      tournament_status: "active",
      tournament_mode: "auto",
      timezone: "Europe/Berlin",
      is_practice: false,
    },
    scenes: [szenen.live_ranking],
    skipped: [],
    ticker: null,
    warnings: [],
    reload_on: ["display.changed", "start.*", "result.*", "backup.status"],
    poll_seconds: 60,
    ...teil,
  };
}
