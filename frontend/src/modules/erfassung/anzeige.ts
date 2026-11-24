/**
 * Anzeige der Werte, die der Server gerechnet hat: Zahlen in der Schreibweise der Sprache.
 * Hier wird nichts gerechnet, nur formatiert.
 */
import type { TFunction } from "i18next";
import { formatDezimalText, formatHundertstel } from "../../lib/format";
import type {
  FeldBeschreibung,
  Formular,
  Fortschritt,
  HinweisArt,
  SerieForm,
  SerienWertung,
} from "./api";
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

/**
 * Zählt die Wertung Treffer statt Ringe (Wurfscheibe: ein Wert je Ziel)? Der Server sagt es mit der
 * Einheit („Treffer“, `app.scoring.models.HITS_UNIT`); dann heißt der Serienwert „Treffer“, der
 * Fortschritt zählt Ziele, und Zehner gibt es nicht.
 */
export function zaehltTreffer(einheit: string | null | undefined): boolean {
  return einheit === "Treffer";
}

/**
 * Gleichstandskriterium in Worten, z. B. für „Für einen Gleichstand fehlt: …“. Der Server liefert
 * `tie_breakers_missing` nur als IDs; der Klartext des Servers steht in `scoring/kriterien.yaml`
 * und ist hier für die Kriterien nachgeschrieben, die überhaupt fehlen können. Eine unbekannte ID
 * wird wie beim Server lesbar gemacht („abstand_zum_rand“ → „abstand zum rand“).
 */
export function kriteriumText(kriterium: string, t: TFunction<"erfassung">): string {
  return t(`gesamt.gleichstand.${kriterium}`, {
    defaultValue: kriterium.replaceAll("_", " ").trim(),
  });
}

/** „16 von 20 Schuss · 1 von 2 Serien“: nur, was diese Wertung zählt. `treffer`: Ziele statt Schuss. */
export function fortschrittText(
  fortschritt: Fortschritt,
  t: TFunction<"erfassung">,
  treffer = false,
): string {
  const teile: string[] = [];
  if (fortschritt.shots_expected > 0) {
    teile.push(
      t(treffer ? "fortschritt.ziele" : "fortschritt.schuss", {
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
export function restText(
  fortschritt: Fortschritt,
  t: TFunction<"erfassung">,
  treffer = false,
): string | null {
  const schuss = fortschritt.shots_expected - fortschritt.shots_entered;
  if (schuss > 0) return t(treffer ? "rest.ziele" : "rest.schuss", { count: schuss });
  const serien = fortschritt.series_expected - fortschritt.series_complete;
  if (serien > 0) return t("rest.serien", { count: serien });
  const zeiten = fortschritt.section_times_expected - fortschritt.section_times_entered;
  if (zeiten > 0) return t("rest.gesamtzeiten", { count: zeiten });
  return null;
}

/**
 * Wort für Ringwerte (Serienwert, Höchstwert im Kopf): bei Trefferzählung die Einheit des Servers
 * („Treffer“), sonst „Ringe“ – auch bei Modellen mit anderer Gesamteinheit („Punkte“), deren
 * Serien Ringe zählen.
 */
export function ringEinheit(einheit: string | null | undefined, t: TFunction<"erfassung">): string {
  return einheit && zaehltTreffer(einheit) ? einheit : t("einheit.ringe");
}

export interface SerienAnzeige {
  /** Hauptwert der Serie (Ringe oder Zeit mit Zuschlag) */
  wert: string;
  /** Einheit zum Wert, fertig geschrieben („Ringe“, „Treffer“, „s“) */
  einheit: string | null;
  /** Zusatz, z. B. „12,84 + 10,00“ */
  zusatz: string | null;
}

/** Ergebnis einer Serie, wie der Server es liefert. `einheit`: Einheit der Wertung (Server). */
export function serienAnzeige(
  serie: SerienWertung | undefined,
  t: TFunction<"erfassung">,
  einheit?: string | null,
): SerienAnzeige {
  const sekunden = t("einheit.sekunden");
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
      einheit: sekunden,
      zusatz: [ringe, zusatz].filter(Boolean).join(" · ") || null,
    };
  }
  if (serie.rings !== null) {
    const zusatz =
      serie.time_cs !== null ? t("serie.zeit", { zeit: formatZeit(serie.time_cs) }) : null;
    return { wert: formatWert(serie.rings), einheit: ringEinheit(einheit, t), zusatz };
  }
  if (serie.time_cs !== null) {
    return { wert: formatZeit(serie.time_cs), einheit: sekunden, zusatz: null };
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

/**
 * Arten der Abschnitts-Hinweise, die bei genau einem Abschnitt ruhig im Kopf stehen (in dieser
 * Reihenfolge) statt in der Abschnittszeile. Der Server nennt die Art (`HintItem.kind`); der Text
 * kommt fertig von ihm.
 */
const KOPF_ARTEN: readonly HinweisArt[] = ["sighters", "preparation_time", "competition_time"];

/** Eine Vorgabe im Kopf: ein Hinweis des Servers oder „aufgelegt“ (Angabe des Abschnitts). */
export type Vorgabe = { art: "hinweis"; kind: HinweisArt; text: string } | { art: "aufgelegt" };

/** Hat genau einen Abschnitt: Seine Vorgaben stehen im Kopf statt in der Abschnittszeile. */
function einzigerAbschnitt(form: Formular) {
  return form.sections.length === 1 ? form.sections[0] : undefined;
}

/** Jeder Abschnitt ist aufgelegt (`SectionForm.aufgelegt`): „aufgelegt“ gilt für den Wettbewerb. */
function alleAufgelegt(form: Formular): boolean {
  return form.sections.length > 0 && form.sections.every((abschnitt) => abschnitt.aufgelegt);
}

/**
 * Vorgaben des Wettbewerbs zur Information im Kopf der Erfassung: Probeschüsse, Vorbereitung und
 * Wettkampfzeit (Hinweise des Servers nach Art), „aufgelegt“. Nur was der Server angibt; geprüft
 * oder erzwungen wird davon nichts. Bei mehreren Abschnitten bleiben deren Angaben an den
 * Abschnitten; die gemeinsame Wettkampfzeit steht in den Notizen des Servers.
 */
export function vorgaben(form: Formular): Vorgabe[] {
  const liste: Vorgabe[] = [];
  const abschnitt = einzigerAbschnitt(form);
  if (abschnitt) {
    for (const kind of KOPF_ARTEN) {
      for (const hinweis of abschnitt.hint_items) {
        if (hinweis.kind === kind) liste.push({ art: "hinweis", kind, text: hinweis.text });
      }
    }
  }
  if (alleAufgelegt(form)) liste.push({ art: "aufgelegt" });
  return liste;
}

/**
 * Hinweise eines Abschnitts ohne die, die schon als Vorgabe im Kopf stehen (gleiche Angabe nicht
 * zweimal), erkannt an der Art (`hint_items[].kind`). Bei mehreren Abschnitten bleibt alles stehen.
 */
export function abschnittsHinweise(form: Formular, abschnittId: string): string[] {
  const abschnitt = form.sections.find((a) => a.id === abschnittId);
  if (!abschnitt) return [];
  const imKopf = einzigerAbschnitt(form) === abschnitt;
  return abschnitt.hint_items
    .filter((hinweis) => !(imKopf && KOPF_ARTEN.includes(hinweis.kind)))
    .map((hinweis) => hinweis.text);
}

/**
 * „aufgelegt“ an diesem Abschnitt zeigen: Er ist aufgelegt, aber nicht jeder Abschnitt (sonst steht
 * es einmal im Kopf).
 */
export function abschnittAufgelegt(form: Formular, abschnittId: string): boolean {
  const abschnitt = form.sections.find((a) => a.id === abschnittId);
  return abschnitt?.aufgelegt === true && !alleAufgelegt(form);
}

/**
 * Arten der Serien-Hinweise, die die Maske schon anders zeigt: „gestrichen“ als Marke,
 * „danach Trefferaufnahme“ als Zeile unter der Serie, die Position im Positionsablauf über den
 * Serien (der erscheint, sobald eine Serie eine Position hat; „aufgelegt“ steht im Kopf).
 */
const SERIE_EIGEN: readonly HinweisArt[] = ["struck", "scoring_break", "position"];

/** Hinweise einer Serie ohne die, die die Karte schon selbst zeigt (erkannt an der Art). */
export function serienHinweise(serie: SerieForm): string[] {
  return serie.hint_items
    .filter((hinweis) => !SERIE_EIGEN.includes(hinweis.kind))
    .map((hinweis) => hinweis.text);
}
