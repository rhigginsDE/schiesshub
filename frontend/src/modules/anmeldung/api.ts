/**
 * Daten des Backend-Moduls `starts`: Anmeldungen, Starts, Ablauf am Stand, Startliste.
 * Gemeinsam für die Station Anmeldung und die Ablaufsteuerung am Stand (`modules/stand`).
 *
 * Alle Query-Keys beginnen mit `starts`, damit die Server-Ereignisse (`entry.*`, `start.*`,
 * `heat.*`) sie mit einem Aufruf neu laden können (siehe `startsEreignisse`).
 */
import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiSenden } from "../../api/client";
import { EREIGNIS_VERBUNDEN, type EreignisZuordnung } from "../../api/ereignisse";
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

export type Anmeldung = Schemas["EntryOut"];
export type AnmeldungNeu = Schemas["EntryCreate"];
export type AnmeldungAenderung = Schemas["EntryUpdate"];
export type Start = Schemas["StartOut"];
export type StartStatus = Start["status"];
export type Abbruchgrund = NonNullable<Start["abort_reason"]>;
export type Buchung = Schemas["StartBooking"];
export type StationStart = Schemas["StationStartOut"];
export type Durchgang = Schemas["HeatOut"];
export type DurchgangNeu = Schemas["HeatCreate"];
export type DurchgangAenderung = Schemas["HeatUpdate"];
export type DurchgangSerie = Schemas["HeatSeries"];
export type NaechsterPlatz = Schemas["NextSlotOut"];
export type Warteschlange = Schemas["QueueOut"];
export type Bahn = Schemas["LaneOut"];

export const ABBRUCHGRUENDE: readonly Abbruchgrund[] = ["dns", "dnf", "dsq"];

export const startsSchluessel = {
  alle: ["starts"] as const,
  turnier: (turnierId: string) => ["starts", turnierId] as const,
  anmeldungen: (turnierId: string) => ["starts", turnierId, "anmeldungen"] as const,
  naechsterPlatz: (turnierId: string, wettbewerbId: string, anmeldungId: string | null) =>
    ["starts", turnierId, "naechster-platz", wettbewerbId, anmeldungId ?? ""] as const,
  warteschlange: (turnierId: string, standId: string) =>
    ["starts", turnierId, "stand", standId, "warteschlange"] as const,
  durchgaenge: (turnierId: string, standId: string) =>
    ["starts", turnierId, "stand", standId, "durchgaenge"] as const,
  startliste: (turnierId: string, filter: StartlistenFilter) =>
    ["starts", turnierId, "startliste", filter.wettbewerb ?? "", filter.stand ?? ""] as const,
};

/**
 * Ereignisse des Backend-Moduls `starts` (service.py, queue.py, schedule.py, lifecycle.py).
 * Nutzlast sind nur IDs; neu geladen wird alles unter `starts`. Eingaben in offenen Formularen
 * liegen im Zustand der Komponenten und bleiben dabei stehen.
 * `person.updated` ändert Namen in den Anmeldungen, `competition.*` und `range.*` die Zuordnung.
 */
const EREIGNISSE = [
  "entry.created",
  "entry.updated",
  "entry.deleted",
  "start.booked",
  "start.cancelled",
  "start.status_changed",
  "start.moved",
  "start.scheduled",
  "heat.created",
  "heat.updated",
  "heat.deleted",
  "person.updated",
  "person.deleted",
  "competition.updated",
  "competition.deleted",
  "range.updated",
  "range.deleted",
  EREIGNIS_VERBUNDEN,
] as const;

export const startsEreignisse: EreignisZuordnung = Object.fromEntries(
  EREIGNISSE.map((name) => [name, [startsSchluessel.alle]]),
);

const kodiert = encodeURIComponent;
const pfad = {
  turnier: (t: string) => `/tournaments/${kodiert(t)}`,
  anmeldungen: (t: string) => `/tournaments/${kodiert(t)}/entries`,
  anmeldung: (t: string, a: string) => `/tournaments/${kodiert(t)}/entries/${kodiert(a)}`,
  start: (t: string, s: string) => `/tournaments/${kodiert(t)}/starts/${kodiert(s)}`,
  stand: (t: string, r: string) => `/tournaments/${kodiert(t)}/ranges/${kodiert(r)}`,
};

// --- Lesen ---------------------------------------------------------------------------------------

/** Alle Anmeldungen des Turniers, nach Startnummer. Gesucht wird in der Oberfläche. */
export const anmeldungenAbfrage = (turnierId: string) =>
  queryOptions({
    queryKey: startsSchluessel.anmeldungen(turnierId),
    queryFn: ({ signal }) => apiGet<Anmeldung[]>(pfad.anmeldungen(turnierId), { signal }),
  });

/** Vorschlag des Servers für den nächsten freien Platz (Zeitplan); `null` = kein freier Platz. */
export const naechsterPlatzAbfrage = (
  turnierId: string,
  wettbewerbId: string,
  anmeldungId: string | null,
) =>
  queryOptions({
    queryKey: startsSchluessel.naechsterPlatz(turnierId, wettbewerbId, anmeldungId),
    queryFn: ({ signal }) =>
      apiGet<NaechsterPlatz | null>(
        `${pfad.turnier(turnierId)}/competitions/${kodiert(wettbewerbId)}/next-slot`,
        { parameter: { entry_id: anmeldungId }, signal },
      ),
  });

export const warteschlangeAbfrage = (turnierId: string, standId: string) =>
  queryOptions({
    queryKey: startsSchluessel.warteschlange(turnierId, standId),
    queryFn: ({ signal }) =>
      apiGet<Warteschlange>(`${pfad.stand(turnierId, standId)}/queue`, { signal }),
  });

export const durchgaengeAbfrage = (turnierId: string, standId: string) =>
  queryOptions({
    queryKey: startsSchluessel.durchgaenge(turnierId, standId),
    queryFn: ({ signal }) =>
      apiGet<Durchgang[]>(`${pfad.stand(turnierId, standId)}/heats`, { signal }),
  });

export interface StartlistenFilter {
  wettbewerb?: string;
  stand?: string;
}

export const startlisteAbfrage = (turnierId: string, filter: StartlistenFilter = {}) =>
  queryOptions({
    queryKey: startsSchluessel.startliste(turnierId, filter),
    queryFn: ({ signal }) =>
      apiGet<StationStart[]>(`${pfad.turnier(turnierId)}/startlist`, {
        parameter: { competition_id: filter.wettbewerb, range_id: filter.stand },
        signal,
      }),
  });

// --- Schreiben -----------------------------------------------------------------------------------

/** Mutation, die danach alle Daten des Turniers unter `starts` neu lädt (das Ereignis kommt zusätzlich). */
function useStartsSchreiben<E, A>(turnierId: string, senden: (eingabe: E) => Promise<A>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: senden,
    // Nicht auf das Neuladen warten: Dialoge schließen sofort, die Daten folgen im Hintergrund.
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: startsSchluessel.turnier(turnierId) });
    },
  });
}

export function anmelden(turnierId: string, daten: AnmeldungNeu): Promise<Anmeldung> {
  return apiSenden<Anmeldung>("POST", pfad.anmeldungen(turnierId), daten);
}

export function anmeldungAendern(
  turnierId: string,
  anmeldungId: string,
  daten: AnmeldungAenderung,
): Promise<Anmeldung> {
  return apiSenden<Anmeldung>("PATCH", pfad.anmeldung(turnierId, anmeldungId), daten);
}

export function startsBuchen(
  turnierId: string,
  anmeldungId: string,
  daten: Buchung,
): Promise<Start[]> {
  return apiSenden<Start[]>("POST", `${pfad.anmeldung(turnierId, anmeldungId)}/starts`, daten);
}

export function naechsterPlatzLaden(
  turnierId: string,
  wettbewerbId: string,
  anmeldungId: string | null,
): Promise<NaechsterPlatz | null> {
  return apiGet<NaechsterPlatz | null>(
    `${pfad.turnier(turnierId)}/competitions/${kodiert(wettbewerbId)}/next-slot`,
    { parameter: { entry_id: anmeldungId } },
  );
}

export function useAnmeldungLoeschen(turnierId: string) {
  return useStartsSchreiben(turnierId, (anmeldungId: string) =>
    apiSenden("DELETE", pfad.anmeldung(turnierId, anmeldungId)),
  );
}

export function useStartStornieren(turnierId: string) {
  return useStartsSchreiben(turnierId, (startId: string) =>
    apiSenden("DELETE", pfad.start(turnierId, startId)),
  );
}

export function useStartAbbrechen(turnierId: string) {
  return useStartsSchreiben(
    turnierId,
    ({ startId, grund }: { startId: string; grund: Abbruchgrund }) =>
      apiSenden<Start>("POST", `${pfad.start(turnierId, startId)}/abort`, { abort_reason: grund }),
  );
}

export function useStartAufrufen(turnierId: string) {
  return useStartsSchreiben(turnierId, ({ startId, bahn }: { startId: string; bahn?: number }) =>
    apiSenden<Start>(
      "POST",
      `${pfad.start(turnierId, startId)}/call`,
      bahn === undefined ? undefined : { lane: bahn },
    ),
  );
}

export function useStartZurueckstellen(turnierId: string) {
  return useStartsSchreiben(
    turnierId,
    ({ startId, position }: { startId: string; position: "front" | "back" }) =>
      apiSenden<Start>("POST", `${pfad.start(turnierId, startId)}/return`, { position }),
  );
}

export type Verschiebung = { direction: "up" | "down" } | { position: number };

export function useStartVerschieben(turnierId: string) {
  return useStartsSchreiben(
    turnierId,
    ({ startId, wohin }: { startId: string; wohin: Verschiebung }) =>
      apiSenden<Warteschlange>("POST", `${pfad.start(turnierId, startId)}/move`, wohin),
  );
}

export function useNaechsteAufrufen(turnierId: string) {
  return useStartsSchreiben(turnierId, (standId: string) =>
    apiSenden<Start[]>("POST", `${pfad.stand(turnierId, standId)}/call-next`),
  );
}

export function useDurchgangAnlegen(turnierId: string, standId: string) {
  return useStartsSchreiben(turnierId, (daten: DurchgangNeu) =>
    apiSenden<Durchgang>("POST", `${pfad.stand(turnierId, standId)}/heats`, daten),
  );
}

export function useSerieAnlegen(turnierId: string, standId: string) {
  return useStartsSchreiben(turnierId, (daten: DurchgangSerie) =>
    apiSenden<Durchgang[]>("POST", `${pfad.stand(turnierId, standId)}/heats/series`, daten),
  );
}

export function useDurchgangAendern(turnierId: string, standId: string) {
  return useStartsSchreiben(
    turnierId,
    ({ durchgangId, daten }: { durchgangId: string; daten: DurchgangAenderung }) =>
      apiSenden<Durchgang>(
        "PATCH",
        `${pfad.stand(turnierId, standId)}/heats/${kodiert(durchgangId)}`,
        daten,
      ),
  );
}

export function useDurchgangLoeschen(turnierId: string, standId: string) {
  return useStartsSchreiben(turnierId, (durchgangId: string) =>
    apiSenden("DELETE", `${pfad.stand(turnierId, standId)}/heats/${kodiert(durchgangId)}`),
  );
}

export function useDurchgangAufrufen(turnierId: string, standId: string) {
  return useStartsSchreiben(turnierId, (durchgangId: string) =>
    apiSenden<Start[]>(
      "POST",
      `${pfad.stand(turnierId, standId)}/heats/${kodiert(durchgangId)}/call`,
    ),
  );
}

export function usePlatzZuweisen(turnierId: string) {
  return useStartsSchreiben(
    turnierId,
    ({ startId, durchgangId, bahn }: { startId: string; durchgangId: string; bahn?: number }) =>
      apiSenden<Start>("PUT", `${pfad.start(turnierId, startId)}/slot`, {
        heat_id: durchgangId,
        ...(bahn === undefined ? {} : { lane: bahn }),
      }),
  );
}

export function usePlatzEntfernen(turnierId: string) {
  return useStartsSchreiben(turnierId, (startId: string) =>
    apiSenden<Start>("DELETE", `${pfad.start(turnierId, startId)}/slot`),
  );
}
