import type { Abschnitt, Variante } from "../../api/typen";
import i18n, { aktiveSprache } from "../../i18n";
import { formatZahl } from "../../lib/format";
import type { Planung } from "./typen";

/**
 * Voreinstellung der Planung aus dem Ablauf – dieselbe Regel wie im Server
 * (`backend/app/modules/turnier/planning.py`): Haben alle Abschnitte eine feste Zeit je Serie oder
 * eine vollständige Zeitliste, gilt der Zeitplan mit der Summe der Serienzeiten (auf volle Minuten
 * aufgerundet) plus Wechselzeit. Sonst gilt die Reihenfolge.
 */
export interface PlanungVorschlag {
  planung: Planung;
  /** Nur bei Zeitplan: Dauer eines Durchgangs einschließlich Wechselzeit */
  durchgangMinuten: number | null;
  /** Reine Schießzeit in Sekunden, falls sie feststeht */
  schiesszeitSekunden: number | null;
  /** Erster Abschnitt ohne feste Zeit (Begründung bei Reihenfolge) */
  ohneZeit: Abschnitt | null;
}

export function abschnittSekunden(abschnitt: Abschnitt): number | null {
  if (abschnitt.zeiten_s) return abschnitt.zeiten_s.reduce((summe, wert) => summe + wert, 0);
  if (typeof abschnitt.zeit_je_serie_s === "number") {
    return abschnitt.serien * abschnitt.zeit_je_serie_s;
  }
  return null;
}

export function planungVorschlag(variante: Variante, wechselMinuten: number): PlanungVorschlag {
  let summe = 0;
  for (const abschnitt of variante.abschnitte) {
    const sekunden = abschnittSekunden(abschnitt);
    if (sekunden === null) {
      return {
        planung: "queue",
        durchgangMinuten: null,
        schiesszeitSekunden: null,
        ohneZeit: abschnitt,
      };
    }
    summe += sekunden;
  }
  return {
    planung: "schedule",
    durchgangMinuten: Math.ceil(summe / 60) + wechselMinuten,
    schiesszeitSekunden: summe,
    ohneZeit: null,
  };
}

/** Ein Satz, warum der Server diese Planung vorschlägt. */
export function planungBegruendung(
  vorschlag: PlanungVorschlag,
  wechselMinuten: number,
  sprache: string = aktiveSprache(),
): string {
  const t = i18n.getFixedT(sprache, "turnier", "planung.begruendung");
  const zahl = (wert: number) => formatZahl(wert, {}, sprache);
  if (vorschlag.planung === "queue") {
    return t("reihenfolge", { abschnitt: vorschlag.ohneZeit?.name ?? "" });
  }
  return t("zeitplan", {
    schiesszeit: zahl(Math.ceil((vorschlag.schiesszeitSekunden ?? 0) / 60)),
    wechsel: zahl(wechselMinuten),
    dauer: zahl(vorschlag.durchgangMinuten ?? 0),
  });
}
