import type { Abschnitt, Variante } from "../../api/typen";
import i18n, { aktiveSprache } from "../../i18n";
import { formatDauer, formatZahl } from "../../lib/format";

const TRENNER = " · ";

/** Abschnitt, wie ihn die API liefert; der Katalog darf weitere Felder mitbringen. */
export type AbschnittOffen = Abschnitt & { [weitere: string]: unknown };

/** Felder, die `beschreibeAbschnitt` in Klartext übersetzt oder bewusst nicht zeigt. */
const BEKANNTE_FELDER = new Set([
  "id",
  "name",
  "serien",
  "schuss_je_serie",
  "max_schuss_je_serie",
  "ziele_je_serie",
  "zeit_je_serie_s",
  "zeiten_s",
  "max_zeit_je_serie_s",
  "zeit_wird_gemessen",
  "zuschlag_je_stehender_scheibe_s",
  "distanzen_m",
  "zeit_je_schuss_s",
  "pause_zwischen_schuessen_s",
  "sollzeit_s",
  "max_gesamtzeit_s",
  // als eigene Ablauf-Darstellung gezeigt, nicht als Text
  "positionen",
  "ringwerte",
  "zeit_bei_abbruch_s",
  "zuschlag_stoerung_vor_erstem_schuss_s",
  "serien_gewertet",
  "trefferaufnahme_nach",
  "wettkampfzeit_s",
  "vorbereitung_probe_s",
  "probeschuesse",
  // Eingabeschutz, keine Angabe für Schützen
  "zeit_plausibel_faktor",
  "zeit_plausibel_max_s",
]);

function istZahl(wert: unknown): wert is number {
  return typeof wert === "number" && Number.isFinite(wert);
}

function istZahlenliste(wert: unknown): wert is number[] {
  return Array.isArray(wert) && wert.length > 0 && wert.every(istZahl);
}

/**
 * Übersetzt einen Abschnitt des Ablaufs in kurze Klartext-Teile, z. B.
 * `["4 Serien", "5 Ziele", "max. 6 Schuss", "max. 1 Min.", "+10 s je stehender Scheibe"]`.
 * Felder, die diese Funktion nicht kennt, erscheinen als „feldname: wert“, damit nichts verloren geht.
 */
export function beschreibeAbschnitt(
  abschnitt: AbschnittOffen,
  sprache: string = aktiveSprache(),
): string[] {
  const t = i18n.getFixedT(sprache, "katalog", "ablauf");
  const zahl = (wert: number) => formatZahl(wert, {}, sprache);
  const dauer = (sekunden: number) => formatDauer(sekunden, sprache);
  const liste = (werte: number[]) => werte.map(zahl).join(" / ");
  const teile: string[] = [];

  if (istZahl(abschnitt.serien)) {
    teile.push(t("serien", { count: abschnitt.serien }));
  }
  if (istZahl(abschnitt.schuss_je_serie)) {
    teile.push(t("schuss", { count: abschnitt.schuss_je_serie }));
  }
  if (istZahl(abschnitt.ziele_je_serie)) {
    teile.push(t("ziele", { count: abschnitt.ziele_je_serie }));
  }
  if (istZahl(abschnitt.max_schuss_je_serie)) {
    teile.push(t("max_schuss", { count: abschnitt.max_schuss_je_serie }));
  }
  if (istZahlenliste(abschnitt.distanzen_m)) {
    const meter = i18n.t("allgemein:einheit.meter", {
      wert: liste(abschnitt.distanzen_m),
      lng: sprache,
    });
    teile.push(t("distanzen", { liste: meter }));
  }
  if (istZahl(abschnitt.zeit_je_serie_s)) {
    teile.push(dauer(abschnitt.zeit_je_serie_s));
  }
  if (istZahl(abschnitt.wettkampfzeit_s)) {
    teile.push(t("wettkampfzeit", { dauer: dauer(abschnitt.wettkampfzeit_s) }));
  }
  if (istZahl(abschnitt.vorbereitung_probe_s)) {
    teile.push(t("vorbereitung_probe", { dauer: dauer(abschnitt.vorbereitung_probe_s) }));
  }
  if (abschnitt.probeschuesse === "unbegrenzt") {
    teile.push(t("probeschuesse_unbegrenzt"));
  } else if (abschnitt.probeschuesse === 0) {
    teile.push(t("probeschuesse_keine"));
  } else if (istZahl(abschnitt.probeschuesse)) {
    teile.push(t("probeschuesse", { count: abschnitt.probeschuesse }));
  }
  if (istZahlenliste(abschnitt.zeiten_s)) {
    const sekunden = i18n.t("allgemein:einheit.sekunden", {
      wert: liste(abschnitt.zeiten_s),
      lng: sprache,
    });
    teile.push(t("zeiten", { liste: sekunden }));
  }
  if (istZahl(abschnitt.zeit_je_schuss_s)) {
    teile.push(t("zeit_je_schuss", { dauer: dauer(abschnitt.zeit_je_schuss_s) }));
  }
  if (istZahl(abschnitt.pause_zwischen_schuessen_s)) {
    teile.push(t("pause", { dauer: dauer(abschnitt.pause_zwischen_schuessen_s) }));
  }
  if (istZahl(abschnitt.max_zeit_je_serie_s)) {
    teile.push(t("max_zeit", { dauer: dauer(abschnitt.max_zeit_je_serie_s) }));
  }
  if (istZahl(abschnitt.zuschlag_je_stehender_scheibe_s)) {
    teile.push(t("zuschlag", { dauer: dauer(abschnitt.zuschlag_je_stehender_scheibe_s) }));
  }
  if (istZahl(abschnitt.sollzeit_s)) {
    teile.push(t("sollzeit", { dauer: dauer(abschnitt.sollzeit_s) }));
  }
  if (istZahl(abschnitt.max_gesamtzeit_s)) {
    teile.push(t("max_gesamtzeit", { dauer: dauer(abschnitt.max_gesamtzeit_s) }));
  }
  if (abschnitt.zeit_wird_gemessen === true) {
    teile.push(t("zeit_gemessen"));
  }
  if (istZahlenliste(abschnitt.ringwerte)) {
    teile.push(t("ringwerte", { liste: liste(abschnitt.ringwerte) }));
  }
  if (istZahl(abschnitt.zeit_bei_abbruch_s)) {
    teile.push(t("zeit_bei_abbruch", { dauer: dauer(abschnitt.zeit_bei_abbruch_s) }));
  }
  if (istZahl(abschnitt.zuschlag_stoerung_vor_erstem_schuss_s)) {
    teile.push(
      t("zuschlag_stoerung", { dauer: dauer(abschnitt.zuschlag_stoerung_vor_erstem_schuss_s) }),
    );
  }
  if (istZahl(abschnitt.serien_gewertet)) {
    teile.push(t("serien_gewertet", { count: abschnitt.serien_gewertet }));
  }
  if (istZahlenliste(abschnitt.trefferaufnahme_nach)) {
    teile.push(
      t("trefferaufnahme_nach", {
        count: abschnitt.trefferaufnahme_nach.length,
        liste: abschnitt.trefferaufnahme_nach.map(zahl).join(", "),
      }),
    );
  }

  for (const [feld, wert] of Object.entries(abschnitt)) {
    if (BEKANNTE_FELDER.has(feld) || wert === null || wert === undefined || wert === false) {
      continue;
    }
    const text = istZahl(wert)
      ? zahl(wert)
      : istZahlenliste(wert)
        ? liste(wert)
        : typeof wert === "string"
          ? wert
          : JSON.stringify(wert);
    teile.push(`${feld.replaceAll("_", " ")}: ${text}`);
  }

  return teile;
}

/** Abschnitt als eine Zeile: „4 Serien · 5 Ziele · max. 6 Schuss · …“. */
export function abschnittAlsText(
  abschnitt: AbschnittOffen,
  sprache: string = aktiveSprache(),
): string {
  return beschreibeAbschnitt(abschnitt, sprache).join(TRENNER);
}

/**
 * Gesamtschusszahl einer Variante. `null`, wenn sie nicht feststeht
 * (z. B. Fallscheibe mit „max. … Schuss“).
 */
export function schussGesamt(variante: Variante): number | null {
  let summe = 0;
  for (const abschnitt of variante.abschnitte) {
    if (!istZahl(abschnitt.serien) || !istZahl(abschnitt.schuss_je_serie)) return null;
    summe += abschnitt.serien * abschnitt.schuss_je_serie;
  }
  return variante.abschnitte.length > 0 ? summe : null;
}
