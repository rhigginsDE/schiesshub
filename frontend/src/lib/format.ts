import i18n, { aktiveSprache } from "../i18n";

/**
 * Zahlen, Zeiten und Datumsangaben in der Schreibweise der aktiven Sprache (über Intl).
 * Deutsch: Dezimalkomma, Tausenderpunkt. In der Oberfläche zusätzlich die CSS-Klasse `num`
 * (tabular-nums) verwenden, damit Ziffern gleich breit sind.
 */

export interface ZahlOptionen {
  /** Feste Zahl an Nachkommastellen, z. B. 2 für „6,00“. */
  nachkommastellen?: number;
  /** Höchstzahl an Nachkommastellen, wenn nicht fest (Standard 3). */
  maxNachkommastellen?: number;
}

const zahlFormate = new Map<string, Intl.NumberFormat>();

function zahlFormat(sprache: string, optionen: ZahlOptionen): Intl.NumberFormat {
  const { nachkommastellen, maxNachkommastellen = 3 } = optionen;
  const schluessel = `${sprache}|${nachkommastellen ?? ""}|${maxNachkommastellen}`;
  let format = zahlFormate.get(schluessel);
  if (!format) {
    format = new Intl.NumberFormat(sprache, {
      minimumFractionDigits: nachkommastellen ?? 0,
      maximumFractionDigits: nachkommastellen ?? maxNachkommastellen,
    });
    zahlFormate.set(schluessel, format);
  }
  return format;
}

/** `1234.5` → „1.234,5“ (de). */
export function formatZahl(
  wert: number,
  optionen: ZahlOptionen = {},
  sprache: string = aktiveSprache(),
): string {
  return zahlFormat(sprache, optionen).format(wert);
}

/** Feste Nachkommastellen: `formatDezimal(6, 2)` → „6,00“ (de). */
export function formatDezimal(
  wert: number,
  nachkommastellen: number,
  sprache: string = aktiveSprache(),
): string {
  return formatZahl(wert, { nachkommastellen }, sprache);
}

/** Zeiten kommen vom Server in Hundertstelsekunden: `1234` → „12,34“ (de). */
export function formatHundertstel(hundertstel: number, sprache: string = aktiveSprache()): string {
  return formatDezimal(hundertstel / 100, 2, sprache);
}

/** Sekunden mit Einheit: `10` → „10 s“, `2.5` → „2,5 s“ (de). */
export function formatSekunden(sekunden: number, sprache: string = aktiveSprache()): string {
  return i18n.t("allgemein:einheit.sekunden", {
    wert: formatZahl(sekunden, {}, sprache),
    lng: sprache,
  });
}

/** Dauer für Regelangaben: volle Minuten als „5 Min.“, sonst Sekunden („90 s“). */
export function formatDauer(sekunden: number, sprache: string = aktiveSprache()): string {
  if (sekunden >= 60 && sekunden % 60 === 0) {
    return i18n.t("allgemein:einheit.minuten", {
      wert: formatZahl(sekunden / 60, {}, sprache),
      lng: sprache,
    });
  }
  return formatSekunden(sekunden, sprache);
}

/** ISO-Datum (`2026-06-30`) oder Zeitstempel → „30.06.2026“ (de). Unlesbare Werte bleiben unverändert. */
export function formatDatum(wert: string | Date, sprache: string = aktiveSprache()): string {
  const nurDatum = typeof wert === "string" && /^\d{4}-\d{2}-\d{2}$/.test(wert);
  const datum = typeof wert === "string" ? new Date(nurDatum ? `${wert}T00:00:00` : wert) : wert;
  if (Number.isNaN(datum.getTime())) return String(wert);
  return new Intl.DateTimeFormat(sprache, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(datum);
}

/** Uhrzeit „10:42“. */
export function formatUhrzeit(datum: Date, sprache: string = aktiveSprache()): string {
  return new Intl.DateTimeFormat(sprache, { hour: "2-digit", minute: "2-digit" }).format(datum);
}
