import { QueryClient } from "@tanstack/react-query";
import { ApiFehler } from "../api/client";

/**
 * Ein Wiederholungsversuch, wenn der Server kurz nicht erreichbar war oder gestolpert ist.
 * 4xx-Antworten werden nicht wiederholt: Die Anfrage wird beim zweiten Mal nicht richtiger.
 */
export function erstelleQueryClient({ wiederholen = true } = {}): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (anzahl, fehler) =>
          wiederholen &&
          anzahl < 1 &&
          fehler instanceof ApiFehler &&
          (fehler.art === "netzwerk" || fehler.art === "server"),
        refetchOnWindowFocus: false,
      },
    },
  });
}
