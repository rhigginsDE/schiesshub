/**
 * Ein Turnier wurde gelöscht (`tournament.deleted`, auch beim Entfernen des Übungsturniers): aus
 * Liste und Cache nehmen, die Wahl dieses Geräts vergessen und nichts mehr über dieses Turnier
 * abfragen. Seiten mit der Turnier-ID in der Adresse zeigen stattdessen „gelöscht“.
 */
import type { Query, QueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import type { EreignisBehandlung } from "../../api/ereignisse";
import { vergissTurnier } from "../../components/useAktivesTurnier";
import { turnierSchluessel } from "./abfragen";
import type { Turnier } from "./typen";

const geloeschte = new Set<string>();
const zuhoerer = new Set<() => void>();

function merken(id: string): void {
  if (geloeschte.has(id)) return;
  geloeschte.add(id);
  for (const zuhoeren of zuhoerer) zuhoeren();
}

/** Für Tests: vergessen, welche Turniere gelöscht wurden. */
export function geloeschteVergessen(): void {
  geloeschte.clear();
  for (const zuhoeren of zuhoerer) zuhoeren();
}

export function istGeloescht(id: string): boolean {
  return geloeschte.has(id);
}

/** `true`, sobald das Turnier `id` in dieser Sitzung gelöscht wurde (hier oder auf einem anderen Gerät). */
export function useTurnierGeloescht(id: string): boolean {
  return useSyncExternalStore(
    (zuhoeren) => {
      zuhoerer.add(zuhoeren);
      return () => zuhoerer.delete(zuhoeren);
    },
    () => geloeschte.has(id),
  );
}

/** Kommt die ID irgendwo im Query-Key vor (auch in Objekten, z. B. `{ turnier: id }`)? */
export function schluesselEnthaelt(schluessel: unknown, id: string): boolean {
  if (schluessel === id) return true;
  if (Array.isArray(schluessel)) return schluessel.some((teil) => schluesselEnthaelt(teil, id));
  if (schluessel && typeof schluessel === "object") {
    return Object.values(schluessel).some((teil) => schluesselEnthaelt(teil, id));
  }
  return false;
}

/**
 * Räumt nach dem Löschen auf: zuerst merken (Seiten des Turniers hängen sich ab), Wahl des Geräts
 * vergessen, das Turnier aus der Liste nehmen, dann alle Abfragen mit seiner ID abbrechen und
 * entfernen. Danach lädt das Ereignis die übrigen Turnierdaten neu – ohne das gelöschte.
 */
export function turnierEntfernen(id: string, queryClient: QueryClient): void {
  merken(id);
  vergissTurnier(id);
  queryClient.setQueryData<Turnier[]>(turnierSchluessel.liste(), (alt) =>
    alt?.filter((turnier) => turnier.id !== id),
  );
  const betrifft = (query: Query) => schluesselEnthaelt(query.queryKey, id);
  void queryClient.cancelQueries({ predicate: betrifft });
  queryClient.removeQueries({ predicate: betrifft });
}

/** Behandlung für `tournament.deleted` mit Nutzlast `{ tournament_id }`. */
export const turnierGeloescht: EreignisBehandlung = (daten, queryClient) => {
  const id = (daten as { tournament_id?: unknown } | null | undefined)?.tournament_id;
  if (typeof id === "string" && id) turnierEntfernen(id, queryClient);
};
