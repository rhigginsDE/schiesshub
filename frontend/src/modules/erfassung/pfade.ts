import type { Erfassungsart } from "./api";

export const ERFASSUNG_ID = "erfassung";
export const ERFASSUNG_PFAD = "/erfassung";

/** Suchparameter der Station: offener Start und gewählte Darstellung. */
export interface ErfassungSuche {
  start?: string;
  art?: Erfassungsart;
}

export function leseErfassungSuche(suche: Record<string, unknown>): ErfassungSuche {
  const ergebnis: ErfassungSuche = {};
  if (typeof suche.start === "string" && suche.start !== "") ergebnis.start = suche.start;
  if (suche.art === "shot" || suche.art === "series") ergebnis.art = suche.art;
  return ergebnis;
}
