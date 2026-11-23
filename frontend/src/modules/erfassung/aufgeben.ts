/**
 * Aufgeben mit angefangener Serie (Sporthandbuch K 1.14 / L 1.12).
 *
 * Wer nach dem Kommando „Feuer“ aufgibt, wird mit dem bis dahin erzielten Ergebnis platziert. Der
 * Server (`backend/app/scoring/aborted.py`) kann das aber nur, wenn jede angefangene Serie entweder
 * fertig erfasst ist oder nach der Regel des Wertungsmodells auch halb zählt
 * (`ScoringModel.partial_series_counts`). Sonst steht der Start ohne Platz da („Ergebnis nicht
 * vergleichbar: Serie 2 unvollständig erfasst“). Bei der Fallscheibe macht der Status „Abbruch
 * durch den Schützen“ die Serie vollständig (dann zählen 60 s plus stehende Scheiben).
 *
 * Diese Datei erkennt solche Serien im Stand des Servers, damit die Rückfrage beim Aufgeben den
 * richtigen Schritt anbieten kann. Sie rechnet nichts selbst: Ob eine Serie angefangen
 * (`captured`) und fertig (`complete`) ist, sagt die Wertung des Servers; nur die Regel, welche
 * Modelle eine halbe Serie zählen, steht hier als Spiegel von `partial_series_counts`.
 */
import type { AbschnittForm, Formular, SerieForm, SerienWertung, Wertung } from "./api";
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
}

/**
 * Zählt eine angefangene, unvollständige Serie nach dem Aufgeben so, wie sie ist? Spiegel von
 * `partial_series_counts` der Wertungsmodelle (`backend/app/scoring/models.py`): Ringe zählen
 * fehlende Schüsse mit 0 (A 9.08); „Ringe minus Zeit“ nur mit erfasster Zeit; alle anderen
 * (Zeit plus Zuschläge und unbekannte Modelle) nicht.
 */
function halbeSerieZaehlt(modell: string, serie: SerienWertung): boolean {
  switch (modell) {
    case "ringe":
    case "ringe_mit_zeitabzug":
      return true;
    case "ringe_minus_zeit":
      return serie.time_cs !== null;
    default:
      return false;
  }
}

/**
 * Serien, die einen aufgegebenen Start ohne Platz ließen: angefangen, nicht fertig erfasst, nicht
 * gestrichen, und das Modell zählt sie halb nicht. Grundlage ist die Wertung des Servers
 * (`computed`), nicht die Eingabe auf dem Gerät.
 */
export function offeneSerien(form: Formular, wertung: Wertung | null | undefined): OffeneSerie[] {
  if (!wertung) return [];
  const liste: OffeneSerie[] = [];
  for (const abschnitt of form.sections) {
    const wertungAbschnitt = wertung.sections.find((a) => a.id === abschnitt.id);
    if (!wertungAbschnitt) continue;
    for (const serie of abschnitt.series) {
      const ergebnis = wertungAbschnitt.series[serie.index];
      if (!ergebnis || ergebnis.struck || serie.struck) continue;
      if (!ergebnis.captured || ergebnis.complete) continue;
      if (halbeSerieZaehlt(wertung.model, ergebnis)) continue;
      const option = statusFeld(serie)?.options?.find((o) => o.key === ABBRUCH_DURCH_SCHUETZEN);
      liste.push({
        abschnitt,
        serie,
        ort: form.sections.length > 1 ? `${abschnitt.name} · ${serie.label}` : serie.label,
        abbruchStatus: option?.label ?? null,
      });
    }
  }
  return liste;
}

/** „Serie 2“, „Serie 2 und 3“, „Serie 1, 2 und 4“ */
export function orteText(liste: readonly OffeneSerie[], und: string): string {
  const orte = liste.map((o) => o.ort);
  if (orte.length <= 1) return orte[0] ?? "";
  return `${orte.slice(0, -1).join(", ")} ${und} ${orte[orte.length - 1]}`;
}
