/**
 * Anzeige der Werte, die der Server gerechnet hat: Zahlen in der Schreibweise der Sprache.
 * Hier wird nichts gerechnet, nur formatiert.
 */
import type { TFunction } from "i18next";
import { formatDezimal, formatHundertstel } from "../../lib/format";
import type { Fortschritt, SerienWertung } from "./api";

/** Dezimalzahl des Servers („59.50“, „187“) mit gleich vielen Nachkommastellen: „59,50“. */
export function formatWert(wert: string | number | null | undefined): string {
  if (wert === null || wert === undefined || wert === "") return "–";
  const text = String(wert);
  const zahl = Number(text);
  if (!Number.isFinite(zahl)) return text;
  const stellen = text.includes(".") ? (text.split(".")[1]?.length ?? 0) : 0;
  return formatDezimal(zahl, stellen);
}

/** Zeit in Hundertstelsekunden: „12,84“ (ohne Einheit). */
export function formatZeit(hundertstel: number | null | undefined): string {
  return hundertstel === null || hundertstel === undefined ? "–" : formatHundertstel(hundertstel);
}

/** „16 von 20 Schuss · 1 von 2 Serien“: nur, was diese Wertung zählt. */
export function fortschrittText(fortschritt: Fortschritt, t: TFunction<"erfassung">): string {
  const teile: string[] = [];
  if (fortschritt.shots_expected > 0) {
    teile.push(
      t("fortschritt.schuss", {
        anzahl: fortschritt.shots_entered,
        count: fortschritt.shots_expected,
      }),
    );
  }
  if (fortschritt.series_expected > 0 && fortschritt.shots_expected === 0) {
    teile.push(
      t("fortschritt.serien", {
        anzahl: fortschritt.series_complete,
        count: fortschritt.series_expected,
      }),
    );
  }
  if (fortschritt.section_times_expected > 0) {
    teile.push(
      t("fortschritt.gesamtzeiten", {
        anzahl: fortschritt.section_times_entered,
        count: fortschritt.section_times_expected,
      }),
    );
  }
  return teile.join(" · ");
}

/** Was noch fehlt, als kurzer Hinweis unter dem Abschluss-Knopf. */
export function restText(fortschritt: Fortschritt, t: TFunction<"erfassung">): string | null {
  const schuss = fortschritt.shots_expected - fortschritt.shots_entered;
  if (schuss > 0) return t("rest.schuss", { count: schuss });
  const serien = fortschritt.series_expected - fortschritt.series_complete;
  if (serien > 0) return t("rest.serien", { count: serien });
  const zeiten = fortschritt.section_times_expected - fortschritt.section_times_entered;
  if (zeiten > 0) return t("rest.gesamtzeiten", { count: zeiten });
  return null;
}

export interface SerienAnzeige {
  /** Hauptwert der Serie (Ringe oder Zeit mit Zuschlag) */
  wert: string;
  einheit: "ringe" | "sekunden" | null;
  /** Zusatz, z. B. „12,84 + 10,00“ */
  zusatz: string | null;
}

/** Ergebnis einer Serie, wie der Server es liefert. */
export function serienAnzeige(
  serie: SerienWertung | undefined,
  t: TFunction<"erfassung">,
): SerienAnzeige {
  // Noch nichts erfasst: kein „0,00 s“, das wie ein Ergebnis aussieht.
  if (!serie || serie.captured === false) return { wert: "–", einheit: null, zusatz: null };
  if (serie.total_cs !== null) {
    const zusatz =
      serie.penalty_cs && serie.time_cs !== null
        ? t("serie.zeit_plus", {
            zeit: formatZeit(serie.time_cs),
            zuschlag: formatZeit(serie.penalty_cs),
          })
        : null;
    const ringe =
      serie.rings !== null ? t("serie.ringe_kurz", { wert: formatWert(serie.rings) }) : null;
    return {
      wert: formatZeit(serie.total_cs),
      einheit: "sekunden",
      zusatz: [ringe, zusatz].filter(Boolean).join(" · ") || null,
    };
  }
  if (serie.rings !== null) {
    const zusatz =
      serie.time_cs !== null ? t("serie.zeit", { zeit: formatZeit(serie.time_cs) }) : null;
    return { wert: formatWert(serie.rings), einheit: "ringe", zusatz };
  }
  if (serie.time_cs !== null) {
    return { wert: formatZeit(serie.time_cs), einheit: "sekunden", zusatz: null };
  }
  return { wert: "–", einheit: null, zusatz: null };
}
