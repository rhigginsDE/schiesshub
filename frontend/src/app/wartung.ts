import { queryOptions, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { ApiFehler, apiGet, beiWartung } from "../api/client";
import type { components } from "../api/schema.gen";

/** Wartungszustand während einer Wiederherstellung (`GET /backup/maintenance`). */
export type Wartung = components["schemas"]["MaintenanceOut"];

export const WARTUNG_SCHLUESSEL = ["wartung"] as const;

export const KEINE_WARTUNG: Wartung = {
  active: false,
  exclusive: false,
  message_de: null,
  since: null,
};

/** So oft fragt jedes Gerät nach, solange die Wartung läuft (das Ende kommt sonst per Ereignis). */
export const WARTUNG_ABFRAGE_MS = 3000;

/**
 * Antwort von `/backup/maintenance` lesen. Während des Tauschs der Datenbank beantwortet der
 * Server auch diese Abfrage mit 503 und `code: maintenance`: Das heißt „Wartung, exklusiv“.
 */
export function wartungAus(antwort: unknown): Wartung {
  if (!antwort || typeof antwort !== "object") return KEINE_WARTUNG;
  const inhalt = antwort as Partial<Wartung> & { code?: unknown; detail?: unknown };
  if (inhalt.code === "maintenance") {
    return {
      active: true,
      exclusive: true,
      message_de: typeof inhalt.detail === "string" ? inhalt.detail : null,
      since: null,
    };
  }
  if (typeof inhalt.active !== "boolean") return KEINE_WARTUNG;
  return {
    active: inhalt.active,
    exclusive: inhalt.exclusive === true,
    message_de: inhalt.message_de ?? null,
    since: inhalt.since ?? null,
  };
}

export const wartungAbfrage = () =>
  queryOptions({
    queryKey: WARTUNG_SCHLUESSEL,
    queryFn: async ({ signal }) => {
      try {
        const antwort = await apiGet<unknown>("/backup/maintenance", {
          signal,
          still: true,
          auchBeiStatus: [503],
        });
        return wartungAus(antwort);
      } catch (fehler) {
        // Keine Antwort (Server startet gerade neu): bisherigen Stand behalten (Abfrage schlägt fehl).
        if (fehler instanceof ApiFehler && fehler.art === "netzwerk") throw fehler;
        // Älterer Server ohne den Endpunkt, nicht gekoppelt, keine Berechtigung: keine Wartung.
        if (fehler instanceof ApiFehler) return KEINE_WARTUNG;
        throw fehler;
      }
    },
    refetchInterval: (abfrage) => (abfrage.state.data?.active ? WARTUNG_ABFRAGE_MS : false),
    retry: false,
    staleTime: 0,
  });

/**
 * Wartungszustand für die App-Shell. Erfährt davon über das Ereignis `backup.maintenance`
 * (siehe AppShell), über jede Antwort „Wartung“ einer beliebigen Anfrage und, solange die Wartung
 * läuft, über regelmäßiges Nachfragen. Endet sie, lädt die App alle Daten neu: Nach einer
 * Wiederherstellung ist der Stand ein anderer.
 */
export function useWartung(): Wartung {
  const queryClient = useQueryClient();
  const abfrage = useQuery(wartungAbfrage());
  const wartung = abfrage.data ?? KEINE_WARTUNG;

  useEffect(
    () =>
      beiWartung(() => {
        // Nicht abbrechen, was schon läuft: Bei vielen gleichzeitigen 503 genügt eine Abfrage.
        void queryClient.refetchQueries({ queryKey: WARTUNG_SCHLUESSEL }, { cancelRefetch: false });
      }),
    [queryClient],
  );

  const vorher = useRef(wartung.active);
  useEffect(() => {
    if (vorher.current && !wartung.active) {
      void queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] !== WARTUNG_SCHLUESSEL[0],
      });
    }
    vorher.current = wartung.active;
  }, [wartung.active, queryClient]);

  return wartung;
}
