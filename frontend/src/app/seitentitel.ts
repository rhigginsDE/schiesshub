import { useLocalStorage } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { bestimmeTurnier, TURNIER_SPEICHER } from "../components/useAktivesTurnier";
import { turnierListeAbfrage } from "../modules/turnier/abfragen";
import type { AnmeldeSeite } from "./anmeldeLage";
import { darfMit, useRechte } from "./berechtigungen";
import { type ModulManifest, useAlleModule } from "./modul";

/** Modul zur Adresse: das mit dem längsten passenden Pfad. */
export function modulZuPfad(module: ModulManifest[], pfad: string): ModulManifest | undefined {
  let treffer: ModulManifest | undefined;
  for (const modul of module) {
    const ziel = modul.navigation.pfad;
    if (pfad !== ziel && !pfad.startsWith(`${ziel}/`)) continue;
    if (!treffer || ziel.length > treffer.navigation.pfad.length) treffer = modul;
  }
  return treffer;
}

/** Turnier-ID aus der Adresse, wenn das Modul sie direkt hinter seinem Pfad führt (`/turnier/<id>`). */
export function turnierIdAusPfad(modul: ModulManifest, pfad: string): string | null {
  const rest = pfad.slice(modul.navigation.pfad.length).split("/").filter(Boolean);
  return rest[0] ? decodeURIComponent(rest[0]) : null;
}

/** „Seite – Turnier – Schiesshub“; leere Teile entfallen. */
export function seitentitel(teile: readonly (string | null | undefined)[], marke: string): string {
  return [...teile.filter((teil): teil is string => Boolean(teil?.trim())), marke].join(" – ");
}

/** Zuletzt von der Shell geschriebener Titel; anfangs der aus `index.html`. */
let letzterShellTitel: string | null = typeof document === "undefined" ? null : document.title;

/**
 * Setzt `document.title` je Ansicht aus dem Modul-Manifest: Titel des Moduls und, wo das Modul
 * es wünscht (`titelTurnier`), der Name des Turniers. Wer mehrere Tabs offen hat (Kasse und
 * Erfassung), unterscheidet sie so. Einzelne Seiten (Bildschirm, Aushang, Druck) dürfen den Titel
 * danach selbst überschreiben.
 */
export function useSeitentitel(pfad: string, anmeldeSeite: AnmeldeSeite | null): void {
  const { t } = useTranslation("shell");
  const rechte = useRechte();
  const module = useAlleModule();
  const modul = anmeldeSeite ? undefined : modulZuPfad(module, pfad);
  const art = modul?.titelTurnier;
  const [gespeichert] = useLocalStorage<string | null>({
    key: TURNIER_SPEICHER,
    defaultValue: null,
    getInitialValueInEffect: false,
  });
  const liste = useQuery({
    ...turnierListeAbfrage(),
    enabled: Boolean(art) && darfMit(rechte, "tournament.read"),
  });

  let turnierName: string | undefined;
  if (modul && art && liste.data) {
    if (art === "adresse") {
      const id = turnierIdAusPfad(modul, pfad);
      turnierName = id ? liste.data.find((eintrag) => eintrag.id === id)?.name : undefined;
    } else {
      turnierName = bestimmeTurnier(liste.data, gespeichert).turnier?.name;
    }
  }

  const seite = anmeldeSeite
    ? t(`seitentitel.${anmeldeSeite}`)
    : modul
      ? t(`${modul.namensraum}:titel`)
      : pfad === "/"
        ? t("seitentitel.start")
        : undefined;
  const titel = seitentitel([seite, turnierName], t("seitentitel.marke"));

  useEffect(() => {
    // Hat eine Seite den Titel inzwischen selbst gesetzt (Bildschirm, Aushang, Druck), bleibt ihrer
    // stehen; sie stellt beim Verlassen den vorigen wieder her, danach schreibt die Shell wieder.
    if (letzterShellTitel !== null && document.title !== letzterShellTitel) return;
    document.title = titel;
    letzterShellTitel = titel;
  }, [titel]);
}
