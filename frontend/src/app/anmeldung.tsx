import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { authStatusAbfrage, schluessel } from "../api/abfragen";
import { apiSenden, beiApiFehler, serverMeldung } from "../api/client";
import type { AuthStatus } from "../api/typenSystem";
import { zeigeMeldung } from "../components/Meldungen";
import {
  type AbweisGrund,
  type AnmeldeLage,
  abweisGrund,
  bestimmeLage,
  rechteAus,
} from "./anmeldeLage";
import { RechteProvider, setzeAktuelleRechte } from "./berechtigungen";

export interface Anmeldung {
  status: AuthStatus | undefined;
  lage: AnmeldeLage;
  /** Warum der Server das Gerät zuletzt abgewiesen hat (gesperrt, abgelaufen …); sonst `null`. */
  grund: AbweisGrund | null;
  /** Meldet die Person ab; das Gerät bleibt gekoppelt. */
  abmelden: () => Promise<void>;
  /** Nach Einrichtung, Kopplung oder Anmeldung: neuen Status übernehmen, alles neu laden. */
  uebernehmen: (status: AuthStatus) => void;
}

const LEERE_LAGE: AnmeldeLage = { pruefe: false, sperren: false, ausstehend: null, pflicht: null };

const AnmeldungKontext = createContext<Anmeldung>({
  status: undefined,
  lage: LEERE_LAGE,
  grund: null,
  abmelden: async () => {},
  uebernehmen: () => {},
});

export function useAnmeldung(): Anmeldung {
  return useContext(AnmeldungKontext);
}

/**
 * Hält den Anmelde-Zustand (`GET /auth/status`) und die Rechte für die ganze App.
 * 401 von einem Endpunkt außerhalb von `/auth` führt zurück zur Anmeldung; 403 zeigt eine Meldung.
 */
export function AnmeldungProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation("shell");
  const queryClient = useQueryClient();
  const abfrage = useQuery(authStatusAbfrage());
  const [abgewiesen, setAbgewiesen] = useState(false);
  // Code aus der letzten 401 (`device_revoked`, `session_expired` …), falls der Server einen liefert.
  const [abweisCode, setAbweisCode] = useState<string | null>(null);

  useEffect(
    () =>
      beiApiFehler((fehler) => {
        if (fehler.pfad.startsWith("/auth/")) return;
        if (fehler.art === "nicht_angemeldet") {
          setAbgewiesen(true);
          setAbweisCode(fehler.code ?? null);
          void queryClient.invalidateQueries({ queryKey: schluessel.auth.status });
        } else if (fehler.art === "verboten") {
          zeigeMeldung({
            ton: "krit",
            schluessel: "verboten",
            titel: t("berechtigung.fehlt_titel"),
            text: serverMeldung(fehler) ?? t("berechtigung.fehlt_text"),
          });
        }
      }),
    [queryClient, t],
  );

  // Eine 401 gilt, bis Einrichtung, Kopplung oder Anmeldung einen neuen Status liefern.
  const status = abfrage.data;

  const lage = useMemo(
    () => bestimmeLage({ status, statusFehler: abfrage.isError, abgewiesen }),
    [status, abfrage.isError, abgewiesen],
  );

  const grund = abweisGrund(status, abgewiesen ? abweisCode : null);
  const rechte = useMemo(() => rechteAus(status, lage), [status, lage]);
  // Für `darf()` ohne Hook; im Rendern gesetzt, damit die Kinder schon die neuen Rechte sehen.
  setzeAktuelleRechte(rechte);

  const uebernehmen = useCallback(
    (neu: AuthStatus) => {
      setAbgewiesen(false);
      setAbweisCode(null);
      // Das Server-Ereignis (z. B. `auth.setup`) kommt oft vor der Antwort an und stößt eine
      // Abfrage noch ohne die neuen Cookies an. Die darf den neuen Status nicht überschreiben.
      void queryClient.cancelQueries({ queryKey: schluessel.auth.status }).then(() => {
        queryClient.setQueryData(schluessel.auth.status, neu);
        void queryClient.invalidateQueries();
      });
      queryClient.setQueryData(schluessel.auth.status, neu);
    },
    [queryClient],
  );

  const abmelden = useCallback(async () => {
    await apiSenden("POST", "/auth/logout");
    // Alles neu laden: Was zu sehen ist, hängt an der Person.
    await queryClient.invalidateQueries();
  }, [queryClient]);

  const wert = useMemo<Anmeldung>(
    () => ({ status, lage, grund, abmelden, uebernehmen }),
    [status, lage, grund, abmelden, uebernehmen],
  );

  return (
    <AnmeldungKontext.Provider value={wert}>
      <RechteProvider value={rechte}>{children}</RechteProvider>
    </AnmeldungKontext.Provider>
  );
}
