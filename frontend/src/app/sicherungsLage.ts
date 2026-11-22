import { useLocalStorage } from "@mantine/hooks";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  schluessel,
  sicherungsEinstellungenAbfrage,
  sicherungsStatusAbfrage,
} from "../api/abfragen";
import { apiSenden } from "../api/client";
import type {
  SicherungsEinstellungen,
  SicherungsStatus,
  SicherungsWarnung,
} from "../api/typenSystem";
import { useDarf } from "./berechtigungen";

/** So lange bleibt die Warnung nach „ausblenden“ auf diesem Gerät weg. */
export const STUMM_DAUER_MS = 15 * 60 * 1000;
const STUMM_SCHLUESSEL = "schiesshub.sicherung.stumm";

/** Ausgeblendet bis `bis` (ms seit 1970), nur für die Warnung mit diesem `code`. */
export interface Stummschaltung {
  bis: number;
  code: string;
}

export interface WarnungEingaben {
  status: SicherungsStatus | undefined;
  einstellungen: SicherungsEinstellungen | undefined;
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
  status,
  einstellungen,
  istAnzeige,
  stumm,
  jetzt,
}: WarnungEingaben): SicherungsWarnung | null {
  const warnung = status?.warning;
  if (!warnung || !einstellungen) return null;
  if (istAnzeige ? !einstellungen.warn_on_display : !einstellungen.warn_all_stations) return null;
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

/** Zustand der Sicherung für Kopfzeile und Banner; ohne `backup.read` bleibt alles leer. */
export function useSicherungsLage(istAnzeige: boolean) {
  const queryClient = useQueryClient();
  const darfLesen = useDarf("backup.read");
  const darfVerwalten = useDarf("backup.manage");
  const status = useQuery({ ...sicherungsStatusAbfrage({ still: true }), enabled: darfLesen });
  const einstellungen = useQuery({
    ...sicherungsEinstellungenAbfrage({ still: true }),
    enabled: darfLesen,
  });
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

  const pruefen = useMutation({
    mutationFn: async () => {
      if (!darfVerwalten) return (await status.refetch()).data;
      return apiSenden<SicherungsStatus>("POST", "/backup/usb/recheck");
    },
    onSuccess: (neu) => {
      if (neu) queryClient.setQueryData(schluessel.sicherung.status, neu);
    },
  });

  const warnung = sichtbareWarnung({
    status: status.data,
    einstellungen: einstellungen.data,
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
