import { ApiFehler } from "../../api/client";
import { fehlertext } from "./api";

/** Bekannte Gründe, warum der Server eine ganze Datei ablehnt. */
export type DateiFehlerArt =
  | "kodierung"
  | "spalte_unbekannt"
  | "spalte_doppelt"
  | "name_fehlt"
  | "leer"
  | "kein_csv"
  | "sonstig";

export interface DateiFehler {
  art: DateiFehlerArt;
  /** Betroffene Spalte, falls der Server eine nennt */
  spalte?: string;
  /** Satz des Servers; wird nur gezeigt, wenn der Grund nicht erkannt wurde */
  meldung?: string;
}

/**
 * Ordnet die Ablehnung einer Import-Datei einem Grund zu, damit die Seite Klartext und eine
 * Abhilfe zeigen kann. `null`, wenn es kein Fehler der Datei ist (z. B. Netz weg, Server-Fehler):
 * Dann hilft „Erneut versuchen“.
 */
export function ablehnungsgrund(fehler: unknown): DateiFehler | null {
  if (!(fehler instanceof ApiFehler) || fehler.art !== "anfrage") return null;
  const meldung = fehlertext(fehler) ?? "";
  if (/UTF-8|kodiert|nicht lesen lassen/i.test(meldung)) return { art: "kodierung" };
  const unbekannt = /Spalte „([^“]+)“ ist unbekannt/.exec(meldung);
  if (unbekannt) return { art: "spalte_unbekannt", spalte: unbekannt[1] };
  const doppelt = /Spalte „([^“]+)“ kommt doppelt vor/.exec(meldung);
  if (doppelt) return { art: "spalte_doppelt", spalte: doppelt[1] };
  if (/braucht eine Spalte/.test(meldung)) return { art: "name_fehlt" };
  if (/Datei ist leer/.test(meldung)) return { art: "leer" };
  if (/kein gültiges CSV/.test(meldung)) return { art: "kein_csv" };
  return { art: "sonstig", meldung: meldung || undefined };
}
