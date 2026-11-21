import { queryOptions } from "@tanstack/react-query";
import { apiGet } from "./client";
import type { Disziplin, DisziplinDetail, Gruppe, Health, Klasse, Verband } from "./typen";
import type {
  AuditSeite,
  AuthPerson,
  AuthStatus,
  Berechtigung,
  Geraet,
  Person,
  Rolle,
  SicherungsEinstellungen,
  SicherungsLauf,
  SicherungsStatus,
} from "./typenSystem";

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
  auth: {
    alle: ["auth"] as const,
    status: ["auth", "status"] as const,
    anmeldePersonen: ["auth", "anmelde-personen"] as const,
    berechtigungen: ["auth", "berechtigungen"] as const,
    geraete: ["auth", "geraete"] as const,
    rollen: ["auth", "rollen"] as const,
    personen: ["auth", "personen"] as const,
    protokollAlle: ["auth", "protokoll"] as const,
    protokoll: (limit: number, offset: number) => ["auth", "protokoll", limit, offset] as const,
  },
  sicherung: {
    alle: ["sicherung"] as const,
    status: ["sicherung", "status"] as const,
    einstellungen: ["sicherung", "einstellungen"] as const,
    laeufe: ["sicherung", "laeufe"] as const,
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

// --- Anmeldung und Rechte ------------------------------------------------------

/** Wer fragt an: Ersteinrichtung, Gerät, Person, Rolle, Berechtigungen. */
export const authStatusAbfrage = () =>
  queryOptions({
    queryKey: schluessel.auth.status,
    queryFn: ({ signal }) => apiGet<AuthStatus>("/auth/status", { signal, still: true }),
    retry: false,
    staleTime: 30 * 1000,
  });

/** Personen zur Auswahl bei der Anmeldung (401, wenn das Gerät nicht gekoppelt ist). */
export const anmeldePersonenAbfrage = () =>
  queryOptions({
    queryKey: schluessel.auth.anmeldePersonen,
    queryFn: ({ signal }) => apiGet<AuthPerson[]>("/auth/users", { signal, still: true }),
    retry: false,
  });

/** Alle Berechtigungen, die die Module des Servers kennen. */
export const berechtigungenAbfrage = ({ still = false } = {}) =>
  queryOptions({
    queryKey: schluessel.auth.berechtigungen,
    queryFn: ({ signal }) => apiGet<Berechtigung[]>("/auth/permissions", { signal, still }),
    staleTime: 5 * 60 * 1000,
  });

export const geraeteAbfrage = () =>
  queryOptions({
    queryKey: schluessel.auth.geraete,
    queryFn: ({ signal }) => apiGet<Geraet[]>("/devices", { signal }),
  });

export const rollenAbfrage = () =>
  queryOptions({
    queryKey: schluessel.auth.rollen,
    queryFn: ({ signal }) => apiGet<Rolle[]>("/roles", { signal }),
  });

export const personenAbfrage = () =>
  queryOptions({
    queryKey: schluessel.auth.personen,
    queryFn: ({ signal }) => apiGet<Person[]>("/users", { signal }),
  });

export const protokollAbfrage = (limit: number, offset: number) =>
  queryOptions({
    queryKey: schluessel.auth.protokoll(limit, offset),
    queryFn: ({ signal }) => apiGet<AuditSeite>("/audit", { parameter: { limit, offset }, signal }),
  });

// --- Sicherung -----------------------------------------------------------------

/** Zustand von Sicherung und Stick. `still`: für die Kopfzeile, die 403 selbst übergeht. */
export const sicherungsStatusAbfrage = ({ still = false } = {}) =>
  queryOptions({
    queryKey: schluessel.sicherung.status,
    queryFn: ({ signal }) => apiGet<SicherungsStatus>("/backup/status", { signal, still }),
    refetchInterval: 60 * 1000,
  });

export const sicherungsEinstellungenAbfrage = ({ still = false } = {}) =>
  queryOptions({
    queryKey: schluessel.sicherung.einstellungen,
    queryFn: ({ signal }) => apiGet<SicherungsEinstellungen>("/backup/settings", { signal, still }),
  });

export const sicherungsLaeufeAbfrage = (limit = 50) =>
  queryOptions({
    queryKey: [...schluessel.sicherung.laeufe, limit] as const,
    queryFn: ({ signal }) =>
      apiGet<SicherungsLauf[]>("/backup/runs", { parameter: { limit }, signal }),
  });
