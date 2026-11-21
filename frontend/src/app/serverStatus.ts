import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { healthAbfrage } from "../api/abfragen";
import type { Health } from "../api/typen";

/**
 * - `verbunden`: Server antwortet, alles in Ordnung
 * - `eingeschraenkt`: Server läuft, der Katalog wurde aber nicht vollständig eingelesen
 * - `gestoert`: Server antwortet, erreicht aber seine Datenbank nicht
 * - `getrennt`: keine Antwort vom Server
 */
export type Verbindung = "pruefe" | "verbunden" | "eingeschraenkt" | "gestoert" | "getrennt";

function nutzbar(verbindung: Verbindung): boolean {
  return verbindung === "verbunden" || verbindung === "eingeschraenkt";
}

export interface ServerStatus {
  verbindung: Verbindung;
  health: Health | undefined;
}

/**
 * Verbindung zum Server aus `GET /health` (regelmäßig abgefragt, zusätzlich angestoßen durch
 * die SSE-Verbindung). Kommt der Server zurück, werden fehlgeschlagene Abfragen neu geladen.
 */
export function useServerStatus(): ServerStatus {
  const queryClient = useQueryClient();
  const abfrage = useQuery(healthAbfrage());

  const verbindung: Verbindung =
    abfrage.status === "pending"
      ? "pruefe"
      : abfrage.status === "error"
        ? "getrennt"
        : abfrage.data.status === "ok"
          ? "verbunden"
          : abfrage.data.status === "eingeschraenkt"
            ? "eingeschraenkt"
            : "gestoert";

  const vorher = useRef<Verbindung>(verbindung);
  useEffect(() => {
    if (!nutzbar(vorher.current) && vorher.current !== "pruefe" && nutzbar(verbindung)) {
      void queryClient.refetchQueries({ predicate: (query) => query.state.status === "error" });
    }
    vorher.current = verbindung;
  }, [verbindung, queryClient]);

  return { verbindung, health: abfrage.status === "success" ? abfrage.data : undefined };
}
