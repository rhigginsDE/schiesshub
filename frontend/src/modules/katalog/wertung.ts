import type { Wertung } from "../../api/typen";
import i18n, { aktiveSprache } from "../../i18n";
import { formatZahl } from "../../lib/format";

/** Wertung, wie sie die API liefert; unbekannte Modelle und Regeln werden mit ihrem Schlüssel gezeigt. */
export type WertungOffen = Omit<Wertung, "modell" | "rangfolge" | "zeit_rundung"> & {
  modell: string;
  rangfolge: string;
  zeit_rundung?: string | null;
};

export interface WertungInKlartext {
  /** Name des Modells, z. B. „Zeit plus Zuschläge“ */
  name: string;
  /** Vollständige Sätze: was gewertet wird, wer gewinnt, Sonderregeln */
  saetze: string[];
  /** Kriterien bei Gleichstand in ihrer Reihenfolge; `null`, wenn das Regelwerk keine nennt */
  gleichstand: string[] | null;
  /** Formeller Begriff für den Gleichstand: Ringgleichheit oder Treffergleichheit (Entscheidung 23.11.) */
  gleichheit: Gleichheit;
}

/** DSB: „Ergebnisgleichheit“ (SpO 0.12), BDS: Ring- oder Treffergleichheit (Entscheidung 23.11.) */
export type Gleichheit = "ringe" | "treffer" | "ergebnis";

/** Nur die Teile des Ablaufs, die über Ringe oder Treffer entscheiden. */
interface AblaufRingwerte {
  varianten: { abschnitte: { ringwerte?: number[] | null }[] }[];
}

/**
 * Treffergleichheit, wenn nach Zeit und Zuschlägen gewertet wird (Fallscheibe) oder jede Wertung
 * nur Treffer zählt (Ringwerte höchstens 1, z. B. Flinte); sonst Ringgleichheit.
 */
function gleichheitAus(
  wertung: WertungOffen,
  ablauf?: AblaufRingwerte,
  verband?: string,
): Gleichheit {
  if (verband === "dsb") return "ergebnis";
  if (wertung.modell === "zeit_plus_zuschlaege") return "treffer";
  const ringwerte = (ablauf?.varianten ?? []).flatMap((variante) =>
    variante.abschnitte.flatMap((abschnitt) => abschnitt.ringwerte ?? []),
  );
  return ringwerte.length > 0 && Math.max(...ringwerte) <= 1 ? "treffer" : "ringe";
}

function modellName(modell: string, sprache: string): string {
  const t = i18n.getFixedT(sprache, "katalog", "wertung.modell");
  return i18n.exists(`katalog:wertung.modell.${modell}.name`, { lng: sprache })
    ? t(`${modell}.name`)
    : t("unbekannt.name", { modell });
}

/** Kurzname eines Wertungsmodells für Listen und Chips. */
export function wertungModellName(modell: string, sprache: string = aktiveSprache()): string {
  return modellName(modell, sprache);
}

/** Übersetzt die Wertungsangaben des Katalogs in Klartext. */
export function beschreibeWertung(
  wertung: WertungOffen,
  sprache: string = aktiveSprache(),
  ablauf?: AblaufRingwerte,
  verband?: string,
): WertungInKlartext {
  const t = i18n.getFixedT(sprache, "katalog", "wertung");
  const bekannt = i18n.exists(`katalog:wertung.modell.${wertung.modell}.text`, { lng: sprache });
  const saetze: string[] = [
    bekannt ? t(`modell.${wertung.modell}.text`) : t("modell.unbekannt.text"),
  ];

  if (i18n.exists(`katalog:wertung.rangfolge.${wertung.rangfolge}`, { lng: sprache })) {
    saetze.push(t(`rangfolge.${wertung.rangfolge}`));
  }

  const abzug = wertung.abzug_je_voller_sekunde_ueber_sollzeit;
  if (typeof abzug === "number") {
    saetze.push(t("abzug", { count: abzug, wert: formatZahl(abzug, {}, sprache) }));
  }
  if (typeof wertung.min_teilergebnis === "number") {
    saetze.push(t("min_teilergebnis", { wert: formatZahl(wertung.min_teilergebnis, {}, sprache) }));
  }
  const offen = wertung as WertungOffen & {
    zehntelwertung?: boolean | null;
    stechen_bis_platz?: number | null;
  };
  if (offen.zehntelwertung === true) {
    saetze.push(t("zehntelwertung"));
  }
  if (typeof offen.stechen_bis_platz === "number") {
    saetze.push(
      t(`stechen_bis_platz_${gleichheitAus(wertung, ablauf, verband)}`, {
        wert: formatZahl(offen.stechen_bis_platz, {}, sprache),
      }),
    );
  }
  if (
    wertung.zeit_rundung &&
    i18n.exists(`katalog:wertung.zeit_rundung.${wertung.zeit_rundung}`, { lng: sprache })
  ) {
    saetze.push(t(`zeit_rundung.${wertung.zeit_rundung}`));
  }

  const gleichstand =
    wertung.gleichstand && wertung.gleichstand.length > 0
      ? wertung.gleichstand.map((kriterium) =>
          i18n.exists(`katalog:wertung.gleichstand.kriterium.${kriterium}`, { lng: sprache })
            ? t(`gleichstand.kriterium.${kriterium}`)
            : kriterium.replaceAll("_", " "),
        )
      : null;

  return {
    name: modellName(wertung.modell, sprache),
    saetze,
    gleichstand,
    gleichheit: gleichheitAus(wertung, ablauf, verband),
  };
}
