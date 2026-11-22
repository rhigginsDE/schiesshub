import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { ApiFehler, apiSenden } from "../../api/client";
import { useDarf } from "../../app/berechtigungen";
import { useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import {
  anmeldungenAbfrage,
  type Bahn,
  type Start,
  type StationStart,
  startsSchluessel,
} from "../anmeldung/api";

/**
 * Neu im Server, noch nicht in den erzeugten API-Typen (`schema.gen.ts`): Fortschritt der
 * Erfassung je Bahn (`LaneOut.progress`). Optional, damit ältere Antworten weiter passen.
 */
export interface BahnFortschritt {
  section_id: string | null;
  series_done: number;
  series_total: number;
  complete: boolean;
}
export type BahnMitFortschritt = Bahn & { progress?: BahnFortschritt | null };

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
 * Name für die Standaufsicht. Wer Starts aufrufen oder Ergebnisse erfassen darf, sieht – wie in der
 * Erfassung – den vollen Namen aus den Anmeldungen (braucht Lesezugriff auf die Anmeldungen; die
 * Startliste des Servers liefert nie den vollen Namen). Sonst der Name nach Anzeige-Einstellung;
 * `null` (Person will nicht genannt werden) bleibt leer.
 */
export function useAnzeigename(turnierId: string): (start: StationStart) => StandName {
  const { t } = useTranslation("stand");
  const intern = useDarf(["start.call", "result.capture"]);
  const anmeldungen = useQuery({
    ...anmeldungenAbfrage(turnierId),
    enabled: intern,
    retry: false,
  });
  const namen = useMemo(
    () => new Map((anmeldungen.data ?? []).map((a) => [a.id, a.person.name] as const)),
    [anmeldungen.data],
  );
  return useCallback(
    (start: StationStart) => {
      const name = (intern ? namen.get(start.entry_id) : undefined) ?? start.display_name;
      return name ? { text: name, ohne: false } : { text: t("bahn.ohne_name"), ohne: true };
    },
    [intern, namen, t],
  );
}
