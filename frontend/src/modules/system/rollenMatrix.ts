import type { Berechtigung } from "../../api/typenSystem";
import { gewaehrt, passt } from "../../app/berechtigungen";

/**
 * Rechte einer Rolle als Matrix: Die Rolle speichert Namen (`club.edit`) oder Muster
 * (`person.*`, `*`), die Matrix zeigt je bekannter Berechtigung ein Häkchen.
 */

export interface Berechtigungsgruppe {
  modul: string;
  titel: string;
  berechtigungen: string[];
}

/** Nach Modul gruppiert, Gruppen nach Titel, Berechtigungen nach Name sortiert. */
export function gruppieren(liste: readonly Berechtigung[]): Berechtigungsgruppe[] {
  const gruppen = new Map<string, Berechtigungsgruppe>();
  for (const eintrag of liste) {
    let gruppe = gruppen.get(eintrag.module);
    if (!gruppe) {
      gruppe = { modul: eintrag.module, titel: eintrag.module_title, berechtigungen: [] };
      gruppen.set(eintrag.module, gruppe);
    }
    if (!gruppe.berechtigungen.includes(eintrag.permission)) {
      gruppe.berechtigungen.push(eintrag.permission);
    }
  }
  return [...gruppen.values()]
    .map((gruppe) => ({ ...gruppe, berechtigungen: [...gruppe.berechtigungen].sort() }))
    .sort((a, b) => a.titel.localeCompare(b.titel, "de"));
}

/** Das Muster, über das eine Berechtigung gewährt ist (nicht der Name selbst), sonst `null`. */
export function ueberMuster(eintraege: readonly string[], berechtigung: string): string | null {
  return eintraege.find((muster) => muster !== berechtigung && passt(muster, berechtigung)) ?? null;
}

/**
 * Schaltet eine Berechtigung an oder aus und gibt die neuen Einträge der Rolle zurück.
 * Ausschalten unter einem Muster löst das Muster in die einzelnen bekannten Berechtigungen auf,
 * damit die übrigen erhalten bleiben. Unbekannte Einträge bleiben unangetastet.
 */
export function umschalten(
  eintraege: readonly string[],
  bekannte: readonly string[],
  berechtigung: string,
  an: boolean,
): string[] {
  if (an) {
    return gewaehrt(eintraege, berechtigung) ? [...eintraege] : [...eintraege, berechtigung];
  }
  const neu: string[] = [];
  for (const eintrag of eintraege) {
    if (eintrag === berechtigung) continue;
    if (passt(eintrag, berechtigung)) {
      for (const andere of bekannte) {
        if (andere !== berechtigung && passt(eintrag, andere) && !neu.includes(andere)) {
          neu.push(andere);
        }
      }
      continue;
    }
    if (!neu.includes(eintrag)) neu.push(eintrag);
  }
  // Ein anderes Muster deckt die Berechtigung womöglich noch ab: dann auch das auflösen.
  return gewaehrt(neu, berechtigung) ? umschalten(neu, bekannte, berechtigung, false) : neu;
}

/** Gleiche Rechte, unabhängig von der Reihenfolge? */
export function gleicheEintraege(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  const menge = new Set(a);
  return b.every((eintrag) => menge.has(eintrag));
}

/** Schlüssel in der Sprachdatei: Punkte trennen dort Ebenen, darum `backup.read` → `backup_read`. */
export function textSchluessel(name: string): string {
  return name.replace(/\./g, "_").replace(/\*/g, "alle");
}
