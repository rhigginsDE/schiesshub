import type { TurnierUebersicht } from "./typen";

/**
 * Schritte der Einrichtung in ihrer Reihenfolge. Die Vorgaben (Startgeld usw.) stehen vor den
 * Wettbewerben, weil sie nur für Wettbewerbe gelten, die danach hinzukommen.
 */
export const BEREICHE = [
  "stammdaten",
  "staende",
  "klassen",
  "einstellungen",
  "wettbewerbe",
  "ausschreibung",
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
 * Was vor dem Start noch fehlt. Nichts davon sperrt etwas; die Schrittliste zeigt „Fehlt noch“
 * und die Zusammenfassung listet die Punkte auf.
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

/**
 * Zustand eines Schritts in der Liste: erledigt, fehlt noch (mit kurzem Grund), optional, oder
 * – beim letzten Schritt – ohne eigenen Zustand.
 */
export type SchrittZustand =
  | { art: "erledigt" }
  | { art: "fehlt"; schluessel: string; anzahl: number }
  | { art: "optional" }
  | { art: "ohne" };

/** Zustand je Schritt aus den vorhandenen Daten. */
export function schrittZustaende(
  turnier: TurnierUebersicht,
  punkte: readonly OffenerPunkt[],
): Record<Bereich, SchrittZustand> {
  const fehlt = (bereich: Bereich): SchrittZustand | null => {
    const eigene = punkte.filter((punkt) => punkt.bereich === bereich);
    const erster = eigene[0];
    if (!erster) return null;
    const gleiche = eigene.filter((punkt) => punkt.schluessel === erster.schluessel).length;
    return { art: "fehlt", schluessel: erster.schluessel, anzahl: gleiche };
  };
  return {
    stammdaten: { art: "erledigt" },
    staende: fehlt("staende") ?? { art: "erledigt" },
    klassen: fehlt("klassen") ?? { art: "erledigt" },
    // Vorgaben haben Standardwerte; „erledigt“, sobald ein Startgeld vorgegeben ist.
    einstellungen:
      turnier.settings.default_fee_first_cents > 0 ? { art: "erledigt" } : { art: "optional" },
    wettbewerbe: fehlt("wettbewerbe") ?? { art: "erledigt" },
    ausschreibung: { art: "optional" },
    zusammenfassung: { art: "ohne" },
  };
}

/** Wohin die Einrichtung ohne Angabe führt: zum ersten Schritt, in dem noch etwas fehlt. */
export function ersterOffenerSchritt(
  zustaende: Record<Bereich, SchrittZustand>,
  bereiche: readonly Bereich[] = BEREICHE,
): Bereich {
  return bereiche.find((bereich) => zustaende[bereich].art === "fehlt") ?? "zusammenfassung";
}
