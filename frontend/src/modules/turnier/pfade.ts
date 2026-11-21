import type { Bereich } from "./vollstaendigkeit";

export const TURNIER_ID = "turnier";
export const TURNIER_PFAD = "/turnier";
export const EINRICHTEN_PFAD = "/turnier/$turnierId";

/** Suchparameter der Einrichtung; stehen in der Adresse, damit „Zurück“ und Links funktionieren. */
export interface EinrichtenSuche {
  bereich?: Bereich;
  /** Aufgeklappter Wettbewerb */
  wettbewerb?: string;
}
