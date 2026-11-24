import { type QueryClient, type QueryKey, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { schluessel } from "./abfragen";
import { API_BASIS } from "./client";

/**
 * Behandlung eines Ereignisses mit seiner Nutzlast (`data`, als JSON gelesen; `undefined`, wenn
 * keine da ist), z. B. ein gelöschtes Turnier aus dem Cache nehmen. Läuft vor dem Neuladen.
 */
export type EreignisBehandlung = (daten: unknown, queryClient: QueryClient) => void;

/**
 * Ereignisname vom Server → Query-Keys, deren Daten danach neu geladen werden. Ein Eintrag darf
 * auch eine `EreignisBehandlung` sein; alle Behandlungen laufen vor dem Neuladen.
 */
export type EreignisZuordnung = Record<string, readonly (QueryKey | EreignisBehandlung)[]>;

function leseNutzlast(ereignis: Event): unknown {
  const roh = (ereignis as MessageEvent).data;
  if (typeof roh !== "string" || roh === "") return undefined;
  try {
    return JSON.parse(roh);
  } catch {
    return undefined;
  }
}

/** Erst die Behandlungen (mit Nutzlast), dann die Query-Keys neu laden. */
export function ereignisAnwenden(
  eintraege: EreignisZuordnung[string],
  daten: unknown,
  queryClient: QueryClient,
): void {
  for (const eintrag of eintraege) {
    if (typeof eintrag === "function") eintrag(daten, queryClient);
  }
  for (const eintrag of eintraege) {
    if (typeof eintrag !== "function") void queryClient.invalidateQueries({ queryKey: eintrag });
  }
}

const NEU_VERBINDEN_MS = 5000;

/** Erstes Ereignis nach jedem Verbindungsaufbau, auch nach einem Neustart des Servers. */
export const EREIGNIS_VERBUNDEN = "verbunden";

/**
 * Hält die Verbindung zu `GET /events` (Server-Sent Events). Bei einem bekannten Ereignis werden
 * die zugeordneten Query-Keys invalidiert; beim Auf- und Abbau der Verbindung wird der
 * Serverstatus sofort neu geprüft. Heartbeats des Servers brauchen keine Behandlung.
 *
 * Nach jedem Verbindungsaufbau sendet der Server einmal `verbunden` (siehe `EREIGNIS_VERBUNDEN`).
 * Module tragen dort ein, was nach einem Server-Neustart neu geladen werden muss.
 */
export function useServerEreignisse(zuordnung: EreignisZuordnung): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (typeof EventSource === "undefined") return;

    let quelle: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let beendet = false;

    const statusPruefen = () => {
      void queryClient.invalidateQueries({ queryKey: schluessel.health });
    };

    const verbinden = () => {
      if (beendet) return;
      quelle = new EventSource(`${API_BASIS}/events`);
      quelle.addEventListener("open", statusPruefen);
      quelle.addEventListener("error", () => {
        statusPruefen();
        // Bei einer Fehlerantwort (z. B. 502 vom Proxy) gibt der Browser auf; dann selbst neu verbinden.
        if (quelle?.readyState === EventSource.CLOSED) {
          clearTimeout(timer);
          timer = setTimeout(verbinden, NEU_VERBINDEN_MS);
        }
      });
      for (const [name, eintraege] of Object.entries(zuordnung)) {
        quelle.addEventListener(name, (ereignis) =>
          ereignisAnwenden(eintraege, leseNutzlast(ereignis), queryClient),
        );
      }
    };

    verbinden();
    return () => {
      beendet = true;
      clearTimeout(timer);
      quelle?.close();
    };
  }, [queryClient, zuordnung]);
}
