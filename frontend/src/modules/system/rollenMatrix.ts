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
 * (`GET /auth/permissions` → `requires`, ermittelt aus den Prüfungen der Endpunkte).
 */
export function voraussetzungen(liste: readonly Berechtigung[]): Map<string, string[]> {
  const karte = new Map<string, string[]>();
  for (const eintrag of liste) {
    const braucht = eintrag.requires.filter((recht) => recht !== eintrag.permission);
    if (braucht.length > 0) karte.set(eintrag.permission, braucht);
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

/** Startrollen mit festem Satz in der Sprachdatei (`rollen.beschreibung.<schluessel>`). */
const FESTE_ROLLEN = ["administrator", "turnierleitung", "kasse", "auswertung", "anzeige"];

/** Was eine Standaufsicht braucht und höchstens hat, damit ihr fester Satz noch stimmt. */
const STANDAUFSICHT_RECHTE = ["start.call", "start.abort", "start.read", "tournament.read"];

/**
 * Schlüssel des festen Satzes für eine Rolle, sonst `null` (dann gilt die Zusammenfassung aus den
 * Rechten). Startrollen nur, solange niemand ihre Rechte geändert hat, auch nicht im Entwurf.
 * „Standaufsicht“ ist keine Startrolle des Servers; der Satz gilt, wenn Name und Rechte passen.
 */
export function festeBeschreibung(
  rolle: Pick<Rolle, "is_system" | "starter_key" | "customized" | "name">,
  eintraege: readonly string[],
  bekannte: readonly string[],
  imEntwurfGeaendert: boolean,
): string | null {
  if (rolle.is_system) return "administrator";
  if (imEntwurfGeaendert) return null;
  const start = rolle.starter_key?.trim().toLowerCase();
  if (start && !rolle.customized && FESTE_ROLLEN.includes(start)) return start;
  if (rolle.name.trim().toLowerCase() === "standaufsicht") {
    const hat = bekannte.filter((recht) => gewaehrt(eintraege, recht));
    if (hat.includes("start.call") && hat.every((recht) => STANDAUFSICHT_RECHTE.includes(recht))) {
      return "standaufsicht";
    }
  }
  return null;
}

/** Ein Teil der Zusammenfassung: ein ganzer Bereich oder ein einzelnes Recht. */
export type Zusammenfassungsteil =
  | { art: "bereich"; titel: string }
  | { art: "recht"; recht: string };

/**
 * Kurze Zusammenfassung der Rechte einer eigenen Rolle, nach Bereichen: Ist ein Bereich ganz
 * erlaubt, steht er als Ganzes da. Sonst die einzelnen Rechte; „ansehen“ entfällt, wenn im selben
 * Bereich mehr als Ansehen erlaubt ist (es versteht sich dann von selbst).
 */
export function zusammenfassen(
  eintraege: readonly string[],
  gruppen: readonly Berechtigungsgruppe[],
): Zusammenfassungsteil[] {
  const teile: Zusammenfassungsteil[] = [];
  for (const gruppe of gruppen) {
    const erlaubt = gruppe.berechtigungen.filter((recht) => gewaehrt(eintraege, recht));
    if (erlaubt.length === 0) continue;
    if (erlaubt.length === gruppe.berechtigungen.length && erlaubt.length > 1) {
      teile.push({ art: "bereich", titel: gruppe.titel });
      continue;
    }
    const handeln = erlaubt.filter((recht) => rechtTaetigkeit(recht) !== "read");
    for (const recht of handeln.length > 0 ? handeln : erlaubt) teile.push({ art: "recht", recht });
  }
  return teile;
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
