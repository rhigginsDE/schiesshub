import { queryOptions } from "@tanstack/react-query";
import { apiGet } from "./client";
import type { Disziplin, DisziplinDetail, Gruppe, Health, Klasse, Verband } from "./typen";

/** Wie oft der Serverstatus geprüft wird. */
export const HEALTH_INTERVALL_MS = 5000;
const KATALOG_FRISCH_MS = 5 * 60 * 1000;

export interface DisziplinFilter {
  gruppe?: string;
  q?: string;
}

/** Query-Keys an einer Stelle, damit Ereignisse gezielt invalidieren können. */
export const schluessel = {
  health: ["health"] as const,
  katalog: {
    alle: ["katalog"] as const,
    verbaende: () => ["katalog", "verbaende"] as const,
    gruppen: (verband: string) => ["katalog", "gruppen", verband] as const,
    disziplinen: (verband: string, filter: DisziplinFilter) =>
      ["katalog", "disziplinen", verband, filter.gruppe ?? "", filter.q ?? ""] as const,
    disziplin: (verband: string, kennziffer: string) =>
      ["katalog", "disziplin", verband, kennziffer] as const,
    klassen: (verband: string) => ["katalog", "klassen", verband] as const,
  },
};

export const healthAbfrage = () =>
  queryOptions({
    queryKey: schluessel.health,
    // 503 heißt hier: Server läuft, aber die Datenbank fehlt. Der Inhalt sagt, was los ist.
    queryFn: ({ signal }) => apiGet<Health>("/health", { signal, auchBeiStatus: [503] }),
    refetchInterval: HEALTH_INTERVALL_MS,
    retry: false,
    staleTime: 0,
  });

export const verbaendeAbfrage = () =>
  queryOptions({
    queryKey: schluessel.katalog.verbaende(),
    queryFn: ({ signal }) => apiGet<Verband[]>("/katalog/verbaende", { signal }),
    staleTime: KATALOG_FRISCH_MS,
  });

export const gruppenAbfrage = (verband: string) =>
  queryOptions({
    queryKey: schluessel.katalog.gruppen(verband),
    queryFn: ({ signal }) =>
      apiGet<Gruppe[]>("/katalog/gruppen", { parameter: { verband }, signal }),
    staleTime: KATALOG_FRISCH_MS,
  });

export const disziplinenAbfrage = (verband: string, filter: DisziplinFilter = {}) =>
  queryOptions({
    queryKey: schluessel.katalog.disziplinen(verband, filter),
    queryFn: ({ signal }) =>
      apiGet<Disziplin[]>("/katalog/disziplinen", {
        parameter: { verband, gruppe: filter.gruppe, q: filter.q },
        signal,
      }),
    staleTime: KATALOG_FRISCH_MS,
  });

export const disziplinAbfrage = (verband: string, kennziffer: string) =>
  queryOptions({
    queryKey: schluessel.katalog.disziplin(verband, kennziffer),
    queryFn: ({ signal }) =>
      apiGet<DisziplinDetail>(
        `/katalog/disziplinen/${encodeURIComponent(verband)}/${encodeURIComponent(kennziffer)}`,
        { signal },
      ),
    staleTime: KATALOG_FRISCH_MS,
  });

export const klassenAbfrage = (verband: string) =>
  queryOptions({
    queryKey: schluessel.katalog.klassen(verband),
    queryFn: ({ signal }) =>
      apiGet<Klasse[]>("/katalog/klassen", { parameter: { verband }, signal }),
    staleTime: KATALOG_FRISCH_MS,
  });
