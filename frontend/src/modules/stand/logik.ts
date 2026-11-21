/**
 * Reine Regeln der Ablaufsteuerung am Stand: ohne React, einzeln getestet.
 */
import type { Bahn, Durchgang, StationStart } from "../anmeldung/api";

/** Gerätespeicher: je Turnier die ID des gewählten Stands (nur IDs). */
export type StandWahl = Record<string, string>;

/** Gewählter Stand: gespeicherte Wahl, solange es ihn gibt; bei genau einem Stand dieser. */
export function bestimmeStand(
  staende: readonly { id: string }[],
  wahl: StandWahl | null | undefined,
  turnierId: string,
): string | null {
  const gespeichert = wahl?.[turnierId];
  if (gespeichert && staende.some((stand) => stand.id === gespeichert)) return gespeichert;
  if (staende.length === 1) return staende[0]?.id ?? null;
  return null;
}

// --- Zeit ----------------------------------------------------------------------------------------

function zweistellig(zahl: number): string {
  return String(zahl).padStart(2, "0");
}

/** Lokales Datum `2026-12-05` eines Zeitpunkts. */
export function lokalesDatum(wert: string | Date): string {
  const datum = typeof wert === "string" ? new Date(wert) : wert;
  return `${datum.getFullYear()}-${zweistellig(datum.getMonth() + 1)}-${zweistellig(datum.getDate())}`;
}

/** Lokale Uhrzeit `14:05` eines Zeitpunkts. */
export function lokaleUhrzeit(wert: string | Date): string {
  const datum = typeof wert === "string" ? new Date(wert) : wert;
  return `${zweistellig(datum.getHours())}:${zweistellig(datum.getMinutes())}`;
}

/**
 * Datum und Uhrzeit aus den Eingabefeldern (lokale Zeit des Geräts) als ISO-Zeitpunkt mit Zone.
 * Unvollständige oder unlesbare Eingaben ergeben `null`.
 */
export function zeitpunktAusEingabe(datum: string, uhrzeit: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(datum) || !/^\d{2}:\d{2}$/.test(uhrzeit)) return null;
  const wert = new Date(`${datum}T${uhrzeit}:00`);
  return Number.isNaN(wert.getTime()) ? null : wert.toISOString();
}

/** Vorschlag für das Datum einer neuen Serie: heute, wenn es im Turnierzeitraum liegt, sonst der erste Tag. */
export function vorschlagDatum(von: string, bis: string, heute: Date = new Date()): string {
  const tag = lokalesDatum(heute);
  return tag >= von && tag <= bis ? tag : von;
}

// --- Belegung ------------------------------------------------------------------------------------

/** Ob ein Start einen Platz belegt (abgebrochene geben ihn frei). */
export function belegtPlatz(start: StationStart): boolean {
  return start.status !== "aborted";
}

/** Bahnen 1…Kapazität eines Durchgangs mit dem Start darauf (oder `null`). */
export function belegungDurchgang(
  durchgang: Durchgang,
  starts: readonly StationStart[],
): { bahn: number; start: StationStart | null }[] {
  const imDurchgang = starts.filter((s) => s.heat_id === durchgang.id && belegtPlatz(s));
  const hoechste = Math.max(durchgang.capacity, ...imDurchgang.map((s) => s.lane ?? 0));
  return Array.from({ length: hoechste }, (_, index) => {
    const bahn = index + 1;
    return { bahn, start: imDurchgang.find((s) => s.lane === bahn) ?? null };
  });
}

/** Freie Bahnen eines Durchgangs; `ohneStart` zählt als frei (der Start, der umgesetzt wird). */
export function freieBahnenDurchgang(
  durchgang: Durchgang,
  starts: readonly StationStart[],
  ohneStart?: string,
): number[] {
  return belegungDurchgang(durchgang, starts)
    .filter(
      ({ start, bahn }) => bahn <= durchgang.capacity && (!start || start.start_id === ohneStart),
    )
    .map(({ bahn }) => bahn);
}

/** Freie Bahnen des Stands (für die Reihenfolge). */
export function freieBahnen(bahnen: readonly Bahn[]): number[] {
  return bahnen.filter((bahn) => bahn.start === null).map((bahn) => bahn.lane);
}

/** Anmeldungen, die gerade auf einer Bahn dieses Stands stehen. */
export function besetzteAnmeldungen(bahnen: readonly Bahn[]): Set<string> {
  return new Set(bahnen.flatMap((bahn) => (bahn.start ? [bahn.start.entry_id] : [])));
}

/** Durchgänge nach Beginn, bei gleicher Zeit nach Nummer. */
export function sortiereDurchgaenge(durchgaenge: readonly Durchgang[]): Durchgang[] {
  return [...durchgaenge].sort(
    (a, b) => a.starts_at.localeCompare(b.starts_at) || a.number - b.number,
  );
}

/** Erster Durchgang (nach Zeit), in dem noch ein Start wartet. */
export function naechsterWartenderDurchgang(
  durchgaenge: readonly Durchgang[],
  starts: readonly StationStart[],
): Durchgang | null {
  const mitWartenden = new Set(
    starts.filter((s) => s.status === "registered" && s.heat_id).map((s) => s.heat_id),
  );
  return sortiereDurchgaenge(durchgaenge).find((d) => mitWartenden.has(d.id)) ?? null;
}

/** Ob ein Durchgang vorbei ist und niemand mehr darin wartet oder schießt. */
export function durchgangErledigt(
  durchgang: Durchgang,
  starts: readonly StationStart[],
  jetzt: Date = new Date(),
): boolean {
  if (new Date(durchgang.ends_at).getTime() > jetzt.getTime()) return false;
  return !starts.some(
    (s) => s.heat_id === durchgang.id && (s.status === "registered" || s.status === "called"),
  );
}

// --- Hauptaktion ---------------------------------------------------------------------------------

export type HauptAktion =
  | { art: "naechste" }
  | { art: "durchgang"; durchgang: Durchgang }
  | { art: "keine" };

/**
 * Genau eine Hauptaktion je Ansicht: „Nächste aufrufen“, wenn auf dem Stand Wettbewerbe nach
 * Reihenfolge laufen; sonst „Durchgang aufrufen“ für den nächsten Durchgang mit Wartenden.
 */
export function hauptAktion(
  mitReihenfolge: boolean,
  naechsterDurchgang: Durchgang | null,
): HauptAktion {
  if (mitReihenfolge) return { art: "naechste" };
  if (naechsterDurchgang) return { art: "durchgang", durchgang: naechsterDurchgang };
  return { art: "keine" };
}

/**
 * Wer bei „Nächsten auf Bahn n“ drankommt: der erste Wartende, der nicht schon auf einer Bahn
 * steht (dieselbe Regel wie im Server beim „Nächste aufrufen“).
 */
export function ersterAufrufbarer(
  wartende: readonly StationStart[],
  besetzt: ReadonlySet<string>,
): StationStart | null {
  return wartende.find((start) => !besetzt.has(start.entry_id)) ?? null;
}
