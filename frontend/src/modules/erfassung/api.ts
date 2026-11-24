/**
 * Daten des Backend-Moduls `ergebnisse` für das Erfassungsterminal: Eingabemaske, Verlauf,
 * Prüfliste und die schreibenden Vorgänge (Rohwerte, Abschluss, Korrektur, Wiederöffnen, Abbruch).
 *
 * Schreibende Vorgänge tragen einen `Idempotency-Key`: Wiederholt das Terminal eine Sendung nach
 * einem Verbindungsabbruch mit demselben Schlüssel, schreibt der Server kein zweites Ereignis.
 */
import { queryOptions } from "@tanstack/react-query";
import { ApiFehler, apiGet, apiSenden } from "../../api/client";
import { EREIGNIS_VERBUNDEN, type EreignisZuordnung } from "../../api/ereignisse";
import type { components } from "../../api/schema.gen";
import { type StationStart, startsSchluessel } from "../anmeldung/api";

type Schemas = components["schemas"];

export type Maske = Schemas["FormOut"];
export type MaskenKopf = Schemas["FormHeader"];
export type Formular = Schemas["FormDescription"];
export type AbschnittForm = Schemas["SectionForm"];
export type SerieForm = Schemas["SeriesForm"];
export type FeldBeschreibung = Schemas["FieldSpec"];
/** Hinweis der Maske mit Art (`kind`), damit nichts am Wortlaut erkannt werden muss. */
export type Hinweis = Schemas["HintItem"];
export type HinweisArt = Hinweis["kind"];
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
/**
 * Vorabauskunft des Servers (`abort_preview`): Würde ein Aufgeben jetzt (dnf) platziert? Gerechnet
 * wie die Rangliste; `null` bei abgeschlossenen und abgebrochenen Starts.
 */
export type AufgebenAuskunft = Schemas["AbortPreview"];
export type AuskunftGrund = AufgebenAuskunft["reason_code"];
/** Feldwert, den der Server aus den Einzelwerten rechnet (Seriensumme), nicht gespeichert. */
export type AbgeleiteterWert = Schemas["DerivedValue"];
/** Notiz zur ganzen Maske mit Art (`form.note_items`). */
export type Notiz = Schemas["NoteItem"];
export type NotizArt = Notiz["kind"];
export type Rangliste = Schemas["RankingOut"];
export type RanglistenZeile = Schemas["RankingRow"];

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
  rangliste: (turnierId: string, wettbewerbId: string, klasseId: string) =>
    ["erfassung", turnierId, "rangliste", wettbewerbId, klasseId] as const,
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
  "result.abort_undone",
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

/**
 * Startliste des Turniers für das Terminal. Mit `voll` (Recht `start.call`, `result.capture` oder
 * `entry.read`) liefert der Server zusätzlich den vollen Namen (`names=full`); ohne das Recht wird
 * ohne den Parameter gefragt, sonst antwortet der Server mit 403.
 */
export const erfassungStartlisteAbfrage = (turnierId: string, voll: boolean) =>
  queryOptions({
    queryKey: [...startsSchluessel.startliste(turnierId, {}), voll ? "voll" : ""] as const,
    queryFn: ({ signal }) =>
      apiGet<StationStart[]>(`/tournaments/${kodiert(turnierId)}/startlist`, {
        parameter: { names: voll ? "full" : undefined },
        signal,
      }),
  });

/**
 * Platz eines Starts in der Rangliste seines Wettbewerbs (nur seine Klasse). Für den aufgegebenen
 * Start: Ob er platziert ist, sagt allein die Rangliste des Servers; ohne Platz nennt sie den Grund
 * (`abort_note`). `null`, wenn der Start nicht in der Liste steht.
 */
export const ranglistenZeileAbfrage = (
  turnierId: string,
  wettbewerbId: string,
  klasseId: string,
  startId: string,
) =>
  queryOptions({
    queryKey: erfassungSchluessel.rangliste(turnierId, wettbewerbId, klasseId),
    queryFn: ({ signal }) =>
      apiGet<Rangliste>(
        `/tournaments/${kodiert(turnierId)}/competitions/${kodiert(wettbewerbId)}/ranking`,
        { parameter: { class_id: klasseId }, signal },
      ),
    select: (liste): RanglistenZeile | null =>
      liste.groups.flatMap((gruppe) => gruppe.rows).find((zeile) => zeile.start_id === startId) ??
      null,
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

/**
 * Sendet einen Vorgang mit `Idempotency-Key` über `apiSenden`. Fehler: `SeqKonflikt` (409 mit dem
 * aktuellen Stand) oder `ApiFehler` (mit Feldfehlern). 401/403 meldet der Vorgang nicht an die
 * App-Shell; das Terminal zeigt den Fehler selbst (wie bisher).
 */
export async function sendeVorgang(
  methode: "POST" | "PUT",
  pfad: string,
  inhalt: unknown,
  schluessel: string,
): Promise<ErgebnisStand> {
  let antwort: unknown;
  try {
    antwort = await apiSenden<unknown>(methode, pfad, inhalt, {
      kopf: { "Idempotency-Key": schluessel },
      still: true,
    });
  } catch (fehler) {
    if (fehler instanceof ApiFehler && fehler.status === 409) {
      const objekt =
        fehler.inhalt && typeof fehler.inhalt === "object"
          ? (fehler.inhalt as Record<string, unknown>)
          : {};
      if (objekt.current && typeof objekt.current === "object") {
        const detail = typeof objekt.detail === "string" ? objekt.detail : "";
        throw new SeqKonflikt(detail, objekt.current as ErgebnisStand);
      }
    }
    throw fehler;
  }
  // Ein Vorgang liefert immer den neuen Stand; alles andere (auch 204) ist unlesbar.
  if (!antwort || typeof antwort !== "object") throw new ApiFehler("format", pfad);
  return antwort as ErgebnisStand;
}

export const ergebnisApi = {
  rohwerte: (t: string, s: string, raw: Rohwerte, baseSeq: number, schluessel: string) =>
    sendeVorgang("PUT", `${startPfad(t, s)}/raw`, { raw, base_seq: baseSeq }, schluessel),
  /**
   * Abschließen. `geprueft`: Sequenz und Ergebnis, die die Prüfansicht gezeigt hat; weicht der
   * Server davon ab, antwortet er mit 409 und dem aktuellen Stand (`SeqKonflikt`).
   */
  abschliessen: (
    t: string,
    s: string,
    baseSeq: number,
    schluessel: string,
    geprueft?: Pick<Schemas["FinalizeRequest"], "expected_seq" | "expected_score">,
  ) =>
    sendeVorgang(
      "POST",
      `${startPfad(t, s)}/finalize`,
      { base_seq: baseSeq, ...geprueft } satisfies Schemas["FinalizeRequest"],
      schluessel,
    ),
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
  /**
   * Abbruch zurücknehmen (Recht `result.correct`): neues Ereignis `abort_undone`, der Start ist
   * danach wieder „erfasst“ (mit Rohwerten) bzw. „angemeldet“, ohne Schützenstand.
   */
  abbruchZuruecknehmen: (
    t: string,
    s: string,
    grund: string,
    baseSeq: number,
    schluessel: string,
  ) =>
    sendeVorgang(
      "POST",
      `${startPfad(t, s)}/result/undo-abort`,
      { reason: grund, base_seq: baseSeq } satisfies Schemas["UndoAbortRequest"],
      schluessel,
    ),
};

/**
 * Probe-Rechnung des Servers (`POST …/starts/{id}/preview`): wertet Rohwerte gegen die aktuelle
 * Definition, speichert aber nichts.
 */
export type Vorschau = Schemas["PreviewOut"];

/** Vorschau für genau diese Rohwerte; `schluessel` ist eine stabile Form der Rohwerte. */
export const vorschauAbfrage = (
  turnierId: string,
  startId: string,
  raw: Rohwerte,
  schluessel: string,
) =>
  queryOptions({
    queryKey: ["erfassung", turnierId, "vorschau", startId, schluessel] as const,
    queryFn: ({ signal }) =>
      apiSenden<Vorschau>("POST", `${startPfad(turnierId, startId)}/preview`, { raw }, { signal }),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });

/** Ob ein Fehler ein vorübergehendes Verbindungsproblem ist (dann erneut senden). */
export function istVoruebergehend(fehler: unknown): boolean {
  return fehler instanceof ApiFehler && (fehler.art === "netzwerk" || fehler.art === "server");
}
