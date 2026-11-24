/** Feste Testdaten für die Tests des Turnier-Moduls (keine echten Personen). */
import type { TurnierUebersicht, Wettbewerb } from "./typen";

export const TURNIER_ID = "11111111-1111-4111-8111-111111111111";
export const STAND_ID = "22222222-2222-4222-8222-222222222222";
export const KLASSE_ID = "33333333-3333-4333-8333-333333333333";
export const WETTBEWERB_ID = "44444444-4444-4444-8444-444444444444";

export function beispielWettbewerb(): Wettbewerb {
  return {
    id: WETTBEWERB_ID,
    tournament_id: TURNIER_ID,
    range_id: STAND_ID,
    sort: 0,
    catalog_federation: "bds",
    catalog_code: "4401",
    name: "Selbstladeflinte, offene Visierung",
    definition: {
      source: {
        federation: "bds",
        code: "4401",
        group: "flinte-15m-fallscheibe",
        catalog_stand: "2026-06-30",
      },
      variant: {
        id: "standard",
        name: "Standard",
        abschnitte: [
          {
            id: "fallscheibe",
            name: "Fallscheibe",
            serien: 4,
            max_schuss_je_serie: 6,
            ziele_je_serie: 5,
            max_zeit_je_serie_s: 60,
            zeit_wird_gemessen: true,
            zuschlag_je_stehender_scheibe_s: 10,
          },
        ],
      },
      scoring: { modell: "zeit_plus_zuschlaege", rangfolge: "aufsteigend", geprueft: true },
      ablauf_beschreibung: "4 Serien auf je 5 Fallscheiben",
    },
    capture_mode: "series",
    multi_start: true,
    max_starts: 3,
    multi_start_rule: "best",
    fee_first_cents: 600,
    fee_repeat_cents: 400,
    class_ids: [],
    combined_ranking: false,
    planning: "queue",
    heat_minutes: null,
    changeover_minutes: 5,
    definition_revision: 1,
    catalog_changed: false,
    catalog_stand_then: "2026-06-30",
    catalog_stand_now: "2026-06-30",
  } as Wettbewerb;
}

export function beispielTurnier(status: TurnierUebersicht["status"] = "draft"): TurnierUebersicht {
  return {
    id: TURNIER_ID,
    name: "Testturnier Fallscheibe",
    organizer: "SV Musterstadt",
    date_from: "2026-12-05",
    date_to: "2026-12-05",
    status,
    template: "open",
    settings: {
      protest_minutes: null,
      currency: "EUR",
      default_fee_first_cents: 600,
      default_fee_repeat_cents: 400,
      default_multi_start: true,
      default_max_starts: 3,
      default_multi_start_rule: "best",
      default_changeover_minutes: 5,
      default_capture_mode: "series",
      display: {},
    },
    created_at: "2026-11-21T10:00:00Z",
    updated_at: "2026-11-21T10:00:00Z",
    ranges: [
      { id: STAND_ID, tournament_id: TURNIER_ID, name: "15-m-Stand", lane_count: 2, sort: 0 },
    ],
    classes: [
      {
        id: KLASSE_ID,
        tournament_id: TURNIER_ID,
        code: "senioren",
        name: "Seniorenklasse",
        short: "Sen",
        sort: 0,
        merge_into_id: null,
      },
    ],
    competitions: [
      beispielWettbewerb(),
      {
        ...beispielWettbewerb(),
        id: "55555555-5555-4555-8555-555555555555",
        catalog_code: "4403",
        name: "Repetierflinte",
        sort: 1,
      },
    ],
  } as TurnierUebersicht;
}
