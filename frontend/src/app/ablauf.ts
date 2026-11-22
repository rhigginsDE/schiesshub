/**
 * Der Ablauf auf der Startseite: fünf Schritte vom Turnier bis zur Sicherung, je mit Zustand,
 * und genau ein Schritt, der als Nächstes dran ist. Ohne React, einzeln getestet.
 *
 * Grundlage sind nur Daten des Servers (Turnierliste, Übersicht, Startliste, Sicherungsstatus).
 * Am Wettkampftag sind mehrere Stationen gleichzeitig in Arbeit; dann sperrt der Ablauf nichts,
 * er hebt nur hervor, was als Nächstes sinnvoll ist.
 */

import { sortiereTurniere } from "../components/useAktivesTurnier";
import type { StationStart } from "../modules/anmeldung/api";
import type { Turnier } from "../modules/turnier/typen";
import type { OffenerPunkt } from "../modules/turnier/vollstaendigkeit";

export const SCHRITTE = ["turnier", "anmeldung", "erfassung", "anzeige", "sicherung"] as const;
export type SchrittId = (typeof SCHRITTE)[number];

/**
 * - `offen`: kann und sollte gemacht werden
 * - `in_arbeit`: läuft gerade (Anmeldung offen, Starts in Arbeit)
 * - `erledigt`: fertig
 * - `ok`: Sicherung in Ordnung
 * - `wartet`: geht noch nicht (der Text sagt, warum); erreichbar bleibt der Schritt trotzdem
 * - `gestoert`: etwas ist kaputt und braucht Hilfe (Sicherung)
 * - `unbekannt`: Zahlen fehlen (keine Berechtigung, noch nicht geladen)
 */
export type SchrittStand =
  | "offen"
  | "in_arbeit"
  | "erledigt"
  | "ok"
  | "wartet"
  | "gestoert"
  | "unbekannt";

/** Was die Hauptaktion des nächsten Schritts tut; Texte in `shell.json` → `ablauf.aktion.*`. */
export type AblaufAktion =
  | "turnier_anlegen"
  | "turnier_einrichten"
  | "turnier_starten"
  | "zur_anmeldung"
  | "ergebnisse_erfassen"
  | "anzeige_oeffnen"
  | "siegerliste"
  | "passwort_festlegen"
  | "zur_sicherung";

export interface AblaufSchritt {
  id: SchrittId;
  stand: SchrittStand;
  /** Schlüssel in `shell.json` → `ablauf.text.*` */
  text: string;
  werte?: Record<string, string | number>;
  /** Beim Entwurf: der erste offene Punkt der Einrichtung (Text kommt aus `turnier.json`) */
  punkt?: OffenerPunkt;
}

export interface StartZaehlung {
  /** Angemeldete Schützen mit mindestens einem Start */
  schuetzen: number;
  starts: number;
  /** Gebucht, aufgerufen oder erfasst, aber nicht abgeschlossen */
  offen: number;
  /** Abgeschlossen oder abgebrochen */
  abgeschlossen: number;
  /** Mit abgeschlossenem Ergebnis (ohne Abbrüche) */
  ergebnisse: number;
}

export type SicherungEingabe =
  | { art: "ok"; zeit: string }
  | { art: "keine" }
  /**
   * `behebbar`: Das Gerät bzw. die Person darf die Sicherung einstellen.
   * `nieGesichert`: Es gibt noch keine gelungene Sicherung.
   */
  | { art: "warnung"; code: string; behebbar: boolean; nieGesichert?: boolean };

export interface AblaufEingaben {
  turnier: Pick<Turnier, "name" | "status"> | null;
  /** Offene Punkte der Einrichtung (nur beim Entwurf); `undefined` = unbekannt */
  offenePunkte?: readonly OffenerPunkt[];
  wettbewerbe?: number;
  /** `undefined` = unbekannt (keine Berechtigung, lädt, Fehler) */
  starts?: StartZaehlung;
  /** `undefined` = unbekannt (keine Berechtigung `backup.read`) */
  sicherung?: SicherungEingabe;
}

export interface Ablauf {
  schritte: AblaufSchritt[];
  naechster: SchrittId;
  aktion: AblaufAktion;
  /**
   * Gestörte Sicherung, die (noch) nicht der nächste Schritt ist: ihre eigene, nachrangige Aktion
   * in der Zeile der Sicherung. Sonst `undefined`.
   */
  sicherungAktion?: AblaufAktion;
}

const OFFEN: ReadonlySet<StationStart["status"]> = new Set(["registered", "called", "captured"]);

/** Zahlen aus der Startliste des Turniers. */
export function zaehleStarts(
  starts: readonly Pick<StationStart, "entry_id" | "status">[],
): StartZaehlung {
  const offen = starts.filter((start) => OFFEN.has(start.status)).length;
  return {
    schuetzen: new Set(starts.map((start) => start.entry_id)).size,
    starts: starts.length,
    offen,
    abgeschlossen: starts.length - offen,
    ergebnisse: starts.filter((start) => start.status === "final").length,
  };
}

/**
 * Das Turnier, auf das sich der Ablauf bezieht: das der Stationen (`bestimmeTurnier`), sonst das
 * zuletzt bearbeitete, aktive vor Entwürfen vor abgeschlossenen.
 */
export function turnierFuerAblauf(
  bestimmt: Turnier | null,
  turniere: readonly Turnier[],
): Turnier | null {
  if (bestimmt) return bestimmt;
  const zuletzt = (status: Turnier["status"]) =>
    turniere
      .filter((t) => t.status === status)
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0];
  return zuletzt("active") ?? zuletzt("draft") ?? sortiereTurniere(turniere)[0] ?? null;
}

function turnierSchritt({ turnier, offenePunkte, wettbewerbe }: AblaufEingaben): AblaufSchritt {
  if (!turnier) return { id: "turnier", stand: "offen", text: "turnier_keins" };
  const name = turnier.name;
  if (turnier.status === "active") {
    return wettbewerbe === undefined
      ? { id: "turnier", stand: "erledigt", text: "turnier_laeuft", werte: { name } }
      : {
          id: "turnier",
          stand: "erledigt",
          text: "turnier_laeuft_wettbewerbe",
          werte: { name, count: wettbewerbe },
        };
  }
  if (turnier.status === "closed") {
    return { id: "turnier", stand: "erledigt", text: "turnier_abgeschlossen", werte: { name } };
  }
  if (offenePunkte === undefined) {
    return { id: "turnier", stand: "offen", text: "turnier_entwurf", werte: { name } };
  }
  const [erster] = offenePunkte;
  if (erster) {
    return {
      id: "turnier",
      stand: "offen",
      text: "turnier_entwurf_offen",
      werte: { name, count: offenePunkte.length - 1 },
      punkt: erster,
    };
  }
  return { id: "turnier", stand: "offen", text: "turnier_entwurf_fertig", werte: { name } };
}

function anmeldungSchritt({ turnier, starts }: AblaufEingaben): AblaufSchritt {
  if (!turnier || turnier.status === "draft") {
    return { id: "anmeldung", stand: "wartet", text: "wartet_auf_start" };
  }
  const fertig = turnier.status === "closed";
  if (!starts) {
    return fertig
      ? { id: "anmeldung", stand: "erledigt", text: "anmeldung_beendet" }
      : { id: "anmeldung", stand: "in_arbeit", text: "anmeldung_offen" };
  }
  if (starts.starts === 0) {
    return fertig
      ? { id: "anmeldung", stand: "erledigt", text: "anmeldung_keine" }
      : { id: "anmeldung", stand: "offen", text: "anmeldung_keine" };
  }
  return {
    id: "anmeldung",
    stand: fertig ? "erledigt" : "in_arbeit",
    text: "anmeldung_zahl",
    werte: { schuetzen: starts.schuetzen, count: starts.starts },
  };
}

function erfassungSchritt({ turnier, starts }: AblaufEingaben): AblaufSchritt {
  if (!turnier || turnier.status === "draft") {
    return { id: "erfassung", stand: "wartet", text: "wartet_auf_start" };
  }
  if (!starts) {
    return turnier.status === "closed"
      ? { id: "erfassung", stand: "erledigt", text: "erfassung_beendet" }
      : { id: "erfassung", stand: "unbekannt", text: "erfassung_unbekannt" };
  }
  if (starts.starts === 0) {
    return turnier.status === "closed"
      ? { id: "erfassung", stand: "erledigt", text: "erfassung_beendet" }
      : { id: "erfassung", stand: "wartet", text: "wartet_auf_starts" };
  }
  if (starts.offen > 0) {
    return {
      id: "erfassung",
      stand: "in_arbeit",
      text: "erfassung_zahl",
      werte: { count: starts.offen, abgeschlossen: starts.abgeschlossen },
    };
  }
  return {
    id: "erfassung",
    stand: "erledigt",
    text: "erfassung_fertig",
    werte: { count: starts.starts },
  };
}

function anzeigeSchritt({ turnier, starts }: AblaufEingaben): AblaufSchritt {
  if (!turnier || turnier.status === "draft") {
    return { id: "anzeige", stand: "wartet", text: "wartet_auf_start" };
  }
  if (starts && starts.starts > 0 && starts.offen === 0) {
    return { id: "anzeige", stand: "offen", text: "anzeige_siegerliste" };
  }
  if (starts && starts.ergebnisse > 0) {
    return {
      id: "anzeige",
      stand: "in_arbeit",
      text: "anzeige_live",
      werte: { count: starts.ergebnisse },
    };
  }
  return { id: "anzeige", stand: "offen", text: "anzeige_bereit" };
}

function sicherungSchritt({ sicherung }: AblaufEingaben): AblaufSchritt {
  if (!sicherung) return { id: "sicherung", stand: "unbekannt", text: "sicherung_unbekannt" };
  if (sicherung.art === "warnung") {
    return {
      id: "sicherung",
      stand: "gestoert",
      text: "sicherung_warnung",
      werte: { code: sicherung.code },
    };
  }
  if (sicherung.art === "keine")
    return { id: "sicherung", stand: "offen", text: "sicherung_keine" };
  return { id: "sicherung", stand: "ok", text: "sicherung_ok", werte: { zeit: sicherung.zeit } };
}

/**
 * Welcher Schritt als Nächstes dran ist:
 * - kein Turnier oder Entwurf: das Turnier einrichten
 * - läuft ohne Starts: Anmeldung; mit offenen Starts: Erfassung; alles abgeschlossen: Anzeige
 *
 * Eine gestörte Sicherung (die diese Person beheben darf) verdrängt die Arbeit am Stand nicht; sie
 * zeigt ihren Zustand mit eigener Aktion. Sie wird erst der nächste Schritt,
 * - wenn schon Ergebnisse erfasst sind und noch nie gesichert wurde (Daten sind gefährdet), oder
 * - wenn sonst nichts mehr ansteht (alle Starts erledigt oder Turnier abgeschlossen).
 */
function naechsterSchritt(e: AblaufEingaben): SchrittId {
  const { turnier, starts, sicherung } = e;
  if (!turnier || turnier.status === "draft") return "turnier";
  const gestoert = sicherung?.art === "warnung" && sicherung.behebbar;
  if (gestoert && sicherung.nieGesichert && starts && starts.ergebnisse > 0) return "sicherung";
  if (turnier.status === "closed") return gestoert ? "sicherung" : "anzeige";
  if (!starts || starts.starts === 0) return "anmeldung";
  if (starts.offen > 0) return "erfassung";
  return gestoert ? "sicherung" : "anzeige";
}

function aktionFuer(id: SchrittId, e: AblaufEingaben, schritt: AblaufSchritt): AblaufAktion {
  switch (id) {
    case "turnier":
      if (!e.turnier) return "turnier_anlegen";
      return schritt.text === "turnier_entwurf_fertig" ? "turnier_starten" : "turnier_einrichten";
    case "anmeldung":
      return "zur_anmeldung";
    case "erfassung":
      return "ergebnisse_erfassen";
    case "anzeige":
      return schritt.text === "anzeige_siegerliste" ? "siegerliste" : "anzeige_oeffnen";
    case "sicherung":
      return e.sicherung?.art === "warnung" && e.sicherung.code === "passphrase_missing"
        ? "passwort_festlegen"
        : "zur_sicherung";
  }
}

/** Schritte mit Zustand und der eine nächste Schritt samt Hauptaktion. */
export function ablauf(eingaben: AblaufEingaben): Ablauf {
  const schritte = [
    turnierSchritt(eingaben),
    anmeldungSchritt(eingaben),
    erfassungSchritt(eingaben),
    anzeigeSchritt(eingaben),
    sicherungSchritt(eingaben),
  ];
  const naechster = naechsterSchritt(eingaben);
  const schritt = schritte.find((x) => x.id === naechster) as AblaufSchritt;
  const sicherung = schritte[4] as AblaufSchritt;
  const nebenbei =
    naechster !== "sicherung" &&
    eingaben.sicherung?.art === "warnung" &&
    eingaben.sicherung.behebbar;
  return {
    schritte,
    naechster,
    aktion: aktionFuer(naechster, eingaben, schritt),
    sicherungAktion: nebenbei ? aktionFuer("sicherung", eingaben, sicherung) : undefined,
  };
}
