import { useLocalStorage } from "@mantine/hooks";
import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { schluessel, sicherungsStatusAbfrage } from "../api/abfragen";
import { apiGet, apiSenden } from "../api/client";
import type { components } from "../api/schema.gen";
import type { SicherungsStatus, SicherungsWarnung } from "../api/typenSystem";
import { useDarf } from "./berechtigungen";

/** Was jedes gekoppelte Gerät über die Sicherung erfährt (`GET /backup/warning`). */
export type SicherungsWarnLage = components["schemas"]["BackupWarningOut"];

/** Unter `schluessel.sicherung.alle`, damit „Sicherung fertig/fehlgeschlagen“ es mit neu lädt. */
export const WARNUNG_SCHLUESSEL = [...schluessel.sicherung.alle, "warnung"] as const;

/**
 * Aktuelle Warnung für das Banner, ohne bestimmtes Recht lesbar. Neu geladen beim Ereignis
 * `backup.status` (siehe AppShell) und zur Sicherheit jede Minute. Still: Ein älterer Server ohne
 * den Endpunkt oder ein noch nicht gekoppeltes Gerät zeigen schlicht keine Warnung.
 */
export const sicherungsWarnungAbfrage = () =>
  queryOptions({
    queryKey: WARNUNG_SCHLUESSEL,
    queryFn: ({ signal }) => apiGet<SicherungsWarnLage>("/backup/warning", { signal, still: true }),
    refetchInterval: 60 * 1000,
    retry: false,
  });

/** So lange bleibt die Warnung nach „ausblenden“ auf diesem Gerät weg. */
export const STUMM_DAUER_MS = 15 * 60 * 1000;
const STUMM_SCHLUESSEL = "schiesshub.sicherung.stumm";

/** Ausgeblendet bis `bis` (ms seit 1970), nur für die Warnung mit diesem `code`. */
export interface Stummschaltung {
  bis: number;
  code: string;
}

export interface WarnungEingaben {
  /** Antwort von `GET /backup/warning` */
  lage: SicherungsWarnLage | undefined;
  /** Die Station ist die öffentliche Anzeige (eigene Einstellung „auf der Anzeige warnen“) */
  istAnzeige: boolean;
  stumm: Stummschaltung | null;
  jetzt: number;
}

/**
 * Welche Warnung das Banner unter der Kopfzeile zeigt, oder `null`.
 * Eine andere Warnung als die ausgeblendete erscheint sofort wieder.
 */
export function sichtbareWarnung({
  lage,
  istAnzeige,
  stumm,
  jetzt,
}: WarnungEingaben): SicherungsWarnung | null {
  const warnung = lage?.warning;
  if (!lage || !warnung) return null;
  if (istAnzeige ? !lage.warn_on_display : !lage.warn_all_stations) return null;
  if (stumm && stumm.code === warnung.code && stumm.bis > jetzt) return null;
  return warnung;
}

/**
 * Was das Banner zu einer Warnung anbietet:
 * - `pruefen`: Stick-Probleme, die sich am Server beheben lassen; danach ändert „Erneut prüfen“ etwas.
 * - `passwort`: Sicherungspasswort festlegen (System → Sicherung).
 * - `sicherung`: Einstellung oder Fehler, den man unter System → Sicherung behebt. Prüfen hilft hier nicht.
 */
export type BannerAktion = "pruefen" | "passwort" | "sicherung";

const AKTION_JE_CODE: Record<SicherungsWarnung["code"], BannerAktion> = {
  usb_missing: "pruefen",
  usb_not_writable: "pruefen",
  usb_full: "pruefen",
  usb_copy_failed: "pruefen",
  journal_sync_failed: "pruefen",
  passphrase_missing: "passwort",
  backup_disabled: "sicherung",
  snapshot_failed: "sicherung",
};

export function bannerAktion(code: string): BannerAktion {
  return AKTION_JE_CODE[code as SicherungsWarnung["code"]] ?? "sicherung";
}

/**
 * Zustand der Sicherung für Kopfzeile und Banner. Die Warnung (Banner) sieht jede Station
 * (`GET /backup/warning`, ohne Recht); Einzelheiten wie die letzte Sicherung (`status`) nur mit
 * `backup.read`.
 */
export function useSicherungsLage(istAnzeige: boolean) {
  const queryClient = useQueryClient();
  const darfLesen = useDarf("backup.read");
  const darfVerwalten = useDarf("backup.manage");
  // „Stick erneut prüfen“ erlaubt der Server mit `backup.run` (Turnierleitung) oder `backup.manage`.
  const darfPruefen = useDarf(["backup.run", "backup.manage"]);
  const status = useQuery({ ...sicherungsStatusAbfrage({ still: true }), enabled: darfLesen });
  const warnLage = useQuery(sicherungsWarnungAbfrage());
  const [stumm, setStumm] = useLocalStorage<Stummschaltung | null>({
    key: STUMM_SCHLUESSEL,
    defaultValue: null,
    getInitialValueInEffect: false,
  });
  const [jetzt, setJetzt] = useState(() => Date.now());

  // Nach Ablauf der Stummschaltung wieder anzeigen.
  useEffect(() => {
    if (!stumm) return;
    const rest = stumm.bis - Date.now();
    if (rest <= 0) return;
    const timer = setTimeout(() => setJetzt(Date.now()), rest + 50);
    return () => clearTimeout(timer);
  }, [stumm]);

  // Ohne Recht kann die Station nur nachfragen, ob der Server den Stick inzwischen sieht.
  const pruefen = useMutation({
    mutationFn: async (): Promise<SicherungsStatus | undefined> => {
      if (!darfPruefen) {
        await warnLage.refetch();
        return undefined;
      }
      return apiSenden<SicherungsStatus>("POST", "/backup/usb/recheck");
    },
    onSuccess: (neu) => {
      if (!neu) return;
      queryClient.setQueryData(schluessel.sicherung.status, neu);
      void queryClient.invalidateQueries({ queryKey: WARNUNG_SCHLUESSEL });
    },
  });

  const warnung = sichtbareWarnung({
    lage: warnLage.data,
    istAnzeige,
    stumm,
    jetzt: Math.max(jetzt, Date.now()),
  });

  return {
    status: darfLesen ? status.data : undefined,
    warnung,
    /** Darf die Sicherung einstellen (Passwort, Ein/Aus); sonst hilft nur, Bescheid zu geben. */
    darfVerwalten,
    pruefen,
    ausblenden: () => {
      if (warnung) setStumm({ bis: Date.now() + STUMM_DAUER_MS, code: warnung.code });
    },
  };
}
