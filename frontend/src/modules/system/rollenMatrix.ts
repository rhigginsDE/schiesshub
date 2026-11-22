import type { Berechtigung, Rolle } from "../../api/typenSystem";
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

/**
 * Tätigkeit einer Berechtigung für den Rückfall-Namen: der Teil nach dem letzten Punkt
 * (`display.control` → `control`, `export.full_names` → `full_names`), `*` → `alle`.
 * Nur Buchstaben und Unterstriche, damit daraus ein gültiger Schlüssel der Sprachdatei wird.
 */
export function rechtTaetigkeit(name: string): string | null {
  const teil = name.split(".").pop() ?? "";
  if (teil === "*") return "alle";
  return /^[a-z_]+$/.test(teil) ? teil : null;
}

/** Schlüssel in der Sprachdatei: Punkte trennen dort Ebenen, darum `backup.read` → `backup_read`. */
export function textSchluessel(name: string): string {
  return name.replace(/\./g, "_").replace(/\*/g, "alle");
}

/**
 * Was eine Berechtigung braucht, damit sie an ihrer Station etwas nützt, so wie der Server es meldet
 * (`GET /auth/permissions` → `requires`, ermittelt aus den Prüfungen der Endpunkte). Ein älterer
 * Server meldet nichts; dann behauptet die Matrix auch nichts.
 */
export function voraussetzungen(liste: readonly Berechtigung[]): Map<string, string[]> {
  const karte = new Map<string, string[]>();
  for (const eintrag of liste) {
    const braucht = (eintrag as { requires?: unknown }).requires;
    if (!Array.isArray(braucht)) continue;
    const bekannte = braucht.filter(
      (recht): recht is string => typeof recht === "string" && recht !== eintrag.permission,
    );
    if (bekannte.length > 0) karte.set(eintrag.permission, bekannte);
  }
  return karte;
}

export interface Luecke {
  /** Gewährte Berechtigungen, denen etwas fehlt, in der Reihenfolge der bekannten */
  rechte: string[];
  /** Was ihnen fehlt, ohne Doppelte */
  fehlt: string[];
}

/** Gewährte Berechtigungen einer Rolle, deren Voraussetzungen fehlen; `null`, wenn nichts fehlt. */
export function luecke(
  eintraege: readonly string[],
  bekannte: readonly string[],
  braucht: ReadonlyMap<string, readonly string[]>,
): Luecke | null {
  const rechte: string[] = [];
  const fehlt: string[] = [];
  for (const recht of bekannte) {
    if (!gewaehrt(eintraege, recht)) continue;
    const offen = (braucht.get(recht) ?? []).filter((noetig) => !gewaehrt(eintraege, noetig));
    if (offen.length === 0) continue;
    rechte.push(recht);
    for (const noetig of offen) if (!fehlt.includes(noetig)) fehlt.push(noetig);
  }
  return rechte.length > 0 ? { rechte, fehlt } : null;
}

/** Fehlende Voraussetzungen einer Berechtigung (für die Zelle der Matrix). */
export function fehlendeVoraussetzungen(
  eintraege: readonly string[],
  recht: string,
  braucht: ReadonlyMap<string, readonly string[]>,
): string[] {
  if (!gewaehrt(eintraege, recht)) return [];
  return (braucht.get(recht) ?? []).filter((noetig) => !gewaehrt(eintraege, noetig));
}

/** Setzt mehrere Berechtigungen zusätzlich (z. B. die fehlenden Voraussetzungen). */
export function hinzufuegen(
  eintraege: readonly string[],
  bekannte: readonly string[],
  rechte: readonly string[],
): string[] {
  return rechte.reduce<string[]>(
    (neu, recht) => umschalten(neu, bekannte, recht, true),
    [...eintraege],
  );
}

/**
 * Verwaltungsrechte wie im Server (`ADMINISTRATION_PERMISSIONS`): Eine Rolle, die eines davon
 * gewährt, taugt nicht als Standardrolle eines Geräts, weil dort niemand eine PIN eingibt.
 */
export const VERWALTUNGSRECHTE = [
  "role.manage",
  "user.manage",
  "device.manage",
  "system.manage",
  "backup.manage",
] as const;

export function taugtAlsStandardrolle(rolle: Pick<Rolle, "is_system" | "permissions">): boolean {
  return !rolle.is_system && !VERWALTUNGSRECHTE.some((recht) => gewaehrt(rolle.permissions, recht));
}
