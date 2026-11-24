/**
 * Aufgeben mit angefangener Serie (Sporthandbuch K 1.14 / L 1.12).
 *
 * Ob ein Aufgeben den Start platziert, sagt allein der Server: vor dem Aufgeben die Vorabauskunft
 * der Maske (`abort_preview`, gerechnet wie die Rangliste), danach die Rangliste selbst. Hier wird
 * nichts davon nachgerechnet. Diese Datei sucht nur die Serien heraus, an denen der Weg zur
 * Wertung ansetzt: angefangen (`captured`), nicht fertig (`complete`), nicht gestrichen – laut
 * Wertung des Servers. Bei der Fallscheibe macht der Status „Abbruch durch den Schützen“ so eine
 * Serie vollständig.
 */
import type { AbschnittForm, AufgebenAuskunft, Formular, SerieForm, Wertung } from "./api";
import { statusFeld } from "./rohwerte";

/** Status „Abbruch durch den Schützen“ (`app.scoring.status.ABORTED_BY_SHOOTER`). */
export const ABBRUCH_DURCH_SCHUETZEN = "aborted_by_shooter";

export interface OffeneSerie {
  abschnitt: AbschnittForm;
  serie: SerieForm;
  /** „Serie 2“, bei mehreren Abschnitten „Präzision · Serie 2“ */
  ort: string;
  /** Bezeichnung des Status „Abbruch durch den Schützen“, wenn die Serie ihn kennt; sonst null */
  abbruchStatus: string | null;
  /** „Abbruch durch den Schützen“ steht laut Server schon an der Serie; es fehlen nur Werte. */
  statusGesetzt: boolean;
}

/**
 * Angefangene, nicht fertige Serien laut Wertung des Servers. `nummern`: nur Serien mit diesen
 * Nummern (`abort_preview.open_series`); ohne Angabe alle.
 */
export function offeneSerien(
  form: Formular,
  wertung: Wertung | null | undefined,
  nummern?: readonly number[],
): OffeneSerie[] {
  if (!wertung) return [];
  const liste: OffeneSerie[] = [];
  for (const abschnitt of form.sections) {
    const wertungAbschnitt = wertung.sections.find((a) => a.id === abschnitt.id);
    if (!wertungAbschnitt) continue;
    for (const serie of abschnitt.series) {
      if (nummern && !nummern.includes(serie.number)) continue;
      const ergebnis = wertungAbschnitt.series[serie.index];
      if (!ergebnis || ergebnis.struck || serie.struck) continue;
      if (!ergebnis.captured || ergebnis.complete) continue;
      const option = statusFeld(serie)?.options?.find((o) => o.key === ABBRUCH_DURCH_SCHUETZEN);
      liste.push({
        abschnitt,
        serie,
        ort: form.sections.length > 1 ? `${abschnitt.name} · ${serie.label}` : serie.label,
        abbruchStatus: option?.label ?? null,
        statusGesetzt: ergebnis.status === ABBRUCH_DURCH_SCHUETZEN,
      });
    }
  }
  return liste;
}

/**
 * Serien, an denen ein Aufgeben laut Vorabauskunft scheitert (`incomplete_series`): die vom Server
 * genannten offenen Serien, soweit angefangen. Sonst keine.
 */
export function serienDerAuskunft(
  form: Formular,
  wertung: Wertung | null | undefined,
  auskunft: AufgebenAuskunft | null | undefined,
): OffeneSerie[] {
  if (auskunft?.reason_code !== "incomplete_series") return [];
  return offeneSerien(form, wertung, auskunft.open_series);
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
  const orte = liste.map((o) => o.ort);
  if (orte.length <= 1) return orte[0] ?? "";
  return `${orte.slice(0, -1).join(", ")} ${und} ${orte[orte.length - 1]}`;
}
