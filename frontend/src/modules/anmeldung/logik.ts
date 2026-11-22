/**
 * Reine Regeln der Station Anmeldung. Sie bilden nach, was der Server rechnet
 * (`backend/app/modules/starts/rules.py`), damit die Kasse den Betrag vorher sieht.
 * Maßgeblich bleibt die Antwort des Servers: Er schreibt den Betrag am Start fest.
 */
import type { ChipTon } from "../../components/Chip";
import type { TurnierKlasse, Wettbewerb } from "../turnier/typen";
import type { Anmeldung, Start } from "./api";

/** Wie viele Starts eine Person im Wettbewerb höchstens haben kann (`check_start_limit`). */
export function startGrenze(wettbewerb: Pick<Wettbewerb, "multi_start" | "max_starts">): number {
  return wettbewerb.multi_start ? Math.max(1, wettbewerb.max_starts) : 1;
}

/**
 * Gebuchte Starts der Anmeldung im Wettbewerb. Wie im Server zählen alle Starts, auch
 * abgebrochene; nur ein Storno gibt einen Platz frei.
 */
export function gebuchteStarts(anmeldung: Anmeldung | null | undefined, wettbewerbId: string) {
  return anmeldung?.starts.filter((start) => start.competition_id === wettbewerbId).length ?? 0;
}

export type Sperre =
  /** Die Klasse ist im Wettbewerb nicht zugelassen */
  | { art: "klasse"; klasse: string }
  /** Der Wettbewerb lässt nur bestimmte Klassen zu, es ist aber noch keine gewählt */
  | { art: "ohne_klasse" }
  /** Die Höchstzahl an Starts ist erreicht */
  | { art: "voll"; grenze: number };

/** Ob und warum im Wettbewerb kein weiterer Start buchbar ist. */
export function sperreFuer(
  wettbewerb: Pick<Wettbewerb, "class_ids" | "multi_start" | "max_starts">,
  klasse: Pick<TurnierKlasse, "id" | "name"> | null,
  bereits: number,
): Sperre | null {
  if (wettbewerb.class_ids.length > 0) {
    if (!klasse) return { art: "ohne_klasse" };
    if (!wettbewerb.class_ids.includes(klasse.id)) return { art: "klasse", klasse: klasse.name };
  }
  const grenze = startGrenze(wettbewerb);
  if (bereits >= grenze) return { art: "voll", grenze };
  return null;
}

/** Wie viele Starts im Wettbewerb noch dazukommen können. */
export function nochBuchbar(
  wettbewerb: Pick<Wettbewerb, "multi_start" | "max_starts">,
  bereits: number,
): number {
  return Math.max(0, startGrenze(wettbewerb) - bereits);
}

export type MengenHinweis =
  /** Es können noch `anzahl` Starts dazukommen (die gerade gewählten schon abgezogen) */
  | { art: "noch"; anzahl: number }
  /** Mit den gewählten Starts ist die Höchstzahl erreicht; „+“ ist deshalb gesperrt */
  | { art: "grenze"; grenze: number };

/**
 * Text unter „− n +“: wie viele Starts nach den gerade gewählten noch gehen. Ist die Grenze
 * erreicht, sagt der Hinweis das, statt „noch 0 möglich“ neben einem grauen „+“ zu zeigen.
 */
export function mengenHinweis(
  wettbewerb: Pick<Wettbewerb, "multi_start" | "max_starts">,
  bereits: number,
  neu: number,
): MengenHinweis {
  const rest = nochBuchbar(wettbewerb, bereits) - Math.max(0, neu);
  if (rest > 0) return { art: "noch", anzahl: rest };
  return { art: "grenze", grenze: startGrenze(wettbewerb) };
}

/**
 * Welche Meldung nach dem Speichern passt:
 * - `angemeldet`: neu angemeldet, mit Starts (Erfolg)
 * - `ohne_start`: neu angemeldet, aber noch kein Start gebucht (neutraler Hinweis, kein Erfolg)
 * - `gebucht`: weitere Starts für eine vorhandene Anmeldung (Erfolg)
 * - `geaendert`: nur Klasse oder Startnummer geändert, nichts zu zahlen
 */
export type BestaetigungsArt = "angemeldet" | "ohne_start" | "gebucht" | "geaendert";

export function bestaetigungsArt(neu: boolean, starts: number): BestaetigungsArt {
  if (neu) return starts > 0 ? "angemeldet" : "ohne_start";
  return starts > 0 ? "gebucht" : "geaendert";
}

export interface Betrag {
  cents: number;
  /** 1, wenn der erste Start der Person im Wettbewerb dabei ist */
  erste: number;
  /** Anzahl Nachkäufe (jeder weitere Start) */
  nachkauf: number;
}

/**
 * Betrag für `neu` weitere Starts, wenn schon `bereits` gebucht sind (`start_fee`): Der erste
 * Start kostet `fee_first_cents`, jeder weitere `fee_repeat_cents`.
 */
export function betragVorschau(
  wettbewerb: Pick<Wettbewerb, "fee_first_cents" | "fee_repeat_cents">,
  bereits: number,
  neu: number,
): Betrag {
  if (neu <= 0) return { cents: 0, erste: 0, nachkauf: 0 };
  const erste = bereits === 0 ? 1 : 0;
  const nachkauf = neu - erste;
  return {
    cents: erste * wettbewerb.fee_first_cents + nachkauf * wettbewerb.fee_repeat_cents,
    erste,
    nachkauf,
  };
}

/** Summe mehrerer Beträge. */
export function summe(betraege: readonly Betrag[]): Betrag {
  return betraege.reduce(
    (gesamt, b) => ({
      cents: gesamt.cents + b.cents,
      erste: gesamt.erste + b.erste,
      nachkauf: gesamt.nachkauf + b.nachkauf,
    }),
    { cents: 0, erste: 0, nachkauf: 0 },
  );
}

/** Kleinste freie Startnummer ab `ab` – Vorschau dessen, was der Server vergibt (`next_free_number`). */
export function naechsteStartnummer(anmeldungen: readonly Anmeldung[], ab: number): number {
  const vergeben = new Set(anmeldungen.map((a) => a.start_number));
  let nummer = Math.max(1, ab);
  while (vergeben.has(nummer)) nummer += 1;
  return nummer;
}

export interface StatusAnzeige {
  /** Schlüssel in `anmeldung:status.*` */
  schluessel: "angemeldet" | "aufgerufen" | "erfasst" | "abgeschlossen" | "dns" | "dnf" | "dsq";
  ton: ChipTon;
  bahn: number | null;
}

/** Text und Farbe zum Status eines Starts. */
export function statusAnzeige(
  start: Pick<Start, "status" | "abort_reason" | "lane">,
): StatusAnzeige {
  switch (start.status) {
    case "registered":
      return { schluessel: "angemeldet", ton: "neutral", bahn: start.lane };
    case "called":
      return { schluessel: "aufgerufen", ton: "info", bahn: start.lane };
    case "captured":
      return { schluessel: "erfasst", ton: "info", bahn: start.lane };
    case "final":
      return { schluessel: "abgeschlossen", ton: "gruen", bahn: start.lane };
    case "aborted":
      return {
        schluessel: start.abort_reason ?? "dns",
        ton: start.abort_reason === "dns" ? "warn" : "krit",
        bahn: start.lane,
      };
  }
}

export type StornoSperre = "aufgerufen" | "geschossen" | "abgebrochen";

/** Stornieren geht nur, solange der Start noch nicht aufgerufen wurde (Server: `cancel_start`). */
export function stornoSperre(start: Pick<Start, "status">): StornoSperre | null {
  if (start.status === "registered") return null;
  if (start.status === "called") return "aufgerufen";
  if (start.status === "aborted") return "abgebrochen";
  return "geschossen";
}

/**
 * Ob die Anmeldung gelöscht werden kann. Der Server lehnt ab, sobald ein Start aufgerufen,
 * geschossen oder abgebrochen ist (auch „nicht angetreten“ steht im Ergebnisprotokoll).
 */
export function loeschbar(anmeldung: Anmeldung): boolean {
  return anmeldung.starts.every((start) => start.status === "registered");
}

function normal(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase("de");
}

/**
 * Suche in den Anmeldungen (rechte Liste): genaue Startnummer zuerst, dann Name oder Verein.
 * Läuft nur im Speicher; der Suchtext verlässt die Seite nicht.
 */
export function sucheAnmeldungen(anmeldungen: readonly Anmeldung[], text: string): Anmeldung[] {
  const q = text.trim();
  if (!q) return [...anmeldungen];
  const nummer = /^\d+$/.test(q) ? Number(q) : null;
  const genau = nummer === null ? [] : anmeldungen.filter((a) => a.start_number === nummer);
  const teile = normal(q).split(/\s+/);
  const weitere = anmeldungen.filter((a) => {
    if (genau.includes(a)) return false;
    const heuhaufen = normal(`${a.person.name} ${a.person.club ?? ""} ${a.start_number}`);
    return teile.every((teil) => heuhaufen.includes(teil));
  });
  return [...genau, ...weitere];
}

export interface Kennzahlen {
  schuetzen: number;
  starts: number;
  cents: number;
}

/** Kennzahlen des Turniers; abgebrochene Starts zählen mit, ihr Startgeld ist gebucht. */
export function kennzahlen(anmeldungen: readonly Anmeldung[]): Kennzahlen {
  return {
    schuetzen: anmeldungen.length,
    starts: anmeldungen.reduce((n, a) => n + a.starts.length, 0),
    cents: anmeldungen.reduce((n, a) => n + a.fee_total_cents, 0),
  };
}
