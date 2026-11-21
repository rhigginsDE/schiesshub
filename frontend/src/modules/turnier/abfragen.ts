import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiFehler, apiGet } from "../../api/client";
import { EREIGNIS_VERBUNDEN, type EreignisZuordnung } from "../../api/ereignisse";
import { turnierSenden } from "./senden";
import type {
  DefinitionGrund,
  KatalogVergleich,
  KlasseAenderung,
  KlasseAnlage,
  Revision,
  Stand,
  StandAenderung,
  StandAnlage,
  Turnier,
  TurnierAenderung,
  TurnierAnlage,
  TurnierKlasse,
  TurnierStatus,
  TurnierUebersicht,
  Wettbewerb,
  WettbewerbAenderung,
  WettbewerbAnlage,
} from "./typen";

/** Query-Keys des Moduls; alles beginnt mit `turnier`, damit Ereignisse pauschal neu laden können. */
export const turnierSchluessel = {
  alle: ["turnier"] as const,
  liste: () => ["turnier", "liste"] as const,
  uebersicht: (id: string) => ["turnier", id, "uebersicht"] as const,
  revisionen: (id: string, wettbewerb: string) =>
    ["turnier", id, "wettbewerb", wettbewerb, "revisionen"] as const,
  katalogDiff: (id: string, wettbewerb: string) =>
    ["turnier", id, "wettbewerb", wettbewerb, "katalog-diff"] as const,
};

/** Alle Ereignisse, die das Backend-Modul `turnier` sendet (service.py). */
const EREIGNISSE = [
  "tournament.created",
  "tournament.updated",
  "tournament.status_changed",
  "tournament.deleted",
  "range.created",
  "range.updated",
  "range.deleted",
  "range.reordered",
  "class.created",
  "class.updated",
  "class.deleted",
  "class.reordered",
  "class.imported",
  "competition.created",
  "competition.updated",
  "competition.deleted",
  "competition.reordered",
  "competition.definition_changed",
  "tournament.announcement_changed",
] as const;

export const turnierEreignisse: EreignisZuordnung = Object.fromEntries([
  ...EREIGNISSE.map((name) => [name, [turnierSchluessel.alle]]),
  [EREIGNIS_VERBUNDEN, [turnierSchluessel.alle]],
]);

const pfad = {
  turniere: "/tournaments",
  turnier: (id: string) => `/tournaments/${encodeURIComponent(id)}`,
  staende: (id: string) => `/tournaments/${encodeURIComponent(id)}/ranges`,
  klassen: (id: string) => `/tournaments/${encodeURIComponent(id)}/classes`,
  wettbewerbe: (id: string) => `/tournaments/${encodeURIComponent(id)}/competitions`,
};

export const turnierListeAbfrage = () =>
  queryOptions({
    queryKey: turnierSchluessel.liste(),
    queryFn: ({ signal }) => apiGet<Turnier[]>(pfad.turniere, { signal }),
  });

export const uebersichtAbfrage = (id: string) =>
  queryOptions({
    queryKey: turnierSchluessel.uebersicht(id),
    queryFn: ({ signal }) => apiGet<TurnierUebersicht>(`${pfad.turnier(id)}/overview`, { signal }),
  });

/**
 * Lädt einen Zusatz-Endpunkt, den es im Backend womöglich noch nicht gibt. 404 ergibt `null`;
 * die Oberfläche blendet den Bereich dann aus.
 */
async function optional<T>(laden: () => Promise<T>): Promise<T | null> {
  try {
    return await laden();
  } catch (fehler) {
    if (fehler instanceof ApiFehler && (fehler.status === 404 || fehler.status === 405)) {
      return null;
    }
    throw fehler;
  }
}

export const revisionenAbfrage = (id: string, wettbewerb: string) =>
  queryOptions({
    queryKey: turnierSchluessel.revisionen(id, wettbewerb),
    queryFn: ({ signal }) =>
      optional(() =>
        apiGet<Revision[]>(`${pfad.wettbewerbe(id)}/${encodeURIComponent(wettbewerb)}/revisions`, {
          signal,
        }),
      ),
    retry: false,
  });

export const katalogDiffAbfrage = (id: string, wettbewerb: string) =>
  queryOptions({
    queryKey: turnierSchluessel.katalogDiff(id, wettbewerb),
    queryFn: ({ signal }) =>
      optional(() =>
        apiGet<KatalogVergleich>(
          `${pfad.wettbewerbe(id)}/${encodeURIComponent(wettbewerb)}/catalog-diff`,
          { signal },
        ),
      ),
    retry: false,
  });

// --- Schreiben ---------------------------------------------------------------------------------

/** Mutation, die danach alle Turnierdaten neu lädt (das Ereignis des Servers kommt zusätzlich). */
function useSchreiben<E, A = unknown>(senden: (eingabe: E) => Promise<A>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: senden,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: turnierSchluessel.alle }),
  });
}

export function useTurnierAnlegen() {
  return useSchreiben((daten: TurnierAnlage) =>
    turnierSenden<Turnier>("POST", pfad.turniere, daten),
  );
}

export function useTurnierAendern(id: string) {
  return useSchreiben((daten: TurnierAenderung) =>
    turnierSenden<Turnier>("PATCH", pfad.turnier(id), daten),
  );
}

export function useStatusWechseln() {
  return useSchreiben(({ id, status }: { id: string; status: TurnierStatus }) =>
    turnierSenden<Turnier>("POST", `${pfad.turnier(id)}/status`, { status }),
  );
}

export function useTurnierLoeschen() {
  return useSchreiben((id: string) => turnierSenden("DELETE", pfad.turnier(id)));
}

export function useStandAnlegen(id: string) {
  return useSchreiben((daten: StandAnlage) =>
    turnierSenden<Stand>("POST", pfad.staende(id), daten),
  );
}

export function useStandAendern(id: string) {
  return useSchreiben(({ standId, daten }: { standId: string; daten: StandAenderung }) =>
    turnierSenden<Stand>("PATCH", `${pfad.staende(id)}/${encodeURIComponent(standId)}`, daten),
  );
}

export function useStandLoeschen(id: string) {
  return useSchreiben((standId: string) =>
    turnierSenden("DELETE", `${pfad.staende(id)}/${encodeURIComponent(standId)}`),
  );
}

export function useStaendeSortieren(id: string) {
  return useSchreiben((ids: string[]) =>
    turnierSenden<Stand[]>("PUT", `${pfad.staende(id)}/order`, { ids }),
  );
}

export function useKlasseAnlegen(id: string) {
  return useSchreiben((daten: KlasseAnlage) =>
    turnierSenden<TurnierKlasse>("POST", pfad.klassen(id), daten),
  );
}

export function useKlasseAendern(id: string) {
  return useSchreiben(({ klasseId, daten }: { klasseId: string; daten: KlasseAenderung }) =>
    turnierSenden<TurnierKlasse>(
      "PATCH",
      `${pfad.klassen(id)}/${encodeURIComponent(klasseId)}`,
      daten,
    ),
  );
}

export function useKlasseLoeschen(id: string) {
  return useSchreiben((klasseId: string) =>
    turnierSenden("DELETE", `${pfad.klassen(id)}/${encodeURIComponent(klasseId)}`),
  );
}

export function useKlassenSortieren(id: string) {
  return useSchreiben((ids: string[]) =>
    turnierSenden<TurnierKlasse[]>("PUT", `${pfad.klassen(id)}/order`, { ids }),
  );
}

export function useKlassenUebernehmen(id: string) {
  return useSchreiben((verband: string) =>
    turnierSenden<TurnierKlasse[]>("POST", `${pfad.klassen(id)}/import`, { federation: verband }),
  );
}

export function useWettbewerbAnlegen(id: string) {
  return useSchreiben((daten: WettbewerbAnlage) =>
    turnierSenden<Wettbewerb>("POST", pfad.wettbewerbe(id), daten),
  );
}

export function useWettbewerbAendern(id: string) {
  return useSchreiben(
    ({
      wettbewerbId,
      daten,
    }: {
      wettbewerbId: string;
      daten: WettbewerbAenderung & DefinitionGrund;
    }) =>
      turnierSenden<Wettbewerb>(
        "PATCH",
        `${pfad.wettbewerbe(id)}/${encodeURIComponent(wettbewerbId)}`,
        daten,
      ),
  );
}

export function useDefinitionZuruecksetzen(id: string) {
  return useSchreiben(
    ({
      wettbewerbId,
      variante,
      grund,
    }: {
      wettbewerbId: string;
      variante?: string;
      grund?: string;
    }) => {
      const inhalt: Record<string, string> = {};
      if (variante) inhalt.variant_id = variante;
      if (grund) inhalt.reason = grund;
      return turnierSenden<Wettbewerb>(
        "POST",
        `${pfad.wettbewerbe(id)}/${encodeURIComponent(wettbewerbId)}/reset-definition`,
        inhalt,
      );
    },
  );
}

export function useWettbewerbLoeschen(id: string) {
  return useSchreiben((wettbewerbId: string) =>
    turnierSenden("DELETE", `${pfad.wettbewerbe(id)}/${encodeURIComponent(wettbewerbId)}`),
  );
}

export function useWettbewerbeSortieren(id: string) {
  return useSchreiben((ids: string[]) =>
    turnierSenden<Wettbewerb[]>("PUT", `${pfad.wettbewerbe(id)}/order`, { ids }),
  );
}
