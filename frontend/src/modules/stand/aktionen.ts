import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { ApiFehler, apiGet, apiSenden } from "../../api/client";
import { useDarf } from "../../app/berechtigungen";
import { useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import {
  type Start,
  type StartlistenFilter,
  type StationStart,
  startsSchluessel,
  type Warteschlange,
} from "../anmeldung/api";

/**
 * Wer Starts aufrufen, Ergebnisse erfassen oder Anmeldungen lesen darf, bekommt vom Server mit
 * `names=full` auch den vollen Namen (`full_name`, `full_club`). Ohne diese Rechte fragt die
 * Standansicht ohne den Parameter (sonst antwortet der Server mit 403).
 */
export const VOLLE_NAMEN = ["start.call", "result.capture", "entry.read"] as const;

export function useVolleNamen(): boolean {
  return useDarf(VOLLE_NAMEN);
}

const kodiert = encodeURIComponent;
const namenParameter = (voll: boolean) => (voll ? "full" : undefined);

/** Reihenfolge und Bahnen eines Stands; mit `voll` samt vollem Namen. */
export const standWarteschlangeAbfrage = (turnierId: string, standId: string, voll: boolean) =>
  queryOptions({
    queryKey: [...startsSchluessel.warteschlange(turnierId, standId), voll ? "voll" : ""] as const,
    queryFn: ({ signal }) =>
      apiGet<Warteschlange>(`/tournaments/${kodiert(turnierId)}/ranges/${kodiert(standId)}/queue`, {
        parameter: { names: namenParameter(voll) },
        signal,
      }),
  });

/** Startliste (gefiltert); mit `voll` samt vollem Namen. */
export const standStartlisteAbfrage = (
  turnierId: string,
  filter: StartlistenFilter,
  voll: boolean,
) =>
  queryOptions({
    queryKey: [...startsSchluessel.startliste(turnierId, filter), voll ? "voll" : ""] as const,
    queryFn: ({ signal }) =>
      apiGet<StationStart[]>(`/tournaments/${kodiert(turnierId)}/startlist`, {
        parameter: {
          competition_id: filter.wettbewerb,
          range_id: filter.stand,
          names: namenParameter(voll),
        },
        signal,
      }),
  });

/**
 * „Bahn freigeben“ (`POST …/starts/{id}/release-lane`): nimmt einen Start mit angefangenem Ergebnis
 * von der Bahn, ohne den Status zu ändern; das Ergebnis bleibt offen.
 */
export function useBahnFreigeben(turnierId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (startId: string) =>
      apiSenden<Start>(
        "POST",
        `/tournaments/${encodeURIComponent(turnierId)}/starts/${encodeURIComponent(startId)}/release-lane`,
      ),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: startsSchluessel.turnier(turnierId) });
    },
  });
}

/**
 * Meldet den Fehler einer Aktion am Bildschirmrand. Konflikte (409, z. B. „Bahn 2 ist schon
 * belegt“) als Hinweis, alles andere als Fehler, der stehen bleibt.
 */
export function useFehlerMelden(): (fehler: unknown) => void {
  const { t } = useTranslation("stand");
  const text = useFehlerText();
  return useCallback(
    (fehler: unknown) => {
      const konflikt = fehler instanceof ApiFehler && fehler.art === "konflikt";
      zeigeMeldung({
        ton: konflikt ? "warn" : "krit",
        titel: t("aktion.fehler"),
        text: text(fehler),
        schluessel: "stand-aktion",
      });
    },
    [t, text],
  );
}

/** Name eines Starts in der Standansicht: was angezeigt wird und ob die Person ungenannt bleibt. */
export interface StandName {
  text: string;
  /** Kein Name (Person will auf Listen nicht genannt werden; nur intern lesbar) */
  ohne: boolean;
}

/**
 * Name für die Standaufsicht: der volle Name, wenn der Server ihn mitgeliefert hat (`names=full`,
 * siehe `useVolleNamen`), sonst der Name nach Anzeige-Einstellung; `null` (Person will nicht
 * genannt werden) bleibt leer.
 */
export function useAnzeigename(): (start: StationStart) => StandName {
  const { t } = useTranslation("stand");
  return useCallback(
    (start: StationStart) => {
      const name = start.full_name ?? start.display_name;
      return name ? { text: name, ohne: false } : { text: t("bahn.ohne_name"), ohne: true };
    },
    [t],
  );
}
