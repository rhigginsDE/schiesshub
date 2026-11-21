import { aktiveSprache } from "../i18n";

/**
 * Geldbeträge: Die API rechnet in Cent (Integer), die Oberfläche zeigt und nimmt Euro mit
 * Dezimalkomma. Beide Richtungen stehen hier, damit es jede Umrechnung genau einmal gibt.
 */

/** `600` → „6,00 €“ (de). Unbekannte Währungskürzel fallen auf das Kürzel zurück. */
export function formatGeld(
  cent: number,
  waehrung = "EUR",
  sprache: string = aktiveSprache(),
): string {
  try {
    return new Intl.NumberFormat(sprache, { style: "currency", currency: waehrung }).format(
      cent / 100,
    );
  } catch {
    return `${formatBetrag(cent, sprache)} ${waehrung}`;
  }
}

/** `600` → „6,00“ (de), ohne Währungszeichen; für Eingabefelder. */
export function formatBetrag(cent: number, sprache: string = aktiveSprache()): string {
  return new Intl.NumberFormat(sprache, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: false,
  }).format(cent / 100);
}

/** Währungszeichen zum Kürzel: `EUR` → „€“. */
export function waehrungsZeichen(waehrung = "EUR", sprache: string = aktiveSprache()): string {
  try {
    const teil = new Intl.NumberFormat(sprache, { style: "currency", currency: waehrung })
      .formatToParts(0)
      .find((eintrag) => eintrag.type === "currency");
    return teil?.value ?? waehrung;
  } catch {
    return waehrung;
  }
}

/**
 * Euro-Text in Cent. Nimmt „6“, „6,5“, „6,50“, „1.234,50“ und auch „6.50“ (Punkt als Dezimaltrenner,
 * wenn danach höchstens zwei Ziffern stehen). Leerer Text ergibt `null`, Unlesbares `undefined`.
 */
export function leseBetrag(text: string): number | null | undefined {
  const sauber = text.replace(/[\s€]/g, "").replace(/EUR$/i, "");
  if (sauber === "") return null;
  let normal: string;
  if (sauber.includes(",")) {
    // Komma ist Dezimaltrenner, Punkte davor sind Tausendertrenner.
    const [ganz, ...rest] = sauber.split(",");
    if (rest.length !== 1 || !/^\d{1,3}(\.\d{3})*$|^\d+$/.test(ganz ?? "")) return undefined;
    normal = `${(ganz ?? "").replaceAll(".", "")}.${rest[0]}`;
  } else if (/^\d+\.\d{1,2}$/.test(sauber)) {
    normal = sauber;
  } else if (/^\d{1,3}(\.\d{3})+$/.test(sauber)) {
    normal = sauber.replaceAll(".", "");
  } else {
    normal = sauber;
  }
  if (!/^\d+(\.\d{0,2})?$/.test(normal)) return undefined;
  return Math.round(Number.parseFloat(normal) * 100);
}
