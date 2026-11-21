import { aktiveSprache } from "../../i18n";
import { formatDatum, formatUhrzeit, formatZahl } from "../../lib/format";

/** „21.11.2026, 22:36“ (de). */
export function formatZeitpunkt(wert: string | Date, sprache: string = aktiveSprache()): string {
  const datum = typeof wert === "string" ? new Date(wert) : wert;
  if (Number.isNaN(datum.getTime())) return String(wert);
  return `${formatDatum(datum, sprache)}, ${formatUhrzeit(datum, sprache)}`;
}

/** Nur die Uhrzeit, wenn der Zeitpunkt heute ist, sonst Datum und Uhrzeit. */
export function formatWann(
  wert: string | Date,
  jetzt: Date = new Date(),
  sprache: string = aktiveSprache(),
): string {
  const datum = typeof wert === "string" ? new Date(wert) : wert;
  if (Number.isNaN(datum.getTime())) return String(wert);
  return datum.toDateString() === jetzt.toDateString()
    ? formatUhrzeit(datum, sprache)
    : formatZeitpunkt(datum, sprache);
}

const EINHEITEN = ["B", "KB", "MB", "GB", "TB"] as const;

/** Dateigröße mit 1024er-Schritten: `56820` → „55,5 KB“ (de). */
export function formatGroesse(bytes: number, sprache: string = aktiveSprache()): string {
  let wert = bytes;
  let stufe = 0;
  while (wert >= 1024 && stufe < EINHEITEN.length - 1) {
    wert /= 1024;
    stufe += 1;
  }
  const stellen = stufe === 0 || wert >= 100 ? 0 : 1;
  return `${formatZahl(wert, { maxNachkommastellen: stellen }, sprache)} ${EINHEITEN[stufe]}`;
}
