/**
 * Startauswahl des Terminals: Bahnen am Stand, Wartende, Suche, nächster offener Start.
 * Ohne React, einzeln getestet. Grundlage ist die Startliste des Turniers (Modul `starts`).
 */
import type { Anmeldung, StationStart } from "../anmeldung/api";

/** Status einer Kachel; „in Erfassung“ ist der Start, der gerade auf diesem Gerät offen ist. */
export type KachelStatus = "offen" | "in_erfassung" | "erfasst" | "abgeschlossen" | "abgebrochen";

export function kachelStatus(start: StationStart, offenId?: string | null): KachelStatus {
  if (start.start_id === offenId && start.status !== "final" && start.status !== "aborted") {
    return "in_erfassung";
  }
  switch (start.status) {
    case "captured":
      return "erfasst";
    case "final":
      return "abgeschlossen";
    case "aborted":
      return "abgebrochen";
    default:
      return "offen";
  }
}

/** Noch nicht abgeschlossen und nicht abgebrochen. */
export function istOffen(start: StationStart): boolean {
  return start.status !== "final" && start.status !== "aborted";
}

export interface BahnBelegung {
  bahn: number;
  start: StationStart | null;
}

/**
 * Bahnen 1…Anzahl mit dem Start, der dort steht: der aufgerufene, sonst einer, der dort gerade
 * erfasst wird. (Die Sicht `queue`/`now` des Servers zeigt nur aufgerufene Starts; sobald der
 * erste Wert erfasst ist, gilt der Start als „erfasst“ und erschiene dort nicht mehr.)
 */
export function bahnenAmStand(
  starts: readonly StationStart[],
  standId: string,
  bahnAnzahl: number,
): BahnBelegung[] {
  const amStand = starts.filter((s) => s.range_id === standId && s.lane != null);
  const hoechste = Math.max(bahnAnzahl, ...amStand.map((s) => s.lane ?? 0));
  return Array.from({ length: hoechste }, (_, index) => {
    const bahn = index + 1;
    const aufBahn = amStand.filter((s) => s.lane === bahn);
    const start =
      aufBahn.find((s) => s.status === "called") ??
      aufBahn.find((s) => s.status === "captured") ??
      null;
    return { bahn, start };
  });
}

function nachReihe(a: StationStart, b: StationStart): number {
  return (
    (a.queue_position ?? Number.MAX_SAFE_INTEGER) - (b.queue_position ?? Number.MAX_SAFE_INTEGER) ||
    (a.heat_starts_at ?? "").localeCompare(b.heat_starts_at ?? "") ||
    (a.lane ?? 0) - (b.lane ?? 0) ||
    a.start_number - b.start_number ||
    a.attempt - b.attempt
  );
}

/** Angemeldete, noch nicht aufgerufene Starts des Stands in ihrer Reihenfolge. */
export function wartende(starts: readonly StationStart[], standId: string): StationStart[] {
  return starts.filter((s) => s.range_id === standId && s.status === "registered").sort(nachReihe);
}

/** Übrige Starts des Stands, die weder auf einer Bahn stehen noch warten (erfasst, abgeschlossen …). */
export function uebrige(
  starts: readonly StationStart[],
  standId: string,
  belegung: readonly BahnBelegung[],
): StationStart[] {
  const aufBahn = new Set(belegung.map((b) => b.start?.start_id).filter(Boolean));
  return starts
    .filter((s) => s.range_id === standId && s.status !== "registered" && !aufBahn.has(s.start_id))
    .sort((a, b) => a.start_number - b.start_number || a.attempt - b.attempt);
}

/** Voller Name aus den Anmeldungen (falls lesbar), sonst der Anzeigename der Startliste. */
export type Namen = ReadonlyMap<string, string>;

export function namenAus(anmeldungen: readonly Anmeldung[] | undefined): Namen {
  return new Map((anmeldungen ?? []).map((a) => [a.id, a.person.name]));
}

export function nameVon(start: StationStart, namen: Namen): string | null {
  return namen.get(start.entry_id) ?? start.display_name ?? null;
}

function vereinfacht(text: string): string {
  return text
    .toLocaleLowerCase("de")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");
}

/**
 * Suche im ganzen Turnier: Ziffern suchen die Startnummer (genau, dann beginnend),
 * Text den Namen (jedes Wort muss vorkommen).
 */
export function suche(
  starts: readonly StationStart[],
  text: string,
  namen: Namen,
  nurOffene: boolean,
): StationStart[] {
  const begriff = text.trim();
  if (begriff === "") return [];
  const kandidaten = nurOffene ? starts.filter(istOffen) : [...starts];
  if (/^\d+$/.test(begriff)) {
    const nummer = Number(begriff);
    return kandidaten
      .filter((s) => String(s.start_number).startsWith(begriff))
      .sort(
        (a, b) =>
          Number(b.start_number === nummer) - Number(a.start_number === nummer) ||
          a.start_number - b.start_number ||
          Number(istOffen(b)) - Number(istOffen(a)) ||
          a.attempt - b.attempt,
      );
  }
  const woerter = vereinfacht(begriff).split(/\s+/).filter(Boolean);
  return kandidaten
    .filter((s) => {
      const name = vereinfacht(`${nameVon(s, namen) ?? ""} ${s.display_name ?? ""}`);
      return woerter.every((wort) => name.includes(wort));
    })
    .sort((a, b) => a.start_number - b.start_number || a.attempt - b.attempt);
}

/**
 * Vorschlag nach dem Abschluss: zuerst ein offener Start auf einer Bahn des Stands, dann der
 * erste Wartende. Der gerade abgeschlossene Start zählt nicht.
 */
export function naechsterOffener(
  starts: readonly StationStart[],
  standId: string,
  bahnAnzahl: number,
  ohne: string | null,
): StationStart | null {
  const aufBahnen = bahnenAmStand(starts, standId, bahnAnzahl)
    .map((b) => b.start)
    .filter((s): s is StationStart => s !== null && s.start_id !== ohne && istOffen(s));
  if (aufBahnen[0]) return aufBahnen[0];
  return wartende(starts, standId).find((s) => s.start_id !== ohne) ?? null;
}

/** Gespeicherte Wahl des Stands je Turnier; bei genau einem Stand dieser. */
export function bestimmeStand(
  staende: readonly { id: string }[],
  wahl: Readonly<Record<string, string>> | null | undefined,
  turnierId: string,
): string | null {
  const gespeichert = wahl?.[turnierId];
  if (gespeichert && staende.some((stand) => stand.id === gespeichert)) return gespeichert;
  return staende.length === 1 ? (staende[0]?.id ?? null) : null;
}
