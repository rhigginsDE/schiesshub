import type { AnyRoute } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { createContext, useContext, useMemo } from "react";
import type { EreignisZuordnung } from "../api/ereignisse";
import { type Anforderung, darfMit, useRechte } from "./berechtigungen";

/**
 * Ein Modul meldet sich mit diesem Manifest an. Die App-Shell baut daraus Navigation,
 * Startseiten-Kacheln und Routen; sie kennt kein Modul beim Namen.
 *
 * Texte: In `src/locales/<sprache>/<namensraum>.json` müssen `titel` (Navigation, Überschrift)
 * und `zweck` (ein Satz, wofür das Modul da ist) stehen.
 */
export interface ModulManifest {
  /** Eindeutiger Name, gleich dem Ordner unter `src/modules/` */
  id: string;
  /** Namensraum der Sprachdatei, in der Regel gleich `id` */
  namensraum: string;
  navigation: ModulNavigation;
  /**
   * Berechtigung, die ein Gerät oder eine Person braucht, um das Modul zu sehen, so wie das
   * Backend sie vergibt (`tournament.read`). Bei einer Liste reicht eine davon; `null` = für alle.
   * Kennt der Server die Berechtigung nicht, gilt sie als Platzhalter und sperrt nichts.
   */
  berechtigung: Anforderung;
  /** Fertige Routen des Moduls; Eltern-Route ist `rootRoute` aus `src/app/rootRoute.ts`. */
  routen: AnyRoute[];
  /** Server-Ereignisse, nach denen Daten dieses Moduls neu geladen werden. */
  ereignisse?: EreignisZuordnung;
}

export type ModulNavigation =
  /** Eigene Station: Eintrag in der Kopfzeile und Kachel auf der Startseite */
  | { art: "station"; pfad: string; icon: LucideIcon; reihenfolge: number }
  /** Bereich innerhalb einer Station: erscheint auf der Seite der Station */
  | { art: "bereich"; station: string; pfad: string; icon: LucideIcon; reihenfolge: number };

const ModulKontext = createContext<ModulManifest[]>([]);

export const ModulProvider = ModulKontext.Provider;

function nachReihenfolge(a: ModulManifest, b: ModulManifest): number {
  return a.navigation.reihenfolge - b.navigation.reihenfolge;
}

/** Alle Module, die das Gerät bzw. die angemeldete Person sehen darf. */
export function useModule(): ModulManifest[] {
  const alle = useContext(ModulKontext);
  const rechte = useRechte();
  return useMemo(() => alle.filter((modul) => darfMit(rechte, modul.berechtigung)), [alle, rechte]);
}

/** Alle angemeldeten Module, unabhängig von den Rechten (z. B. für Routen und Ereignisse). */
export function useAlleModule(): ModulManifest[] {
  return useContext(ModulKontext);
}

/** Module, die als Station in Kopfzeile und Startseite erscheinen. */
export function useStationen(): ModulManifest[] {
  return useModule()
    .filter((modul) => modul.navigation.art === "station")
    .sort(nachReihenfolge);
}

/** Module, die als Bereich zu einer Station gehören. */
export function useBereiche(station: string): ModulManifest[] {
  return useModule()
    .filter((modul) => modul.navigation.art === "bereich" && modul.navigation.station === station)
    .sort(nachReihenfolge);
}
