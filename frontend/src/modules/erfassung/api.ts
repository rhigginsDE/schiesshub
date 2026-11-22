/**
 * Daten des Backend-Moduls `ergebnisse` für das Erfassungsterminal: Eingabemaske, Verlauf,
 * Prüfliste und die schreibenden Vorgänge (Rohwerte, Abschluss, Korrektur, Wiederöffnen, Abbruch).
 *
 * Schreibende Vorgänge tragen einen `Idempotency-Key`: Wiederholt das Terminal eine Sendung nach
 * einem Verbindungsabbruch mit demselben Schlüssel, schreibt der Server kein zweites Ereignis.
 * `apiSenden` aus `api/client.ts` kann noch keine eigenen Kopfzeilen setzen; deshalb sendet dieses
 * Modul selbst und nutzt dafür die Bausteine des Clients (URL, Fehlerart, Feldfehler).
 */
import { queryOptions } from "@tanstack/react-query";
import { ApiFehler, apiGet, apiUrl, artAusStatus, feldFehlerAus } from "../../api/client";
import { EREIGNIS_VERBUNDEN, type EreignisZuordnung } from "../../api/ereignisse";
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

export type Maske = Schemas["FormOut"];
export type MaskenKopf = Schemas["FormHeader"];
export type Formular = Schemas["FormDescription"];
export type AbschnittForm = Schemas["SectionForm"];
export type SerieForm = Schemas["SeriesForm"];
export type FeldBeschreibung = Schemas["FieldSpec"];
export type StatusOption = Schemas["StatusOption"];
export type PositionForm = Schemas["PositionForm"];
export type ErgebnisStand = Schemas["ResultState"];
export type Wertung = Schemas["ComputedResult"];
export type AbschnittWertung = Schemas["SectionResult"];
export type SerienWertung = Schemas["SeriesResult"];
export type Fortschritt = Schemas["Progress"];
export type VerlaufEintrag = Schemas["EventOut"];
export type PruefEintrag = Schemas["ReviewItemOut"];
export type Erfassungsart = Formular["capture_mode"];
export type Abbruchgrund = NonNullable<ErgebnisStand["abort_reason"]>;
export type StartStatus = ErgebnisStand["status"];

/** Rohwerte eines Starts, Format: docs/DATENMODELL.md („Rohwerte“). */
export type Rohwerte = Record<string, unknown>;

export const ABBRUCHGRUENDE: readonly Abbruchgrund[] = ["dns", "dnf", "dsq"];

/** Alle Query-Keys beginnen mit `erfassung`, damit Ereignisse sie mit einem Aufruf neu laden. */
export const erfassungSchluessel = {
  alle: ["erfassung"] as const,
  maske: (turnierId: string, startId: string, art: Erfassungsart | null) =>
    ["erfassung", turnierId, "maske", startId, art ?? ""] as const,
  verlauf: (turnierId: string, startId: string) =>
    ["erfassung", turnierId, "verlauf", startId] as const,
  pruefliste: (turnierId: string) => ["erfassung", turnierId, "pruefliste"] as const,
};

/**
 * Ereignisse des Backend-Moduls `ergebnisse` (service.py, router.py) und Statuswechsel der Starts.
 * Die Maske des offenen Starts lädt dabei neu; das Terminal vergleicht die Sequenznummer und
 * übernimmt fremde Änderungen nur, wenn nichts Eigenes ungespeichert ist.
 */
const EREIGNISSE = [
  "result.raw_set",
  "result.finalized",
  "result.corrected",
  "result.reopened",
  "result.aborted",
  "result.recomputed",
  "start.status_changed",
  "start.cancelled",
  "competition.definition_changed",
  EREIGNIS_VERBUNDEN,
] as const;

export const erfassungEreignisse: EreignisZuordnung = Object.fromEntries(
  EREIGNISSE.map((name) => [
    name,
    name.startsWith("result.")
      ? [erfassungSchluessel.alle, ["starts"]]
      : [erfassungSchluessel.alle],
  ]),
);

const kodiert = encodeURIComponent;
const startPfad = (t: string, s: string) => `/tournaments/${kodiert(t)}/starts/${kodiert(s)}`;

// --- Lesen ---------------------------------------------------------------------------------------

/** Eingabemaske, Kopf und aktueller Stand eines Starts. `art`: Darstellung (sonst die des Wettbewerbs). */
export const maskeAbfrage = (turnierId: string, startId: string, art: Erfassungsart | null) =>
  queryOptions({
    queryKey: erfassungSchluessel.maske(turnierId, startId, art),
    queryFn: ({ signal }) =>
      apiGet<Maske>(`${startPfad(turnierId, startId)}/form`, {
        parameter: { capture_mode: art },
        signal,
      }),
  });

/** Frischer Stand des Servers, am Cache vorbei (Prüfansicht vor dem Abschluss). */
export function ladeMaske(turnierId: string, startId: string, art: Erfassungsart | null) {
  return apiGet<Maske>(`${startPfad(turnierId, startId)}/form`, {
    parameter: { capture_mode: art },
  });
}

export const verlaufAbfrage = (turnierId: string, startId: string) =>
  queryOptions({
    queryKey: erfassungSchluessel.verlauf(turnierId, startId),
    queryFn: ({ signal }) =>
      apiGet<VerlaufEintrag[]>(`${startPfad(turnierId, startId)}/events`, { signal }),
  });

export const prueflisteAbfrage = (turnierId: string) =>
  queryOptions({
    queryKey: erfassungSchluessel.pruefliste(turnierId),
    queryFn: ({ signal }) =>
      apiGet<PruefEintrag[]>(`/tournaments/${kodiert(turnierId)}/results/needs-review`, {
        signal,
      }),
  });

// --- Schreiben -----------------------------------------------------------------------------------

/**
 * HTTP 409 mit dem aktuellen Stand: Ein anderes Gerät hat denselben Start inzwischen geändert.
 * Nichts wurde geschrieben.
 */
export class SeqKonflikt extends Error {
  readonly aktuell: ErgebnisStand;
  readonly detail: string;

  constructor(detail: string, aktuell: ErgebnisStand) {
    super(detail);
    this.name = "SeqKonflikt";
    this.detail = detail;
    this.aktuell = aktuell;
  }
}

/**
 * Zufälliger Schlüssel (UUID v4). `crypto.randomUUID` gibt es nur in sicheren Kontexten; im
 * Vereinsnetz läuft die App aber über einfaches HTTP. `getRandomValues` geht überall.
 */
export function neuerSchluessel(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** Sendet einen Vorgang mit `Idempotency-Key`. Fehler: `SeqKonflikt` oder `ApiFehler`. */
export async function sendeVorgang(
  methode: "POST" | "PUT",
  pfad: string,
  inhalt: unknown,
  schluessel: string,
): Promise<ErgebnisStand> {
  let antwort: Response;
  try {
    antwort = await fetch(apiUrl(pfad), {
      method: methode,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Schiesshub-Request": "1",
        "Idempotency-Key": schluessel,
      },
      body: JSON.stringify(inhalt),
    });
  } catch {
    throw new ApiFehler("netzwerk", pfad);
  }

  let koerper: unknown;
  try {
    koerper = await antwort.json();
  } catch {
    koerper = undefined;
  }

  if (antwort.ok) {
    if (!koerper || typeof koerper !== "object")
      throw new ApiFehler("format", pfad, antwort.status);
    return koerper as ErgebnisStand;
  }

  const objekt = koerper && typeof koerper === "object" ? (koerper as Record<string, unknown>) : {};
  const detail = typeof objekt.detail === "string" ? objekt.detail : undefined;
  if (antwort.status === 409 && objekt.current && typeof objekt.current === "object") {
    throw new SeqKonflikt(detail ?? "", objekt.current as ErgebnisStand);
  }
  throw new ApiFehler(
    artAusStatus(antwort.status),
    pfad,
    antwort.status,
    detail,
    undefined,
    feldFehlerAus(koerper),
  );
}

export const ergebnisApi = {
  rohwerte: (t: string, s: string, raw: Rohwerte, baseSeq: number, schluessel: string) =>
    sendeVorgang("PUT", `${startPfad(t, s)}/raw`, { raw, base_seq: baseSeq }, schluessel),
  abschliessen: (t: string, s: string, baseSeq: number, schluessel: string) =>
    sendeVorgang("POST", `${startPfad(t, s)}/finalize`, { base_seq: baseSeq }, schluessel),
  korrigieren: (
    t: string,
    s: string,
    raw: Rohwerte,
    grund: string,
    baseSeq: number,
    schluessel: string,
  ) =>
    sendeVorgang(
      "POST",
      `${startPfad(t, s)}/correct`,
      { raw, reason: grund, base_seq: baseSeq },
      schluessel,
    ),
  wiederOeffnen: (t: string, s: string, grund: string, baseSeq: number, schluessel: string) =>
    sendeVorgang(
      "POST",
      `${startPfad(t, s)}/reopen`,
      { reason: grund, base_seq: baseSeq },
      schluessel,
    ),
  abbrechen: (t: string, s: string, grund: Abbruchgrund, text: string | null, schluessel: string) =>
    sendeVorgang(
      "POST",
      `${startPfad(t, s)}/result/abort`,
      { abort_reason: grund, reason: text },
      schluessel,
    ),
};

/** Ob ein Fehler ein vorübergehendes Verbindungsproblem ist (dann erneut senden). */
export function istVoruebergehend(fehler: unknown): boolean {
  return fehler instanceof ApiFehler && (fehler.art === "netzwerk" || fehler.art === "server");
}
