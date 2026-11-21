import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiFehler, apiGet } from "../../../api/client";
import { turnierSchluessel } from "../abfragen";
import { turnierSenden } from "../senden";
import type { Ausschreibung, AusschreibungDokument } from "./typen";

const pfad = (id: string) => `/tournaments/${encodeURIComponent(id)}/announcement`;

export const ausschreibungSchluessel = {
  entwurf: (id: string) => ["turnier", id, "ausschreibung"] as const,
  dokument: (id: string) => ["turnier", id, "ausschreibung", "dokument"] as const,
};

/** 404 heißt hier: Das Backend kennt die Ausschreibung (noch) nicht. Ergebnis dann `null`. */
async function oderNull<T>(laden: () => Promise<T>): Promise<T | null> {
  try {
    return await laden();
  } catch (fehler) {
    if (
      fehler instanceof ApiFehler &&
      fehler.status === 404 &&
      // „Not Found“ von FastAPI = Route fehlt; ein fehlendes Turnier meldet sich deutsch.
      (fehler.detail === undefined || fehler.detail === "Not Found")
    ) {
      return null;
    }
    throw fehler;
  }
}

export const ausschreibungAbfrage = (id: string) =>
  queryOptions({
    queryKey: ausschreibungSchluessel.entwurf(id),
    // Ältere Turniere haben womöglich noch keine Ausschreibung (Inhalt `null`): leer beginnen.
    queryFn: ({ signal }) =>
      oderNull(async () => {
        const daten = await apiGet<Ausschreibung | null>(pfad(id), { signal });
        return daten ?? { title: null, facts: {}, blocks: [] };
      }),
    retry: false,
  });

export const ausschreibungDokumentAbfrage = (id: string) =>
  queryOptions({
    queryKey: ausschreibungSchluessel.dokument(id),
    queryFn: ({ signal }) =>
      oderNull(() => apiGet<AusschreibungDokument>(`${pfad(id)}/document`, { signal })),
    retry: false,
  });

export function useAusschreibungSpeichern(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (daten: Ausschreibung) => turnierSenden<Ausschreibung>("PUT", pfad(id), daten),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: turnierSchluessel.alle }),
  });
}
