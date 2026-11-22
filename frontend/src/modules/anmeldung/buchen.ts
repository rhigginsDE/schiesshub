import type { Wettbewerb } from "../turnier/typen";
import {
  type Anmeldung,
  type AnmeldungAenderung,
  anmelden,
  anmeldungAendern,
  naechsterPlatzLaden,
  type Start,
  startsBuchen,
} from "./api";

/** Gewählter Platz im Zeitplan (Durchgang und Bahn). */
export interface Platz {
  durchgangId: string;
  bahn: number;
}

export interface BuchungsZeile {
  wettbewerb: Pick<Wettbewerb, "id" | "planning" | "range_id">;
  anzahl: number;
  /** Nur Zeitplan: Platz für den ersten neuen Start; ohne Angabe der Vorschlag des Servers */
  platz?: Platz | null;
}

export interface BuchungsAuftrag {
  turnierId: string;
  /** Vorhandene Anmeldung; fehlt sie, wird die Person zuerst angemeldet */
  anmeldung: Anmeldung | null;
  personId: string;
  klasseId: string;
  /** Nur bei neuer Anmeldung: eigene Startnummer, sonst vergibt der Server die nächste freie */
  startnummer: number | null;
  /** Nur bei vorhandener Anmeldung: geänderte Klasse oder Startnummer */
  aenderung?: AnmeldungAenderung;
  zeilen: readonly BuchungsZeile[];
}

export interface BuchungsErgebnis {
  anmeldung: Anmeldung;
  neu: boolean;
  starts: Start[];
}

/** Fehler eines Schritts. Was davor gelang, bleibt gebucht und steht in `anmeldung`/`gebucht`. */
export class BuchungsFehler extends Error {
  readonly ursache: unknown;
  readonly schritt: "anmeldung" | "start";
  readonly wettbewerbId?: string;
  readonly anmeldung: Anmeldung | null;
  readonly gebucht: Start[];

  constructor(
    ursache: unknown,
    schritt: "anmeldung" | "start",
    anmeldung: Anmeldung | null,
    gebucht: Start[],
    wettbewerbId?: string,
  ) {
    super(ursache instanceof Error ? ursache.message : String(ursache));
    this.name = "BuchungsFehler";
    this.ursache = ursache;
    this.schritt = schritt;
    this.anmeldung = anmeldung;
    this.gebucht = gebucht;
    this.wettbewerbId = wettbewerbId;
  }
}

/**
 * Meldet an (falls nötig), übernimmt Änderungen an Klasse/Startnummer und bucht die Starts.
 * Reihenfolge-Wettbewerbe: alle Starts auf einmal. Zeitplan: einzeln, jeweils auf den gewählten
 * bzw. vom Server vorgeschlagenen nächsten freien Platz; gibt es keinen, ohne Platz (die
 * Standaufsicht plant ihn ein).
 */
export async function buchen(auftrag: BuchungsAuftrag): Promise<BuchungsErgebnis> {
  const { turnierId } = auftrag;
  let anmeldung = auftrag.anmeldung;
  const neu = anmeldung === null;
  const gebucht: Start[] = [];

  try {
    if (anmeldung === null) {
      anmeldung = await anmelden(turnierId, {
        person_id: auftrag.personId,
        class_id: auftrag.klasseId,
        ...(auftrag.startnummer === null ? {} : { start_number: auftrag.startnummer }),
      });
    } else if (auftrag.aenderung && Object.keys(auftrag.aenderung).length > 0) {
      anmeldung = await anmeldungAendern(turnierId, anmeldung.id, auftrag.aenderung);
    }
  } catch (fehler) {
    throw new BuchungsFehler(fehler, "anmeldung", anmeldung, gebucht);
  }

  const id = anmeldung.id;
  for (const zeile of auftrag.zeilen) {
    if (zeile.anzahl <= 0) continue;
    const { wettbewerb } = zeile;
    try {
      if (wettbewerb.planning === "schedule" && wettbewerb.range_id) {
        let offen = zeile.anzahl;
        let platz: Platz | null | undefined = zeile.platz;
        while (offen > 0) {
          if (!platz) {
            const vorschlag = await naechsterPlatzLaden(turnierId, wettbewerb.id, id);
            platz = vorschlag ? { durchgangId: vorschlag.heat.id, bahn: vorschlag.lane } : null;
          }
          if (!platz) {
            // Kein freier Durchgang mehr: die übrigen Starts ohne Platz buchen.
            gebucht.push(
              ...(await startsBuchen(turnierId, id, {
                competition_id: wettbewerb.id,
                count: offen,
              })),
            );
            break;
          }
          gebucht.push(
            ...(await startsBuchen(turnierId, id, {
              competition_id: wettbewerb.id,
              count: 1,
              heat_id: platz.durchgangId,
              lane: platz.bahn,
            })),
          );
          offen -= 1;
          platz = null;
        }
      } else {
        gebucht.push(
          ...(await startsBuchen(turnierId, id, {
            competition_id: wettbewerb.id,
            count: zeile.anzahl,
          })),
        );
      }
    } catch (fehler) {
      throw new BuchungsFehler(fehler, "start", anmeldung, gebucht, wettbewerb.id);
    }
  }
  return { anmeldung, neu, starts: gebucht };
}
