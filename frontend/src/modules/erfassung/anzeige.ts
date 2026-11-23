/**
 * Anzeige der Werte, die der Server gerechnet hat: Zahlen in der Schreibweise der Sprache.
 * Hier wird nichts gerechnet, nur formatiert.
 */
import type { TFunction } from "i18next";
import { formatDauer, formatDezimalText, formatHundertstel } from "../../lib/format";
import type { FeldBeschreibung, Formular, Fortschritt, SerienWertung } from "./api";
import { istKommaFeld, kommaBereich } from "./eingabe";

/** Dezimalzahl des Servers („59.50“, „187“) mit gleich vielen Nachkommastellen: „59,50“. */
export function formatWert(wert: string | number | null | undefined): string {
  if (wert === null || wert === undefined || wert === "") return "–";
  return formatDezimalText(wert) ?? String(wert);
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

/** Erlaubter Bereich eines Zahlenfelds in Worten („0 bis 5“, „0 oder 1,0 bis 10,9“); sonst `null`. */
export function feldBereich(feld: FeldBeschreibung, t: TFunction<"erfassung">): string | null {
  if (istKommaFeld(feld)) {
    const b = kommaBereich(feld);
    if (b.max === null) return null;
    return b.null
      ? t("feld.bereich_null", { min: b.min ?? "", max: b.max })
      : t("feld.bereich", { min: b.min ?? "0", max: b.max });
  }
  if (feld.max != null && feld.kind === "integer") {
    return t("feld.bereich", { min: feld.min ?? 0, max: feld.max });
  }
  return null;
}

// --- Vorgaben im Kopf -----------------------------------------------------------------------------

export type VorgabeArt =
  | "probe"
  | "probe_unbegrenzt"
  | "vorbereitung"
  | "wettkampfzeit"
  | "wettkampfzeit_gesamt"
  | "aufgelegt";

export interface Vorgabe {
  art: VorgabeArt;
  /** Fertig geschriebener Wert („15 Min.“, „10“); leer bei „aufgelegt“ und „unbegrenzt“ */
  wert: string;
}

function dauerText(sekunden: string | null | undefined): string | null {
  if (sekunden === null || sekunden === undefined) return null;
  const zahl = Number(sekunden);
  return Number.isFinite(zahl) ? formatDauer(zahl) : null;
}

/** Hat genau einen Abschnitt: Seine Vorgaben stehen im Kopf statt in der Abschnittszeile. */
function einzigerAbschnitt(form: Formular) {
  return form.sections.length === 1 ? form.sections[0] : undefined;
}

/**
 * Vorgaben des Wettbewerbs zur Information im Kopf der Erfassung: Probeschüsse, Vorbereitungs- und
 * Wettkampfzeit, „aufgelegt“. Nur was der Server angibt; geprüft oder erzwungen wird davon nichts.
 * Bei mehreren Abschnitten bleiben deren Angaben an den Abschnitten; hier steht dann nur die
 * gemeinsame Wettkampfzeit. „aufgelegt“ nur, wenn jede Position ausschließlich aufgelegt ist.
 */
export function vorgaben(form: Formular): Vorgabe[] {
  const liste: Vorgabe[] = [];
  const abschnitt = einzigerAbschnitt(form);
  if (abschnitt) {
    if (abschnitt.sighters === "unbegrenzt") liste.push({ art: "probe_unbegrenzt", wert: "" });
    else if (abschnitt.sighters != null) {
      liste.push({ art: "probe", wert: String(abschnitt.sighters) });
    }
    const vorbereitung = dauerText(abschnitt.preparation_time_s);
    if (vorbereitung) liste.push({ art: "vorbereitung", wert: vorbereitung });
    const wettkampf = dauerText(abschnitt.competition_time_s);
    if (wettkampf) liste.push({ art: "wettkampfzeit", wert: wettkampf });
  }
  const gesamt = dauerText(form.competition_time_total_s);
  if (gesamt) liste.push({ art: "wettkampfzeit_gesamt", wert: gesamt });
  const anschlaege = form.sections.flatMap((a) =>
    a.series.flatMap((serie) => serie.position?.stances ?? []),
  );
  if (anschlaege.length > 0 && anschlaege.every((anschlag) => anschlag.aufgelegt === true)) {
    liste.push({ art: "aufgelegt", wert: "" });
  }
  return liste;
}

/**
 * Hinweise eines Abschnitts ohne die, die schon als Vorgabe im Kopf stehen (gleiche Angabe nicht
 * zweimal). Erkannt am Wortlaut des Servers, nur wenn die Angabe auch als eigenes Feld kommt;
 * bei mehreren Abschnitten bleibt alles stehen.
 */
export function abschnittsHinweise(form: Formular, abschnittId: string): string[] {
  const abschnitt = form.sections.find((a) => a.id === abschnittId);
  if (!abschnitt) return [];
  if (einzigerAbschnitt(form) !== abschnitt) return abschnitt.hints;
  return abschnitt.hints.filter((hinweis) => {
    if (abschnitt.competition_time_s != null && hinweis.startsWith("Wettkampfzeit ")) return false;
    if (abschnitt.preparation_time_s != null && hinweis.startsWith("Vorbereitung und Probe "))
      return false;
    if (
      abschnitt.sighters != null &&
      /^(\d+ Probeschuss|\d+ Probeschüsse|Probeschüsse unbegrenzt)$/.test(hinweis)
    )
      return false;
    return true;
  });
}
