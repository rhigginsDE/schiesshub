import type { Erfassungsart } from "./api";

export const ERFASSUNG_ID = "erfassung";
export const ERFASSUNG_PFAD = "/erfassung";

/** Suchparameter der Station: offener Start und gewählte Darstellung. */
export interface ErfassungSuche {
  start?: string;
  art?: Erfassungsart;
  /** Vom Schießstand: Rückfrage „aufgegeben“ für diesen Start gleich öffnen (einmalig) */
  aufgeben?: boolean;
}

export function leseErfassungSuche(suche: Record<string, unknown>): ErfassungSuche {
  const ergebnis: ErfassungSuche = {};
  if (typeof suche.start === "string" && suche.start !== "") ergebnis.start = suche.start;
  if (suche.art === "shot" || suche.art === "series") ergebnis.art = suche.art;
  if (ergebnis.start && (suche.aufgeben === true || suche.aufgeben === "1")) {
    ergebnis.aufgeben = true;
  }
  return ergebnis;
}
