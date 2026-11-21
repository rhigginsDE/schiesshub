import type { TurnierUebersicht } from "./typen";

/** Bereiche der Einrichtung, in der Reihenfolge der Navigation. */
export const BEREICHE = [
  "stammdaten",
  "staende",
  "klassen",
  "wettbewerbe",
  "ausschreibung",
  "einstellungen",
  "zusammenfassung",
] as const;

export type Bereich = (typeof BEREICHE)[number];

export function istBereich(wert: unknown): wert is Bereich {
  return typeof wert === "string" && (BEREICHE as readonly string[]).includes(wert);
}

/** Ein offener Punkt: in welchem Bereich, welcher Text (Schlüssel in turnier.json → `offen.*`). */
export interface OffenerPunkt {
  bereich: Bereich;
  schluessel: string;
  werte?: Record<string, string | number>;
}

/**
 * Was vor dem Start noch fehlt. Nichts davon sperrt etwas; die Navigation zeigt
 * „unvollständig“ und die Zusammenfassung listet die Punkte auf.
 */
export function offenePunkte(turnier: TurnierUebersicht): OffenerPunkt[] {
  const punkte: OffenerPunkt[] = [];
  if (turnier.ranges.length === 0) punkte.push({ bereich: "staende", schluessel: "kein_stand" });
  if (turnier.classes.length === 0) punkte.push({ bereich: "klassen", schluessel: "keine_klasse" });
  if (turnier.competitions.length === 0) {
    punkte.push({ bereich: "wettbewerbe", schluessel: "kein_wettbewerb" });
  }
  const standIds = new Set(turnier.ranges.map((stand) => stand.id));
  for (const wettbewerb of turnier.competitions) {
    if (!wettbewerb.range_id || !standIds.has(wettbewerb.range_id)) {
      punkte.push({
        bereich: "wettbewerbe",
        schluessel: "ohne_stand",
        werte: { name: wettbewerb.name },
      });
    }
    if (wettbewerb.planning === "schedule" && !wettbewerb.heat_minutes) {
      punkte.push({
        bereich: "wettbewerbe",
        schluessel: "ohne_dauer",
        werte: { name: wettbewerb.name },
      });
    }
  }
  return punkte;
}

export function unvollstaendigeBereiche(punkte: readonly OffenerPunkt[]): Set<Bereich> {
  return new Set(punkte.map((punkt) => punkt.bereich));
}
