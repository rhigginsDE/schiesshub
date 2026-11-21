/**
 * Daten der Teilnehmerverwaltung: Typen, Query-Keys, Abfragen und schreibende Anfragen.
 * Alle Keys beginnen mit `teilnehmer`, damit Server-Ereignisse (`person.*`, `club.*`) sie mit einem
 * Aufruf neu laden können (siehe manifest.ts).
 */
import { queryOptions } from "@tanstack/react-query";
import {
  ApiFehler,
  type ApiFehlerArt,
  apiDatei,
  apiGet,
  apiSenden,
  apiUrl,
  type Datei,
} from "../../api/client";
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

export type Person = Schemas["PersonOut"];
export type Verein = Schemas["ClubOut"];
export type Dublette = Schemas["DuplicateOut"];
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
};

export interface Trefferliste {
  personen: Person[];
  /** Gesamtzahl passender Personen (kann größer sein als `personen.length`) */
  gesamt: number;
}

// Wie in api/client.ts; dort ist die Zuordnung nicht exportiert.
function artAusStatus(status: number): ApiFehlerArt {
  if (status === 401) return "nicht_angemeldet";
  if (status === 403) return "verboten";
  if (status === 404) return "nicht_gefunden";
  if (status === 409) return "konflikt";
  if (status === 429) return "gesperrt";
  if (status === 502 || status === 503 || status === 504) return "netzwerk";
  if (status >= 500) return "server";
  return "anfrage";
}

/**
 * `GET /persons` mit Gesamtzahl aus dem Header `X-Total-Count`. `apiGet` liefert keine Header,
 * deshalb hier ein eigener kleiner Abruf auf Basis von `apiUrl`.
 */
export async function personenSuchen(q: string, signal?: AbortSignal): Promise<Trefferliste> {
  const pfad = "/persons";
  let antwort: Response;
  try {
    antwort = await fetch(apiUrl(pfad, { q: q.trim(), limit: TREFFER_LIMIT }), {
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (fehler) {
    if (fehler instanceof DOMException && fehler.name === "AbortError") throw fehler;
    throw new ApiFehler("netzwerk", pfad);
  }
  if (!antwort.ok) {
    let detail: string | undefined;
    try {
      const inhalt = (await antwort.json()) as { detail?: unknown };
      detail = typeof inhalt.detail === "string" ? inhalt.detail : undefined;
    } catch {
      detail = undefined;
    }
    throw new ApiFehler(artAusStatus(antwort.status), pfad, antwort.status, detail);
  }
  let personen: Person[];
  try {
    personen = (await antwort.json()) as Person[];
  } catch {
    throw new ApiFehler("format", pfad, antwort.status);
  }
  const kopf = antwort.headers.get("X-Total-Count");
  const gesamt = kopf !== null && /^\d+$/.test(kopf) ? Number(kopf) : personen.length;
  return { personen, gesamt };
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

export type AnlegenErgebnis =
  | { art: "angelegt"; person: Person }
  | { art: "dublette"; dublette: Dublette };

/** `POST /persons`. 409 mit Kandidaten ist kein Fehler, sondern ein Hinweis auf eine Dublette. */
export async function personAnlegen(daten: PersonNeu, trotzdem = false): Promise<AnlegenErgebnis> {
  const antwort = await apiSenden<Person | Dublette>("POST", "/persons", daten, {
    parameter: { force: trotzdem ? true : undefined },
    auchBeiStatus: [409],
  });
  if ("candidates" in antwort) return { art: "dublette", dublette: antwort };
  return { art: "angelegt", person: antwort };
}

export function personAendern(id: string, daten: PersonAenderung): Promise<Person> {
  return apiSenden<Person>("PATCH", `/persons/${encodeURIComponent(id)}`, daten);
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
