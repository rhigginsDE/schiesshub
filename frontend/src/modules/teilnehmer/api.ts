/**
 * Daten der Teilnehmerverwaltung: Typen, Query-Keys, Abfragen und schreibende Anfragen.
 * Alle Keys beginnen mit `teilnehmer`, damit Server-Ereignisse (`person.*`, `club.*`) sie mit einem
 * Aufruf neu laden können (siehe manifest.ts).
 */
import { queryOptions } from "@tanstack/react-query";
import {
  ApiFehler,
  apiDatei,
  apiGet,
  apiGetMitKopf,
  apiSenden,
  type Datei,
  zahlAusKopf,
} from "../../api/client";
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

export type Person = Schemas["PersonOut"];
export type Verein = Schemas["ClubOut"];
export type Dublette = Schemas["DuplicateOut"];
export type DublettenPruefung = Schemas["DuplicateCheckOut"];
export type ImportBericht = Schemas["ImportReportOut"];
export type ImportZeile = Schemas["ImportRowOut"];
export type PersonNeu = Schemas["PersonCreate"];
export type PersonAenderung = Schemas["PersonUpdate"];
export type VereinNeu = Schemas["ClubCreate"];
export type VereinAenderung = Schemas["ClubUpdate"];

/** So viele Treffer zeigt die Suche höchstens; die Gesamtzahl kommt aus `X-Total-Count`. */
export const TREFFER_LIMIT = 50;

/** Größte Importdatei, die der Server annimmt. */
export const IMPORT_MAX_BYTES = 5 * 1024 * 1024;

export const teilnehmerSchluessel = {
  alle: ["teilnehmer"] as const,
  personen: (q: string) => ["teilnehmer", "personen", q] as const,
  person: (id: string) => ["teilnehmer", "person", id] as const,
  vereine: () => ["teilnehmer", "vereine"] as const,
  dubletten: (name: string, vereinId: string | null) =>
    ["teilnehmer", "dubletten", name, vereinId ?? ""] as const,
};

export interface Trefferliste {
  personen: Person[];
  /** Gesamtzahl passender Personen (kann größer sein als `personen.length`) */
  gesamt: number;
}

/** `GET /persons` mit Gesamtzahl aus dem Header `X-Total-Count`. */
export async function personenSuchen(q: string, signal?: AbortSignal): Promise<Trefferliste> {
  // `still`: wie bisher meldet die Suche 401/403 nicht an die App-Shell; sie zeigt den Fehler selbst.
  const { daten, kopf } = await apiGetMitKopf<Person[]>("/persons", {
    parameter: { q: q.trim(), limit: TREFFER_LIMIT },
    signal,
    still: true,
  });
  return { personen: daten, gesamt: zahlAusKopf(kopf, "X-Total-Count") ?? daten.length };
}

export const personenAbfrage = (q: string) =>
  queryOptions({
    queryKey: teilnehmerSchluessel.personen(q.trim()),
    queryFn: ({ signal }) => personenSuchen(q, signal),
  });

export const personAbfrage = (id: string) =>
  queryOptions({
    queryKey: teilnehmerSchluessel.person(id),
    queryFn: ({ signal }) => apiGet<Person>(`/persons/${encodeURIComponent(id)}`, { signal }),
    retry: (anzahl, fehler) =>
      !(fehler instanceof ApiFehler && fehler.art === "nicht_gefunden") && anzahl < 2,
  });

function nachName(a: Verein, b: Verein): number {
  return a.name.localeCompare(b.name, "de", { sensitivity: "base" });
}

export const vereineAbfrage = () =>
  queryOptions({
    queryKey: teilnehmerSchluessel.vereine(),
    queryFn: async ({ signal }) => (await apiGet<Verein[]>("/clubs", { signal })).sort(nachName),
  });

/**
 * `POST /persons/check`: dieselbe Dublettenprüfung wie beim Anlegen, ohne Fehlerstatus und ohne
 * etwas anzulegen. Für den Hinweis schon während der Eingabe. `still`: Ein Fehler (z. B. 403) soll
 * hier niemanden zur Anmeldung schicken; ohne Antwort gibt es eben keinen Hinweis.
 */
export function personPruefen(
  name: string,
  vereinId: string | null,
  signal?: AbortSignal,
): Promise<DublettenPruefung> {
  return apiSenden<DublettenPruefung>(
    "POST",
    "/persons/check",
    { name, club_id: vereinId },
    { signal, still: true },
  );
}

/** Dublettenprüfung für den bereinigten Namen; nur abfragen, wenn ein Name da ist. */
export const dublettenAbfrage = (name: string, vereinId: string | null) =>
  queryOptions({
    queryKey: teilnehmerSchluessel.dubletten(name, vereinId),
    queryFn: ({ signal }) => personPruefen(name, vereinId, signal),
    enabled: name !== "",
    retry: false,
    staleTime: 10_000,
  });

export type AnlegenErgebnis =
  | { art: "angelegt"; person: Person }
  | { art: "dublette"; dublette: Dublette };

/**
 * Mit einem neuen Verein (`club_name`) meldet das Formular 403 selbst am Vereinsfeld; die App-Shell
 * soll dann nicht zusätzlich „Berechtigung fehlt“ zeigen.
 */
function stillBeiNeuemVerein(daten: { club_name?: string | null }): boolean {
  return daten.club_name != null;
}

/** `POST /persons`. 409 mit Kandidaten ist kein Fehler, sondern ein Hinweis auf eine Dublette. */
export async function personAnlegen(daten: PersonNeu, trotzdem = false): Promise<AnlegenErgebnis> {
  const antwort = await apiSenden<Person | Dublette>("POST", "/persons", daten, {
    parameter: { force: trotzdem ? true : undefined },
    auchBeiStatus: [409],
    still: stillBeiNeuemVerein(daten),
  });
  if ("candidates" in antwort) return { art: "dublette", dublette: antwort };
  return { art: "angelegt", person: antwort };
}

export function personAendern(id: string, daten: PersonAenderung): Promise<Person> {
  return apiSenden<Person>("PATCH", `/persons/${encodeURIComponent(id)}`, daten, {
    still: stillBeiNeuemVerein(daten),
  });
}

export function personLoeschen(id: string): Promise<void> {
  return apiSenden("DELETE", `/persons/${encodeURIComponent(id)}`);
}

export function vereinAnlegen(daten: VereinNeu): Promise<Verein> {
  return apiSenden<Verein>("POST", "/clubs", daten);
}

export function vereinAendern(id: string, daten: VereinAenderung): Promise<Verein> {
  return apiSenden<Verein>("PATCH", `/clubs/${encodeURIComponent(id)}`, daten);
}

export function vereinLoeschen(id: string): Promise<void> {
  return apiSenden("DELETE", `/clubs/${encodeURIComponent(id)}`);
}

/** Hängt alle Personen von `id` an `zielId` und löscht `id`. */
export function vereineZusammenfuehren(id: string, zielId: string): Promise<Verein> {
  return apiSenden<Verein>("POST", `/clubs/${encodeURIComponent(id)}/merge`, {
    into_id: zielId,
  });
}

/** `POST /persons/import` mit dem Rohinhalt der Datei; `pruefen` = nur Vorschau (dry_run). */
export function personenImportieren(inhalt: ArrayBuffer, pruefen: boolean): Promise<ImportBericht> {
  return apiSenden<ImportBericht>("POST", "/persons/import", undefined, {
    parameter: { dry_run: pruefen },
    roh: { inhalt, typ: "text/csv" },
  });
}

/** Alle Personen als CSV-Datei (`GET /persons/export.csv`). */
export function exportLaden(): Promise<Datei> {
  return apiDatei("/persons/export.csv", "personen.csv");
}

/** Lesbare Meldung zu einem Fehler beim Schreiben: Erklärung des Servers, wenn es eine gibt. */
export function fehlertext(fehler: unknown): string | undefined {
  if (!(fehler instanceof ApiFehler) || !fehler.detail) return undefined;
  // FastAPI liefert Prüffehler (422) als Liste; dann die erste Meldung zeigen.
  try {
    const liste = JSON.parse(fehler.detail) as unknown;
    if (Array.isArray(liste)) {
      const erste = liste[0] as { msg?: unknown } | undefined;
      if (erste && typeof erste.msg === "string") return erste.msg;
    }
  } catch {
    // kein JSON: Detail ist bereits ein Satz
  }
  return fehler.detail;
}
