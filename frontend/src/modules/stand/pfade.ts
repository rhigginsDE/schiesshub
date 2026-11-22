export const STAND_ID = "stand";
export const STAND_PFAD = "/erfassung/stand";

/** Suchparameter der Standansicht; nur IDs, nie Namen. */
export interface StandSuche {
  ansicht?: "startliste";
  /** Filter der Startliste */
  wettbewerb?: string;
  stand?: string;
}

const ID_MUSTER = /^[0-9a-f-]{8,64}$/i;

export function leseStandSuche(suche: Record<string, unknown>): StandSuche {
  const id = (wert: unknown) =>
    typeof wert === "string" && ID_MUSTER.test(wert) ? wert : undefined;
  return {
    ansicht: suche.ansicht === "startliste" ? "startliste" : undefined,
    wettbewerb: id(suche.wettbewerb),
    stand: id(suche.stand),
  };
}
