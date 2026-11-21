import type { Abschnitt, Variante } from "../../api/typen";
import i18n, { aktiveSprache } from "../../i18n";
import { formatSekunden, formatZahl } from "../../lib/format";

/** Felder, in denen sich Parcours-Varianten unterscheiden dürfen, ohne dass sich der Ablauf ändert. */
const ZEITFELDER = new Set(["sollzeit_s", "max_gesamtzeit_s"]);

function ohneZeiten(variante: Variante): string {
  return JSON.stringify(
    variante.abschnitte.map((abschnitt) =>
      Object.fromEntries(Object.entries(abschnitt).filter(([feld]) => !ZEITFELDER.has(feld))),
    ),
  );
}

/**
 * `true`, wenn sich die Varianten nur in Sollzeit und Abbruchzeit unterscheiden (Mehrdistanz).
 * Dann zeigt der Aushang einen Ablauf und eine Sollzeit-Tabelle statt einer Variantenauswahl.
 */
export function nurZeitVarianten(varianten: Variante[]): boolean {
  const [kopf] = varianten;
  if (!kopf || varianten.length < 2) return false;
  const erste = ohneZeiten(kopf);
  return varianten.every((variante) => ohneZeiten(variante) === erste);
}

export interface SollzeitZeile {
  variante: string;
  sollzeit: string;
  abbruch: string | null;
}

/** Sollzeit und Abbruchzeit je Variante für einen Abschnitt (Index), sofern vorhanden. */
export function sollzeitTabelle(
  varianten: Variante[],
  abschnittIndex: number,
  sprache: string = aktiveSprache(),
): SollzeitZeile[] {
  const zeilen: SollzeitZeile[] = [];
  for (const variante of varianten) {
    const abschnitt = variante.abschnitte[abschnittIndex];
    if (abschnitt?.sollzeit_s == null) continue;
    zeilen.push({
      variante: variante.name,
      sollzeit: formatSekunden(abschnitt.sollzeit_s, sprache),
      abbruch:
        abschnitt.max_gesamtzeit_s != null
          ? formatSekunden(abschnitt.max_gesamtzeit_s, sprache)
          : null,
    });
  }
  return zeilen;
}

export interface ZeitZeile {
  fall: string;
  zeit: string;
}

/**
 * Wie die Zeit einer Serie entsteht (Fallscheibe), abgeleitet aus den Katalogfeldern:
 * Zuschlag je stehender Scheibe, Zeit bei Abbruch, Zuschlag bei Störung, max. Schuss und Zeitlimit.
 * Leer, wenn der Abschnitt keinen Zuschlag kennt.
 */
export function zeitTabelle(abschnitt: Abschnitt, sprache: string = aktiveSprache()): ZeitZeile[] {
  const zuschlag = abschnitt.zuschlag_je_stehender_scheibe_s;
  if (zuschlag == null) return [];
  const t = i18n.getFixedT(sprache, "katalog", "aushang.zeit");
  const dauer = (s: number) => formatSekunden(s, sprache);
  const gemessen = t("gemessen");
  const abbruch = abschnitt.zeit_bei_abbruch_s;
  const zeilen: ZeitZeile[] = [{ fall: t("alle_gefallen"), zeit: gemessen }];

  if (abschnitt.max_schuss_je_serie != null) {
    zeilen.push({
      fall: t("max_schuss", { count: abschnitt.max_schuss_je_serie }),
      zeit: t("plus_zuschlag", { basis: gemessen, zuschlag: dauer(zuschlag) }),
    });
  }
  if (abbruch != null) {
    const mitZuschlag = t("plus_zuschlag", { basis: dauer(abbruch), zuschlag: dauer(zuschlag) });
    if (abschnitt.max_zeit_je_serie_s != null) {
      zeilen.push({
        fall: t("zeitlimit", { limit: dauer(abschnitt.max_zeit_je_serie_s) }),
        zeit: mitZuschlag,
      });
    }
    zeilen.push({ fall: t("abbruch_schuetze"), zeit: mitZuschlag });
    if (abschnitt.zuschlag_stoerung_vor_erstem_schuss_s != null) {
      zeilen.push({
        fall: t("stoerung"),
        zeit: t("plus", {
          basis: dauer(abbruch),
          zuschlag: dauer(abschnitt.zuschlag_stoerung_vor_erstem_schuss_s),
        }),
      });
    }
  }
  return zeilen;
}

/** Hand-Abzeichen, die in einer Variante vorkommen (für die Legende). */
export function verwendeteHaende(variante: Variante): string[] {
  const haende = new Set<string>();
  for (const abschnitt of variante.abschnitte) {
    for (const position of abschnitt.positionen ?? []) {
      for (const anschlag of position.anschlaege) {
        if (anschlag.hand) haende.add(anschlag.hand);
      }
    }
  }
  return ["beidhaendig", "starke_hand", "schwache_hand", "einhaendig"].filter((h) => haende.has(h));
}

/** Zahl ohne Nachkommastellen, wie sie im Kopf steht. */
export function ganzzahl(wert: number, sprache: string = aktiveSprache()): string {
  return formatZahl(wert, {}, sprache);
}
