import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { ApiFehler } from "../../api/client";
import { useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import type { StationStart } from "../anmeldung/api";

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

/** Name, wie der Server ihn für Stationen liefert; `null` (Person will nicht genannt werden) bleibt leer. */
export function useAnzeigename(): (start: StationStart) => string {
  const { t } = useTranslation("stand");
  return (start) => start.display_name ?? t("bahn.ohne_name");
}
