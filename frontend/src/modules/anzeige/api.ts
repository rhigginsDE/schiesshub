import { queryOptions } from "@tanstack/react-query";
import { apiGet, apiSenden } from "../../api/client";
import { EREIGNIS_VERBUNDEN, type EreignisZuordnung } from "../../api/ereignisse";
import type { Anzeige, AnzeigeKonfig, Feed, FeedVorschauAnfrage } from "./typen";

/** Query-Keys des Moduls; alles beginnt mit `anzeige`. */
export const anzeigeSchluessel = {
  alle: ["anzeige"] as const,
  liste: () => ["anzeige", "liste"] as const,
  vorschau: (id: string) => ["anzeige", "vorschau", id] as const,
};

/** Verwaltung lädt neu, wenn sich eine Anzeige ändert (auch von einem anderen Gerät aus). */
export const anzeigeEreignisse: EreignisZuordnung = {
  "display.changed": [anzeigeSchluessel.alle],
  [EREIGNIS_VERBUNDEN]: [anzeigeSchluessel.alle],
};

const pfad = {
  liste: "/displays",
  anzeige: (id: string) => `/displays/${encodeURIComponent(id)}`,
};

export const anzeigenAbfrage = () =>
  queryOptions({
    queryKey: anzeigeSchluessel.liste(),
    queryFn: ({ signal }) => apiGet<Anzeige[]>(pfad.liste, { signal }),
  });

export function anzeigeAnlegen(name: string, sort?: number) {
  return apiSenden<Anzeige>("POST", pfad.liste, { name, sort });
}

/** Szenen einer neuen Anzeige für ein Turnier: Live-Wertung, Startliste, Siegerliste. */
export function turnierSzenen(): NonNullable<AnzeigeKonfig["scenes"]> {
  const basis = { seconds: 20, title: null, competition_ids: [] };
  return [
    {
      ...basis,
      id: "live",
      kind: "live_ranking",
      class_ids: [],
      rows: 10,
      show_running: true,
      show_aborted: false,
    },
    {
      ...basis,
      id: "startliste",
      kind: "startlist",
      seconds: 15,
      range_ids: [],
      rows: 12,
      include_finished: false,
    },
    {
      ...basis,
      id: "sieger",
      kind: "winners",
      class_ids: [],
      top: 3,
      include_provisional: true,
      show_aborted: false,
    },
  ];
}

/**
 * Neue Anzeige, fest auf ein Turnier eingestellt, mit Live-Wertung, Startliste und Siegerliste.
 * Ohne Turnier wählt der Server das laufende Turnier selbst.
 */
export function anzeigeFuerTurnierAnlegen(name: string, turnierId: string | null, sort?: number) {
  return apiSenden<Anzeige>("POST", pfad.liste, {
    name,
    sort,
    tournament_id: turnierId,
    config: {
      scenes: turnierSzenen(),
      name_mode: "as_person",
      show_club: "as_person",
      show_provisional_note: true,
      theme: "dark",
    } satisfies AnzeigeKonfig,
  });
}

export function standardAnlegen() {
  return apiSenden<Anzeige>("POST", `${pfad.liste}/defaults`);
}

/** Name, Turnier, Reihenfolge und (mit `config`) den Inhalt in einer Anfrage ändern. */
export function anzeigeAendern(
  id: string,
  aenderung: {
    name?: string;
    tournament_id?: string | null;
    sort?: number;
    config?: AnzeigeKonfig;
  },
) {
  return apiSenden<Anzeige>("PATCH", pfad.anzeige(id), aenderung);
}

/**
 * Feed für einen nicht gespeicherten Entwurf (Vorschau in der Verwaltung). Prüft die Szenen wie
 * beim Speichern (422), speichert aber nichts.
 */
export function vorschauFeed(id: string, anfrage: FeedVorschauAnfrage, signal?: AbortSignal) {
  return apiSenden<Feed>("POST", `${pfad.anzeige(id)}/preview-feed`, anfrage, { signal });
}

export function anzeigeLoeschen(id: string) {
  return apiSenden("DELETE", pfad.anzeige(id));
}

export function geraetZuweisen(id: string, geraetId: string) {
  return apiSenden<Anzeige>("PUT", `${pfad.anzeige(id)}/device`, { device_id: geraetId });
}

export function geraetLoesen(id: string) {
  return apiSenden<Anzeige>("DELETE", `${pfad.anzeige(id)}/device`);
}

/** Adresse des Bildschirms einer Anzeige (zum Öffnen und Abtippen). */
export function schirmPfad(id?: string): string {
  return id ? `/anzeige/schirm/${encodeURIComponent(id)}` : "/anzeige/schirm";
}
