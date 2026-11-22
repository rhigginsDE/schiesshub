import { Loader } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Navigate } from "@tanstack/react-router";
import { MonitorOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ApiFehler, apiGet } from "../api/client";
import type { AuthStatus } from "../api/typenSystem";
import { Fehlerzustand } from "../components/Zustand";
import { useAnmeldung } from "./anmeldung";
import { gewaehrt } from "./berechtigungen";
import s from "./Startseite.module.css";

/** Pfad des Vollbilds für das Gerät selbst (`modules/anzeige`, `GET /displays/mine/feed`). */
export const GERAETE_SCHIRM_PFAD = "/anzeige/schirm";

/** Solange keine Anzeige zugeordnet ist: so oft nachsehen, ob die Turnierleitung das erledigt hat. */
const NACHSEHEN_MS = 10_000;

/**
 * Ein reines Anzeige-Gerät: gekoppelt, niemand eingeloggt, und seine Standardrolle darf die
 * Anzeige sehen und sonst nur lesen (wie die Startrolle „Anzeige“). Es gehört an den Bildschirm,
 * nicht in Turnier, Erfassung oder Verwaltung. Am Namen der Rolle hängt nichts.
 */
export function istAnzeigeGeraet(status: AuthStatus | undefined): boolean {
  if (!status?.device || status.user || !status.role) return false;
  const rechte = status.permissions;
  return (
    gewaehrt(rechte, "display.read") &&
    rechte.every((recht) => recht !== "*" && recht.endsWith(".read"))
  );
}

export function useIstAnzeigeGeraet(): boolean {
  return istAnzeigeGeraet(useAnmeldung().status);
}

/**
 * Startseite eines Anzeige-Geräts: direkt auf den Bildschirm; ohne zugeordnete Anzeige eine ruhige
 * Seite, die sagt, was die Turnierleitung tun muss. Sie wechselt von selbst, sobald es so weit ist.
 */
export function AnzeigeGeraetStart() {
  const { t } = useTranslation("shell");
  const { status } = useAnmeldung();
  const eigene = useQuery({
    queryKey: ["anzeige", "geraet", "eigene"],
    queryFn: ({ signal }) => apiGet<unknown>("/displays/mine", { signal, still: true }),
    retry: false,
    refetchInterval: (abfrage) =>
      abfrage.state.error instanceof ApiFehler && abfrage.state.error.art === "nicht_gefunden"
        ? NACHSEHEN_MS
        : false,
  });

  if (eigene.isSuccess) return <Navigate to={GERAETE_SCHIRM_PFAD} replace />;
  if (eigene.isPending) {
    return (
      <div className={s.anzeigeLeer} aria-busy="true">
        <Loader color="gruen" />
      </div>
    );
  }
  const keine = eigene.error instanceof ApiFehler && eigene.error.art === "nicht_gefunden";
  if (!keine) {
    return (
      <div className="panel">
        <Fehlerzustand fehler={eigene.error} onErneut={() => void eigene.refetch()} />
      </div>
    );
  }
  return (
    <section className={s.anzeigeLeer} aria-labelledby="anzeige-leer-titel">
      <MonitorOff className={s.anzeigeLeerSymbol} size={56} strokeWidth={1.5} aria-hidden />
      <h1 className="h-display" id="anzeige-leer-titel">
        {t("anzeige_geraet.titel")}
      </h1>
      <p className={s.anzeigeLeerText}>{t("anzeige_geraet.text")}</p>
      <ol className={s.anzeigeLeerSchritte}>
        <li>{t("anzeige_geraet.schritt_1")}</li>
        <li>{t("anzeige_geraet.schritt_2", { name: status?.device?.name ?? "" })}</li>
        <li>{t("anzeige_geraet.schritt_3")}</li>
      </ol>
    </section>
  );
}
