import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render } from "@testing-library/react";
import { Users } from "lucide-react";
import type { ReactNode } from "react";
import { vi } from "vitest";
import { type ModulManifest, ModulProvider } from "../../app/modul";
import { theme } from "../../theme";
import type { Person, Verein } from "./api";

/** Antwort einer Testroute: Inhalt, Status, Kopfzeilen. */
export interface TestAntwort {
  status?: number;
  inhalt?: unknown;
  kopf?: Record<string, string>;
}

export interface Aufruf {
  methode: string;
  pfad: string;
  inhalt: unknown;
}

/**
 * Ersetzt `fetch`. Schlüssel: „METHODE /pfad?query“ (ohne `/api/v1`). Funktionen bekommen den
 * Aufruf und dürfen je Anfrage anders antworten. Unbekannte Pfade antworten mit 404.
 */
export function serverAttrappe(
  routen: Record<string, TestAntwort | ((aufruf: Aufruf) => TestAntwort)>,
) {
  const aufrufe: Aufruf[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (eingabe: RequestInfo | URL, init?: RequestInit) => {
      const pfad = String(eingabe).replace(/^\/api\/v1/, "");
      const methode = init?.method ?? "GET";
      let inhalt: unknown = init?.body;
      if (typeof inhalt === "string") {
        try {
          inhalt = JSON.parse(inhalt);
        } catch {
          // Rohinhalt behalten
        }
      }
      const aufruf = { methode, pfad, inhalt };
      aufrufe.push(aufruf);
      const eintrag = routen[`${methode} ${pfad}`];
      if (!eintrag) {
        return new Response(JSON.stringify({ detail: `Kein Testwert für ${methode} ${pfad}` }), {
          status: 404,
        });
      }
      const antwort = typeof eintrag === "function" ? eintrag(aufruf) : eintrag;
      const status = antwort.status ?? 200;
      return new Response(status === 204 ? null : JSON.stringify(antwort.inhalt ?? null), {
        status,
        headers: { "Content-Type": "application/json", ...antwort.kopf },
      });
    }),
  );
  return aufrufe;
}

const MODULE: ModulManifest[] = [
  {
    id: "anmeldung",
    namensraum: "anmeldung",
    navigation: { art: "station", pfad: "/anmeldung", icon: Users, reihenfolge: 10 },
    berechtigung: null,
    routen: [],
  },
  {
    id: "teilnehmer",
    namensraum: "teilnehmer",
    navigation: {
      art: "bereich",
      station: "anmeldung",
      pfad: "/anmeldung/teilnehmer",
      icon: Users,
      reihenfolge: 10,
    },
    berechtigung: null,
    routen: [],
  },
];

/** Rendert eine Ansicht mit Theme, Daten-Cache und einem kleinen Router (ohne App-Shell). */
export function renderAnsicht(inhalt: () => ReactNode) {
  const wurzel = createRootRoute({ component: () => <>{inhalt()}</> });
  const router = createRouter({
    routeTree: wurzel,
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const ergebnis = render(
    <MantineProvider theme={theme} env="test">
      <QueryClientProvider client={queryClient}>
        <ModulProvider value={MODULE}>
          <RouterProvider router={router} />
        </ModulProvider>
      </QueryClientProvider>
    </MantineProvider>,
  );
  return { ...ergebnis, queryClient };
}

export const VEREIN_TELL: Verein = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "SV Tell Musterstadt",
  short: "SV Tell",
  person_count: 2,
  created_at: "2026-11-21T10:00:00Z",
  updated_at: "2026-11-21T10:00:00Z",
};

export const VEREIN_HUBERTUS: Verein = {
  id: "22222222-2222-4222-8222-222222222222",
  name: "SSV Hubertus Altdorf",
  short: null,
  person_count: 1,
  created_at: "2026-11-21T10:00:00Z",
  updated_at: "2026-11-21T10:00:00Z",
};

export function person(id: string, name: string, extra: Partial<Person> = {}): Person {
  return {
    id,
    name,
    member_no: null,
    club_id: VEREIN_TELL.id,
    club_name: VEREIN_TELL.name,
    display_mode: "full",
    show_club: true,
    display_name: name,
    display_club: VEREIN_TELL.name,
    created_at: "2026-11-21T10:00:00Z",
    updated_at: "2026-11-21T10:00:00Z",
    ...extra,
  };
}

export const BRANDT = person("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "Markus Brandt", {
  member_no: "10 2231",
});
export const MAIER = person("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "Jürgen Maier");
export const KOEHLER = person("cccccccc-cccc-4ccc-8ccc-cccccccccccc", "Sabine Köhler", {
  club_id: VEREIN_HUBERTUS.id,
  club_name: VEREIN_HUBERTUS.name,
  display_mode: "short",
  display_name: "S. Köhler",
  display_club: VEREIN_HUBERTUS.name,
});
