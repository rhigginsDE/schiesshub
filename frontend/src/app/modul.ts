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
   * Backend sie vergibt (`tournament.read`). Bei einer Liste reicht eine davon; `null` = für alle,
   * die eingeloggt sind. Nur echte Berechtigungen des Servers; Platzhalter sperren.
   */
  berechtigung: Anforderung;
  /** Fertige Routen des Moduls; Eltern-Route ist `rootRoute` aus `src/app/rootRoute.ts`. */
  routen: AnyRoute[];
  /** Server-Ereignisse, nach denen Daten dieses Moduls neu geladen werden. */
  ereignisse?: EreignisZuordnung;
  /**
   * Turniername im Seitentitel: `aktiv` = das an diesem Gerät gewählte Turnier (Stationen wie
   * Anmeldung oder Erfassung), `adresse` = die Turnier-ID direkt hinter dem Pfad (`/turnier/<id>`).
   */
  titelTurnier?: "aktiv" | "adresse";
}

export type ModulNavigation =
  /** Eigene Station: Eintrag in der Kopfzeile und Kachel auf der Startseite */
  | { art: "station"; pfad: string; icon: LucideIcon; reihenfolge: number }
  /**
   * Bereich innerhalb einer Station: erscheint auf der Seite der Station. Mit `eigenstaendig`
   * erscheint er selbst als Station (an deren Platz), wenn die Rolle die Station nicht sieht,
   * wohl aber den Bereich – z. B. der Stand für die Standaufsicht ohne Rechte an der Erfassung.
   */
  | {
      art: "bereich";
      station: string;
      pfad: string;
      icon: LucideIcon;
      reihenfolge: number;
      eigenstaendig?: boolean;
    };

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

/**
 * Module, die als Station in Kopfzeile und Startseite erscheinen: alle Stationen, dazu
 * eigenständige Bereiche, deren Station die Rolle nicht sieht (auf dem Platz dieser Station).
 */
export function stationenAus(alle: ModulManifest[], sichtbar: ModulManifest[]): ModulManifest[] {
  const sichtbareIds = new Set(sichtbar.map((modul) => modul.id));
  const platz = (modul: ModulManifest) => {
    const nav = modul.navigation;
    if (nav.art === "station") return nav.reihenfolge;
    const station = alle.find((m) => m.id === nav.station);
    return (station?.navigation.reihenfolge ?? nav.reihenfolge) + nav.reihenfolge / 1000;
  };
  return sichtbar
    .filter((modul) => {
      const nav = modul.navigation;
      return (
        nav.art === "station" || (nav.eigenstaendig === true && !sichtbareIds.has(nav.station))
      );
    })
    .sort((a, b) => platz(a) - platz(b));
}

export function useStationen(): ModulManifest[] {
  const alle = useContext(ModulKontext);
  const sichtbar = useModule();
  return useMemo(() => stationenAus(alle, sichtbar), [alle, sichtbar]);
}

/** Module, die als Bereich zu einer Station gehören. */
export function useBereiche(station: string): ModulManifest[] {
  return useModule()
    .filter((modul) => modul.navigation.art === "bereich" && modul.navigation.station === station)
    .sort(nachReihenfolge);
}
