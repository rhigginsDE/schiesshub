/**
 * Voraussetzungen, bevor die App Koppeln und PIN verlangen darf (`GET /auth/enforcement`).
 * Der Server nennt nur, was noch fehlt (`blockers`); die Liste zeigt alle Schritte mit Haken.
 */
import type { components } from "../../api/schema.gen";

export type PruefungsLage = components["schemas"]["EnforcementOut"];
export type Hindernis = components["schemas"]["BlockerOut"];

export type AufgabeId = "admin" | "geraet" | "eingeloggt";

export interface PruefungsAufgabe {
  id: AufgabeId;
  erledigt: boolean;
  /** Welcher Grund offen ist; beim Einloggen gibt es zwei (`not_logged_in`, `not_admin`). */
  code?: string;
}

/** Welche Codes des Servers zu welchem Schritt gehören. */
const SCHRITTE: readonly { id: AufgabeId; codes: readonly string[] }[] = [
  { id: "admin", codes: ["no_admin_with_pin"] },
  { id: "geraet", codes: ["device_not_paired"] },
  { id: "eingeloggt", codes: ["not_logged_in", "not_admin"] },
];

const BEKANNT = new Set(SCHRITTE.flatMap((schritt) => schritt.codes));

/** Alle Schritte in fester Reihenfolge, je erledigt oder mit dem offenen Grund. */
export function pruefungsAufgaben(hindernisse: readonly Hindernis[]): PruefungsAufgabe[] {
  const offen = new Set(hindernisse.map((hindernis) => hindernis.code));
  return SCHRITTE.map(({ id, codes }) => {
    const code = codes.find((kandidat) => offen.has(kandidat));
    return code ? { id, erledigt: false, code } : { id, erledigt: true };
  });
}

/** Hindernisse, die die App (noch) nicht kennt; sie erscheinen mit dem Text des Servers. */
export function unbekannteHindernisse(hindernisse: readonly Hindernis[]): Hindernis[] {
  return hindernisse.filter((hindernis) => !BEKANNT.has(hindernis.code));
}
