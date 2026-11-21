/**
 * Ausschreibung eines Turniers. Lokal definiert nach `backend/app/modules/turnier/schemas.py`
 * (Announcement, AnnouncementDocument), weil `schema.gen.ts` sie noch nicht enthält.
 */

export type BausteinArt = "text" | "competitions" | "classes" | "fees" | "dates" | "ranges";

export const AUTOMATISCHE_ARTEN: readonly BausteinArt[] = [
  "competitions",
  "classes",
  "fees",
  "dates",
  "ranges",
];

export interface Eckdaten {
  venue?: string | null;
  address?: string | null;
  /** ISO-Datum */
  registration_deadline?: string | null;
  registration_info?: string | null;
  contact_name?: string | null;
  contact_info?: string | null;
}

export const ECKDATEN_FELDER = [
  "venue",
  "address",
  "registration_deadline",
  "registration_info",
  "contact_name",
  "contact_info",
] as const;

export interface Baustein {
  id: string;
  kind: BausteinArt;
  heading: string;
  /** Reiner Text, Absätze durch Leerzeilen; bei automatischen Bausteinen ein Zusatztext */
  body: string;
  visible: boolean;
}

export interface Ausschreibung {
  title?: string | null;
  facts: Eckdaten;
  blocks: Baustein[];
}

// --- Zusammengesetztes Dokument (GET …/announcement/document) ---------------------------------

export interface DokumentAbschnitt {
  name: string;
  serien: number;
  schuss_je_serie: number | null;
  serien_gewertet: number | null;
  summary: string;
}

export interface DokumentWettbewerb {
  id: string;
  name: string;
  catalog_federation: string | null;
  catalog_code: string | null;
  group: string | null;
  range_name: string | null;
  procedure: string | null;
  sections: DokumentAbschnitt[];
  multi_start: boolean;
  max_starts: number;
  multi_start_rule: "best" | "first" | "all";
  multi_start_text: string;
  deviates_from_catalog: boolean;
  deviations: string[];
}

export interface DokumentGebuehr {
  competition_id: string;
  name: string;
  fee_first_cents: number;
  fee_repeat_cents: number | null;
}

export interface DokumentBaustein {
  id: string;
  kind: BausteinArt;
  heading: string;
  body: string;
  competitions?: DokumentWettbewerb[] | null;
  classes?: { name: string; short: string }[] | null;
  fees?: { currency: string; items: DokumentGebuehr[] } | null;
  dates?: { date_from: string; date_to: string; registration_deadline: string | null } | null;
  ranges?: { name: string; lane_count: number }[] | null;
}

export interface AusschreibungDokument {
  title: string;
  tournament: {
    id: string;
    name: string;
    organizer: string | null;
    date_from: string;
    date_to: string;
    status: string;
    currency: string;
  };
  facts: Eckdaten;
  blocks: DokumentBaustein[];
}
