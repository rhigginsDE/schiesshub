/**
 * Aufgeben mit angefangener Serie (Sporthandbuch K 1.14 / L 1.12).
 *
 * Ob ein Aufgeben den Start platziert, sagt allein der Server: die Vorabauskunft der Maske
 * (`abort_preview`, gerechnet wie die Rangliste) – vor dem Aufgeben, und beim schon
 * abgebrochenen Start, wie dieser Abbruch gewertet wird. Hier wird nichts davon nachgerechnet.
 * Diese Datei ordnet nur die Serien, die der Server nennt (`open_series_items`, `missing_fields`),
 * der Maske zu: wo der Weg zur Wertung ansetzt und wohin ein Tipp führt.
 */
import type { AbschnittForm, AufgebenAuskunft, Formular, SerieForm, Wertung } from "./api";
import { normalerPfad, serienPfad, statusFeld } from "./rohwerte";

/** Status „Abbruch durch den Schützen“ (`app.scoring.status.ABORTED_BY_SHOOTER`). */
export const ABBRUCH_DURCH_SCHUETZEN = "aborted_by_shooter";

/** Offene Serie laut Server: angefangen oder noch gar nicht geschossen. */
export type OffenZustand = AufgebenAuskunft["open_series_items"][number]["state"];

/** Fehlender Pflichtwert einer Serie mit gesetztem Serienstatus (`missing_fields`). */
export type FehlenderWert = AufgebenAuskunft["missing_fields"][number];

export interface OffeneSerie {
  abschnitt: AbschnittForm;
  serie: SerieForm;
  /** „Serie 2“, bei mehreren Abschnitten „Präzision · Serie 2“ */
  ort: string;
  /** Bezeichnung des Status „Abbruch durch den Schützen“, wenn die Serie ihn kennt; sonst null */
  abbruchStatus: string | null;
  /** Ein Serienstatus steht laut Server schon an der Serie; es fehlen nur Werte. */
  statusGesetzt: boolean;
  /** Pflichtwerte, die laut Server in dieser Serie fehlen (Schlüssel des Feldes) */
  fehlend: string[];
}

/** Abschnitt und Serie der Maske zu einem Pfad des Servers (`sections.x.series[2]`). */
function serieZumPfad(
  form: Formular,
  pfad: string,
): { abschnitt: AbschnittForm; serie: SerieForm } | null {
  const normal = normalerPfad(pfad);
  for (const abschnitt of form.sections) {
    for (const serie of abschnitt.series) {
      if (serienPfad(abschnitt.id, serie.index) === normal) return { abschnitt, serie };
    }
  }
  return null;
}

function offeneSerie(
  form: Formular,
  wertung: Wertung | null | undefined,
  abschnitt: AbschnittForm,
  serie: SerieForm,
): OffeneSerie {
  const option = statusFeld(serie)?.options?.find((o) => o.key === ABBRUCH_DURCH_SCHUETZEN);
  const ergebnis = wertung?.sections.find((a) => a.id === abschnitt.id)?.series[serie.index];
  return {
    abschnitt,
    serie,
    ort: form.sections.length > 1 ? `${abschnitt.name} · ${serie.label}` : serie.label,
    abbruchStatus: option?.label ?? null,
    statusGesetzt: ergebnis !== undefined && ergebnis.status !== "normal",
    fehlend: [],
  };
}

/**
 * Serien, an denen die Wertung laut Vorabauskunft scheitert: angefangen ohne Serienstatus
 * (`incomplete_series`, aus `open_series_items` mit „started“) und Serien mit gesetztem Status,
 * denen Pflichtwerte fehlen (`missing_values`, aus `missing_fields`). Sonst keine.
 */
export function serienDerAuskunft(
  form: Formular,
  wertung: Wertung | null | undefined,
  auskunft: AufgebenAuskunft | null | undefined,
): OffeneSerie[] {
  if (auskunft?.reason_code !== "incomplete_series" && auskunft?.reason_code !== "missing_values") {
    return [];
  }
  const liste: OffeneSerie[] = [];
  const eintrag = (pfad: string): OffeneSerie | null => {
    const treffer = serieZumPfad(form, pfad);
    if (!treffer) return null;
    const vorhanden = liste.find((o) => o.serie === treffer.serie);
    if (vorhanden) return vorhanden;
    const neu = offeneSerie(form, wertung, treffer.abschnitt, treffer.serie);
    liste.push(neu);
    return neu;
  };
  if (auskunft.reason_code === "incomplete_series") {
    for (const item of auskunft.open_series_items ?? []) {
      if (item.state !== "started") continue;
      const ergebnis = wertung?.sections.find((a) => a.id === item.section_id)?.series;
      const roh = ergebnis?.find((x) => x.number === item.series);
      // Mit Serienstatus gehört die Serie zu den fehlenden Werten (unten), nicht hierher.
      if (roh && roh.status !== "normal") continue;
      eintrag(item.path);
    }
  }
  for (const wert of auskunft.missing_fields ?? []) {
    const offen = eintrag(wert.path);
    if (!offen) continue;
    offen.statusGesetzt = true;
    if (!offen.fehlend.includes(wert.key)) offen.fehlend.push(wert.key);
  }
  // In der Reihenfolge der Maske.
  const rang = (o: OffeneSerie) =>
    form.sections.indexOf(o.abschnitt) * 10_000 + o.abschnitt.series.indexOf(o.serie);
  return liste.sort((a, b) => rang(a) - rang(b));
}

/** Offene Serien eines Abschnitts laut Server, getrennt nach angefangen und nicht geschossen. */
export interface OffeneImAbschnitt {
  abschnittId: string;
  /** Name des Abschnitts (vom Server) */
  name: string;
  angefangen: { nummer: number; pfad: string }[];
  nichtGeschossen: { nummer: number; pfad: string }[];
}

/** `open_series_items` je Abschnitt, in der Reihenfolge des Servers. */
export function offeneJeAbschnitt(auskunft: AufgebenAuskunft | null | undefined) {
  const liste: OffeneImAbschnitt[] = [];
  for (const item of auskunft?.open_series_items ?? []) {
    let abschnitt = liste.find((a) => a.abschnittId === item.section_id);
    if (!abschnitt) {
      abschnitt = {
        abschnittId: item.section_id,
        name: item.section_name,
        angefangen: [],
        nichtGeschossen: [],
      };
      liste.push(abschnitt);
    }
    const eintrag = { nummer: item.series, pfad: normalerPfad(item.path) };
    if (item.state === "started") abschnitt.angefangen.push(eintrag);
    else abschnitt.nichtGeschossen.push(eintrag);
  }
  return liste;
}

/** Bezeichnung von „Abbruch durch den Schützen“, wenn alle Serien der Liste ihn kennen. */
export function gemeinsamerStatus(liste: readonly OffeneSerie[]): string | null {
  return liste.length > 0 && liste.every((o) => o.abbruchStatus)
    ? (liste[0]?.abbruchStatus ?? null)
    : null;
}

/** Alle Serien der Liste haben den Status schon: Es fehlen nur noch Werte. */
export function nurWerteFehlen(liste: readonly OffeneSerie[]): boolean {
  return liste.length > 0 && liste.every((o) => o.statusGesetzt);
}

/** „Serie 2“, „Serie 2 und 3“, „Serie 1, 2 und 4“ */
export function orteText(liste: readonly OffeneSerie[], und: string): string {
  return aufzaehlung(
    liste.map((o) => o.ort),
    und,
  );
}

/** „a“, „a und b“, „a, b und c“ */
export function aufzaehlung(teile: readonly string[], und: string): string {
  if (teile.length <= 1) return teile[0] ?? "";
  return `${teile.slice(0, -1).join(", ")} ${und} ${teile[teile.length - 1]}`;
}
