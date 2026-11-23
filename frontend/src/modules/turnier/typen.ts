/**
 * Typen des Turnier-Moduls. Quelle ist `schema.gen.ts`; hier stehen nur sprechende Namen.
 * Was das Backend (noch) nicht beschreibt, ist unten lokal definiert und als solches markiert.
 */
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

export type Turnier = Schemas["TournamentOut"];
export type TurnierUebersicht = Schemas["TournamentOverview"];
export type TurnierEinstellungen = Schemas["TournamentSettings"];
export type TurnierEinstellungenAenderung = Schemas["TournamentSettingsUpdate"];
export type TurnierAnlage = Schemas["TournamentCreate"];
export type TurnierAenderung = Schemas["TournamentUpdate"];
export type TurnierStatus = Turnier["status"];
export type Vorlage = Turnier["template"];

/** „Wie ein früheres Turnier“: `POST /tournaments/{id}/copy` */
export type TurnierKopie = Schemas["TournamentCopy"];
export type KopieErgebnis = Schemas["TournamentCopyOut"];
export type KopierterWettbewerb = Schemas["CopiedCompetitionOut"];
/** Fertige Vorlage: `GET /tournament-templates`, `POST /tournaments/from-template` */
export type TurnierVorlage = Schemas["TournamentTemplateOut"];
export type VorlagenAnlage = Schemas["TournamentFromTemplate"];

export type Stand = Schemas["RangeOut"];
export type StandAnlage = Schemas["RangeCreate"];
export type StandAenderung = Schemas["RangeUpdate"];

export type TurnierKlasse = Schemas["ClassOut"];
export type KlasseAnlage = Schemas["ClassCreate"];
export type KlasseAenderung = Schemas["ClassUpdate"];

export type Wettbewerb = Schemas["CompetitionOut"];
export type WettbewerbAnlage = Schemas["CompetitionCreate"];
export type WettbewerbAenderung = Schemas["CompetitionUpdate"];
export type Definition = Schemas["CompetitionDefinition"];
export type Erfassungsart = Wettbewerb["capture_mode"];
export type MehrfachRegel = Wettbewerb["multi_start_rule"];
export type Planung = Wettbewerb["planning"];

export const STATUS_FOLGE: readonly TurnierStatus[] = ["draft", "active", "closed"];
export const VORLAGEN: readonly Vorlage[] = ["open", "club_championship", "custom"];

// --- Lokal definiert, bis das Backend sie beschreibt -------------------------------------------

/** Einstellungen, die das Backend erst später liefert; fehlen sie, blendet die Oberfläche sie aus. */
export interface ZusatzEinstellungen {
  first_start_number?: number | null;
}

/** Änderung der Definition mit Grund (aktives Turnier). Feldname laut Backend-Absprache. */
export interface DefinitionGrund {
  reason?: string | null;
}

/** Ein Eintrag aus `GET …/competitions/{id}/revisions` (Backend `RevisionOut`, gekürzt). */
export interface Revision {
  revision: number;
  created_at: string;
  reason: string | null;
}

/** Antwort von `GET …/competitions/{id}/catalog-diff` (Backend `CatalogDiffOut`). */
export interface KatalogVergleich {
  deviates: boolean;
  catalog_available?: boolean;
  differences: { path: string; text: string; section_id?: string | null }[];
}
