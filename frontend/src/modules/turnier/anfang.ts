/**
 * Hilfen für die drei Wege, ein Turnier zu beginnen (leer, wie ein früheres, aus einer Vorlage):
 * Datum und Name vorschlagen, doppelte Namen erkennen, Hinweise nach dem Kopieren merken.
 */
import type { KopierterWettbewerb, Turnier } from "./typen";

const zwei = (zahl: number) => String(zahl).padStart(2, "0");

/** Heutiges Datum als `JJJJ-MM-TT` (Ortszeit). */
export function heute(jetzt = new Date()): string {
  return `${jetzt.getFullYear()}-${zwei(jetzt.getMonth() + 1)}-${zwei(jetzt.getDate())}`;
}

/** Datum um ganze Jahre verschieben; der 29. Februar wird in Nicht-Schaltjahren der 28. */
function plusJahre(datum: string, jahre: number): string {
  const [j, m, t] = datum.split("-").map(Number) as [number, number, number];
  const ziel = j + jahre;
  const letzter = new Date(ziel, m, 0).getDate();
  return `${ziel}-${zwei(m)}-${zwei(Math.min(t, letzter))}`;
}

/**
 * Vorschlag für den Termin der Kopie: derselbe Tag ein Jahr später, und so lange ein weiteres
 * Jahr, bis der Tag nicht mehr in der Vergangenheit liegt („wie letztes Jahr“).
 */
export function naechsterTermin(quelle: string, heuteDatum = heute()): string {
  let jahre = 1;
  let vorschlag = plusJahre(quelle, jahre);
  while (vorschlag < heuteDatum && jahre < 50) {
    jahre += 1;
    vorschlag = plusJahre(quelle, jahre);
  }
  return vorschlag;
}

const JAHR = /\b(?:19|20)\d{2}\b/g;

/**
 * Name der Kopie: Steht im Namen eine Jahreszahl, wird die letzte durch das neue Jahr ersetzt
 * („Herbstpokal 2026“ → „Herbstpokal 2027“); sonst wird das Jahr angehängt.
 */
export function nameMitJahr(name: string, jahr: string): string {
  const basis = name.trim();
  const treffer = [...basis.matchAll(JAHR)];
  const letzter = treffer[treffer.length - 1];
  if (!letzter || letzter.index === undefined) return `${basis} ${jahr}`;
  return basis.slice(0, letzter.index) + jahr + basis.slice(letzter.index + letzter[0].length);
}

/** Gibt es schon ein Turnier mit diesem Namen? Groß-/Kleinschreibung und Leerzeichen zählen nicht. */
export function nameVergeben(name: string, turniere: readonly Turnier[]): boolean {
  const gesucht = name.trim().replace(/\s+/g, " ").toLocaleLowerCase("de");
  if (!gesucht) return false;
  return turniere.some(
    (turnier) => turnier.name.trim().replace(/\s+/g, " ").toLocaleLowerCase("de") === gesucht,
  );
}

/** Anzahl der Turniertage (1 bei einem eintägigen Turnier). */
export function tage(turnier: Pick<Turnier, "date_from" | "date_to">): number {
  const tag = (datum: string) => {
    const [j, m, t] = datum.split("-").map(Number) as [number, number, number];
    return Date.UTC(j, m - 1, t);
  };
  return Math.round((tag(turnier.date_to) - tag(turnier.date_from)) / 86_400_000) + 1;
}

/** Turniere, die sich als Vorbild eignen: jüngstes zuerst, das Übungsturnier zuletzt. */
export function vorbilder(turniere: readonly Turnier[]): Turnier[] {
  return [...turniere].sort(
    (a, b) =>
      Number(a.is_practice) - Number(b.is_practice) ||
      b.date_from.localeCompare(a.date_from) ||
      a.name.localeCompare(b.name, "de"),
  );
}

// --- Hinweis nach dem Kopieren -----------------------------------------------------------------

/** Ein Wettbewerb der Kopie, dessen Katalog-Disziplin sich seit dem Vorbild geändert hat. */
export interface GeaenderterWettbewerb {
  id: string;
  name: string;
  /** Unterschiede in Klartext, wie der Server sie beim Kopieren beschrieben hat */
  punkte: string[];
}

export interface KopieHinweisDaten {
  /** Name des Vorbilds („seit „Herbstpokal 2026““) */
  quelle: string;
  wettbewerbe: GeaenderterWettbewerb[];
}

const SPEICHER = (turnierId: string) => `schiesshub.kopie.${turnierId}`;

/** Aus der Antwort von `POST …/copy`: nur Wettbewerbe mit `catalog_changed`. */
export function geaenderteWettbewerbe(
  wettbewerbe: readonly KopierterWettbewerb[],
): GeaenderterWettbewerb[] {
  return wettbewerbe
    .filter((w) => w.catalog_changed)
    .map((w) => ({
      id: w.id,
      name: w.name,
      punkte: w.catalog_diff.differences.map((d) => d.text).filter(Boolean),
    }));
}

/**
 * Merkt sich auf diesem Gerät, welche Wettbewerbe der Kopie zu prüfen sind. Die Einrichtung zeigt
 * den Hinweis, bis er ausgeblendet wird oder kein Wettbewerb mehr abweicht.
 */
export function merkeKopieHinweis(turnierId: string, daten: KopieHinweisDaten): void {
  if (daten.wettbewerbe.length === 0) return;
  try {
    window.localStorage.setItem(SPEICHER(turnierId), JSON.stringify(daten));
  } catch {
    // Ohne Speicher (privates Fenster) gibt es den Hinweis eben nicht.
  }
}

export function leseKopieHinweis(turnierId: string): KopieHinweisDaten | null {
  try {
    const roh = window.localStorage.getItem(SPEICHER(turnierId));
    if (!roh) return null;
    const daten = JSON.parse(roh) as KopieHinweisDaten;
    return Array.isArray(daten?.wettbewerbe) ? daten : null;
  } catch {
    return null;
  }
}

export function vergissKopieHinweis(turnierId: string): void {
  try {
    window.localStorage.removeItem(SPEICHER(turnierId));
  } catch {
    // nichts zu tun
  }
}
