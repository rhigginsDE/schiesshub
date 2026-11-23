import { queryOptions } from "@tanstack/react-query";
import { schluessel } from "../../api/abfragen";
import { ApiFehler, apiGet, istWartungsFehler } from "../../api/client";
import type { components } from "../../api/schema.gen";

/**
 * Geführte Wiederherstellung einer Sicherung (`/backup/restore/*`): Typen, Abfragen und die
 * Entscheidungen des Ablaufs, getrennt von der Oberfläche, damit sie sich testen lassen.
 */

type Schemas = components["schemas"];
export type Quelle = Schemas["RestoreSourceOut"];
export type Quellen = Schemas["RestoreSourcesOut"];
export type Vorschau = Schemas["RestorePreviewOut"];
export type WiederherstellungsStatus = Schemas["RestoreStatusOut"];
export type WiederherstellungsSchritt = Schemas["RestoreStepOut"];
export type AusfuehrenAnfrage = Schemas["RestoreExecuteIn"];
export type SchrittId = WiederherstellungsSchritt["key"];

/** Unter `sicherung.alle`: Ereignisse der Sicherung laden das mit neu. */
export const WIEDERHERSTELLEN_SCHLUESSEL = {
  quellen: [...schluessel.sicherung.alle, "wiederherstellen", "quellen"] as const,
  status: [...schluessel.sicherung.alle, "wiederherstellen", "status"] as const,
};

/** So oft fragt die Seite während der Wiederherstellung nach dem Fortschritt. */
export const ABFRAGE_MS = 1500;

export const quellenAbfrage = () =>
  queryOptions({
    queryKey: WIEDERHERSTELLEN_SCHLUESSEL.quellen,
    queryFn: ({ signal }) => apiGet<Quellen>("/backup/restore/sources", { signal }),
    staleTime: 0,
  });

/**
 * Fortschritt. Still, weil sich der Zugang mit dem Tausch der Datenbank ändern kann: Dann zeigt
 * die Seite selbst, was zu tun ist, statt zur Anmeldung zu springen.
 */
export const statusAbfrage = (beobachten: boolean) =>
  queryOptions({
    queryKey: WIEDERHERSTELLEN_SCHLUESSEL.status,
    queryFn: ({ signal }) =>
      apiGet<WiederherstellungsStatus>("/backup/restore/status", { signal, still: true }),
    refetchInterval: (abfrage) =>
      beobachten && weiterFragen(abfrage.state.data, abfrage.state.error) ? ABFRAGE_MS : false,
    retry: false,
  });

/**
 * Weiter nach dem Fortschritt fragen? Solange die Wiederherstellung läuft, und auch dann, wenn der
 * Server beim Umschalten kurz gar nicht oder mit 503 antwortet. Nicht mehr, wenn der Zugang weg ist.
 */
export function weiterFragen(
  status: WiederherstellungsStatus | undefined,
  fehler: unknown,
): boolean {
  if (fehler) return istKurzeUnterbrechung(fehler) && !istZugangWeg(fehler);
  return status?.state === "running";
}

/**
 * Fehler beim Abfragen des Fortschritts, die während einer laufenden Wiederherstellung dazugehören:
 * Wartung (503, `code: maintenance`) und kurz keine Antwort beim Umschalten der Datenbank.
 */
export function istKurzeUnterbrechung(fehler: unknown): boolean {
  return istWartungsFehler(fehler) || (fehler instanceof ApiFehler && fehler.art === "netzwerk");
}

/** Zugang geändert: Nach dem Tausch gelten Konten und Geräte aus der Sicherung. */
export function istZugangWeg(fehler: unknown): boolean {
  return (
    fehler instanceof ApiFehler && (fehler.art === "nicht_angemeldet" || fehler.art === "verboten")
  );
}

export type Ansicht = "waehlen" | "passwort" | "vorschau" | "bestaetigen" | "fortschritt";

/** Die Schritte, wie die Kopfzeile des Ablaufs sie zeigt. */
export const ANSICHTEN: readonly Ansicht[] = [
  "waehlen",
  "passwort",
  "vorschau",
  "bestaetigen",
  "fortschritt",
];

/** Beim Öffnen: Läuft schon eine Wiederherstellung, gleich den Fortschritt zeigen. */
export function startAnsicht(status: WiederherstellungsStatus | undefined): Ansicht {
  return status?.state === "running" ? "fortschritt" : "waehlen";
}

/** Nach der Wahl einer Sicherung: Passwort nur, wenn sie verschlüsselt ist. */
export function nachDerWahl(quelle: Quelle): Ansicht {
  return quelle.needs_passphrase ? "passwort" : "vorschau";
}

/** Schritt, der gerade läuft, oder der zuletzt fehlgeschlagene. */
export function aktuellerSchritt(status: WiederherstellungsStatus): SchrittId | null {
  const fehler = status.steps.find((schritt) => schritt.state === "failed");
  return fehler?.key ?? status.step ?? null;
}

/**
 * Schritte vor dem Tausch: Schlägt einer davon fehl, verwirft der Server die neue Datenbank, und
 * die bisherigen Daten sind unverändert.
 */
const VOR_DEM_TAUSCH: ReadonlySet<SchrittId> = new Set([
  "check",
  "maintenance",
  "pre_backup",
  "load",
  "upgrade",
  "journal",
  "verify",
]);

/** Sind die bisherigen Daten nach einem Fehler sicher unverändert? */
export function datenUnveraendert(status: WiederherstellungsStatus): boolean {
  if (status.state !== "failed") return false;
  const schritt = aktuellerSchritt(status);
  return schritt === null || VOR_DEM_TAUSCH.has(schritt);
}

/** Beim Umschalten (und kurz danach) ist der Server ein paar Sekunden nicht erreichbar. */
export function umschaltenLaeuft(status: WiederherstellungsStatus | undefined): boolean {
  return status?.state === "running" && (status.step === "swap" || status.step === "finish");
}

export interface Bestaetigungen {
  /** „Der jetzige Stand wird ersetzt“ */
  ersetzen: boolean;
  /** Ausdrücklich angenommen: danach an diesem Gerät kein Zugang zur Verwaltung */
  aussperren: boolean;
}

/** Was vor dem Ausführen noch fehlt; leer = es kann losgehen. */
export function fehlendeBestaetigungen(
  vorschau: Vorschau,
  bestaetigt: Bestaetigungen,
): (keyof Bestaetigungen)[] {
  const fehlt: (keyof Bestaetigungen)[] = [];
  if (vorschau.access.lockout_risk && !bestaetigt.aussperren) fehlt.push("aussperren");
  if (!bestaetigt.ersetzen) fehlt.push("ersetzen");
  return fehlt;
}

/** Die Anfrage für `POST /backup/restore/execute`; `confirm` ist laut Server die Kennung der Sicherung. */
export function ausfuehrenAnfrage(
  vorschau: Vorschau,
  passwort: string,
  nachtragen: boolean,
  aussperrenAngenommen: boolean,
): AusfuehrenAnfrage {
  return {
    source_id: vorschau.source.id,
    passphrase: vorschau.source.needs_passphrase ? passwort : null,
    confirm: vorschau.confirm,
    apply_journal: nachtragen,
    accept_lockout: vorschau.access.lockout_risk && aussperrenAngenommen,
  };
}

/** Lohnt sich die Wahl „Ergebnisse nachtragen“? Nur, wenn es eine Mitschrift dazu gibt. */
export function nachtragenMoeglich(vorschau: Vorschau): boolean {
  return vorschau.source.journal_available || vorschau.comparison.journal_applicable > 0;
}

/**
 * Was ohne Nachtragen verloren ginge: alle Ergebnis-Eingaben seit der Sicherung. Mit Nachtragen
 * nur die, die der Server als verloren meldet.
 */
export function verloreneEingaben(vorschau: Vorschau, nachtragen: boolean): number {
  const { comparison } = vorschau;
  return nachtragen ? comparison.events_lost : comparison.events_since_backup;
}
