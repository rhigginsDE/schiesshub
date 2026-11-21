import type { AnyRoute } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { createContext, useContext } from "react";
import type { EreignisZuordnung } from "../api/ereignisse";

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
   * Berechtigung, die ein Gerät oder eine Person braucht, um das Modul zu sehen.
   * Platzhalter, bis das Backend-Modul `auth` steht; `null` = für alle sichtbar.
   */
  berechtigung: string | null;
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

/** Alle Module, die das Gerät sehen darf. */
export function useModule(): ModulManifest[] {
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
