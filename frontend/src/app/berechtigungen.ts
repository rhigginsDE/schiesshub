import { createContext, useContext } from "react";
import type { ModulManifest } from "./modul";

/**
 * Rechte des Geräts bzw. der angemeldeten Person, wie `GET /auth/status` sie liefert.
 *
 * - `offen`: Der Server setzt keine Anmeldung durch und niemand ist angemeldet. Dann ist alles
 *   sichtbar, damit die App ohne Ersteinrichtung benutzbar bleibt.
 * - sonst: `erlaubt` enthält Berechtigungen (`tournament.edit`) oder Muster (`person.*`, `*`).
 *   `bekannt` sind alle Berechtigungen, die der Server kennt (falls lesbar). Eine Berechtigung,
 *   die der Server gar nicht kennt, ist ein Platzhalter im Frontend und sperrt nichts.
 */
export type Rechte =
  | { offen: true }
  | { offen: false; erlaubt: readonly string[]; bekannt?: ReadonlySet<string> };

export const OFFENE_RECHTE: Rechte = { offen: true };

/** Eine Berechtigung oder mehrere, von denen eine reicht. `null` = für alle. */
export type Anforderung = string | readonly string[] | null;

/** `*` passt auf alles, `person.*` auf alles, was mit `person.` beginnt. */
export function passt(muster: string, berechtigung: string): boolean {
  if (muster === "*" || muster === berechtigung) return true;
  return muster.endsWith(".*") && berechtigung.startsWith(muster.slice(0, -1));
}

export function gewaehrt(erlaubt: readonly string[], berechtigung: string): boolean {
  return erlaubt.some((muster) => passt(muster, berechtigung));
}

/** Entscheidet, ob die Rechte für die Anforderung reichen. */
export function darfMit(rechte: Rechte, anforderung: Anforderung): boolean {
  if (anforderung === null) return true;
  if (typeof anforderung !== "string") {
    return anforderung.length === 0 || anforderung.some((eine) => darfMit(rechte, eine));
  }
  if (rechte.offen) return true;
  if (gewaehrt(rechte.erlaubt, anforderung)) return true;
  return rechte.bekannt !== undefined && !rechte.bekannt.has(anforderung);
}

let aktuelleRechte: Rechte = OFFENE_RECHTE;

/** Setzt die Rechte für `darf()` außerhalb von React; nur die App-Shell ruft das auf. */
export function setzeAktuelleRechte(rechte: Rechte) {
  aktuelleRechte = rechte;
}

/**
 * Wie `useDarf`, aber ohne Hook (liest die zuletzt geladenen Rechte). In Komponenten besser
 * `useDarf`, weil die Komponente dann neu zeichnet, sobald sich die Rechte ändern.
 */
export function darf(anforderung: Anforderung): boolean {
  return darfMit(aktuelleRechte, anforderung);
}

export function sichtbareModule(
  module: ModulManifest[],
  rechte: Rechte = OFFENE_RECHTE,
): ModulManifest[] {
  return module.filter((modul) => darfMit(rechte, modul.berechtigung));
}

const RechteKontext = createContext<Rechte>(OFFENE_RECHTE);

/** Stellt die Rechte bereit; die App-Shell setzt ihn aus `GET /auth/status`. */
export const RechteProvider = RechteKontext.Provider;

export function useRechte(): Rechte {
  return useContext(RechteKontext);
}

/**
 * Darf das Gerät bzw. die angemeldete Person das? Für Knöpfe und Bereiche in Modulen:
 * `const darfBearbeiten = useDarf("tournament.edit");`
 * Ohne Anmeldung und ohne Durchsetzung im Server ist alles erlaubt.
 */
export function useDarf(anforderung: Anforderung): boolean {
  return darfMit(useRechte(), anforderung);
}
