import type { Abschnitt, Variante } from "../../api/typen";
import i18n, { aktiveSprache } from "../../i18n";
import { formatDatum, formatDauer, formatZahl } from "../../lib/format";
import type { Turnier, Wettbewerb } from "./typen";

/** Kurze Beschreibung eines Abschnitts: „4 Serien · max. 6 Schuss · 5 Ziele · max. 1 Min.“ */
export function abschnittKurz(abschnitt: Abschnitt, sprache: string = aktiveSprache()): string {
  const t = i18n.getFixedT(sprache, "turnier", "klartext");
  const dauer = (sekunden: number) => formatDauer(sekunden, sprache);
  const teile = [t("serien", { count: abschnitt.serien })];
  if (abschnitt.schuss_je_serie) teile.push(t("schuss", { count: abschnitt.schuss_je_serie }));
  if (abschnitt.max_schuss_je_serie) {
    teile.push(t("max_schuss", { count: abschnitt.max_schuss_je_serie }));
  }
  if (abschnitt.ziele_je_serie) teile.push(t("ziele", { count: abschnitt.ziele_je_serie }));
  if (abschnitt.zeit_je_serie_s) teile.push(t("zeit", { dauer: dauer(abschnitt.zeit_je_serie_s) }));
  if (abschnitt.zeiten_s) {
    teile.push(
      t("zeiten", {
        liste: abschnitt.zeiten_s.map((wert) => formatZahl(wert, {}, sprache)).join(" / "),
      }),
    );
  }
  if (abschnitt.max_zeit_je_serie_s) {
    teile.push(t("max_zeit", { dauer: dauer(abschnitt.max_zeit_je_serie_s) }));
  }
  if (abschnitt.serien_gewertet && abschnitt.serien_gewertet < abschnitt.serien) {
    teile.push(t("gewertet", { count: abschnitt.serien_gewertet }));
  }
  if (abschnitt.trefferaufnahme_nach && abschnitt.trefferaufnahme_nach.length > 0) {
    teile.push(
      t("trefferaufnahme", {
        liste: abschnitt.trefferaufnahme_nach.map((nr) => formatZahl(nr, {}, sprache)).join(", "),
      }),
    );
  }
  return teile.join(" · ");
}

/** Ganzer Ablauf in einer Zeile; bei mehreren Abschnitten mit Namen. */
export function ablaufKurz(variante: Variante, sprache: string = aktiveSprache()): string {
  if (variante.abschnitte.length === 1) {
    return abschnittKurz(variante.abschnitte[0] as Abschnitt, sprache);
  }
  return variante.abschnitte
    .map((abschnitt) => `${abschnitt.name}: ${abschnittKurz(abschnitt, sprache)}`)
    .join(" – ");
}

/** Planung in Klartext: „Zeitplan · 12 Min. je Durchgang“ oder „Reihenfolge“. */
export function planungKurz(wettbewerb: Wettbewerb, sprache: string = aktiveSprache()): string {
  const t = i18n.getFixedT(sprache, "turnier", "klartext");
  if (wettbewerb.planning === "queue") return t("planung_reihenfolge");
  return wettbewerb.heat_minutes
    ? t("planung_zeitplan_dauer", { minuten: formatZahl(wettbewerb.heat_minutes, {}, sprache) })
    : t("planung_zeitplan");
}

/** Mehrfachstart in Klartext: „1 Start“ oder „bis 3 Starts, bestes zählt“. */
export function startsKurz(wettbewerb: Wettbewerb, sprache: string = aktiveSprache()): string {
  const t = i18n.getFixedT(sprache, "turnier", "klartext");
  if (!wettbewerb.multi_start) return t("ein_start");
  return t("mehrfach", {
    anzahl: formatZahl(wettbewerb.max_starts, {}, sprache),
    regel: t(`regel.${wettbewerb.multi_start_rule}`),
  });
}

/** Zeitraum „21.11.2026“ oder „21.11.2026 – 22.11.2026“. */
export function zeitraum(
  turnier: Pick<Turnier, "date_from" | "date_to">,
  sprache: string = aktiveSprache(),
): string {
  const von = formatDatum(turnier.date_from, sprache);
  return turnier.date_to && turnier.date_to !== turnier.date_from
    ? `${von} – ${formatDatum(turnier.date_to, sprache)}`
    : von;
}
