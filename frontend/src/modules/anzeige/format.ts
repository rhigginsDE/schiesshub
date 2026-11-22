import type { Position } from "../../components/anschlag/typen";
import { formatHundertstel, formatZahl } from "../../lib/format";
import type {
  FeedAbschnitt,
  FeedGruppe,
  FeedPosition,
  FeedRangliste,
  FeedSerie,
  FeedZeile,
} from "./typen";

/**
 * Teilwert einer Serie, wie er in der Live-Wertung steht: Ringe, sonst die Zeit mit Zuschlägen
 * (Hundertstel, Dezimalkomma), sonst die reine Zeit; ohne Wert ein Strich.
 */
export function serienWert(serie: FeedSerie | undefined, sprache: string): string {
  if (!serie) return "–";
  if (serie.rings != null) return formatZahl(serie.rings, {}, sprache);
  if (serie.total_cs != null) return formatHundertstel(serie.total_cs, sprache);
  if (serie.time_cs != null) return formatHundertstel(serie.time_cs, sprache);
  return "–";
}

/** So viele Serienspalten braucht die Rangliste (die längste Zeile zählt). */
export function serienAnzahl(rangliste: FeedRangliste): number {
  let anzahl = 0;
  for (const gruppe of rangliste.groups) {
    for (const zeile of gruppe.rows) anzahl = Math.max(anzahl, zeile.series.length);
  }
  return anzahl;
}

/**
 * Breite einer Serienspalte in cqmin: so breit wie der längste Teilwert (Ziffern in Mono, etwa
 * 1,85 cqmin je Zeichen bei 3 cqmin Schrift), mindestens so breit wie die Überschrift.
 */
export function serienBreite(rangliste: FeedRangliste, sprache: string): number {
  let zeichen = 3;
  for (const gruppe of rangliste.groups) {
    for (const zeile of gruppe.rows) {
      for (const serie of zeile.series)
        zeichen = Math.max(zeichen, serienWert(serie, sprache).length);
    }
  }
  return Math.max(9, Math.round((zeichen * 1.85 + 1.2) * 10) / 10);
}

/** Passen die Serienspalten neben Platz, Name und Gesamt? Sonst stehen nur diese da. */
export function serienPassen(anzahl: number, breite: number, hochkant: boolean): boolean {
  const platz = hochkant ? 44 : 96;
  return anzahl * (breite + 1.8) <= platz;
}

export interface GesamtTeile {
  wert: string;
  einheit: string | null;
}

/**
 * Trennt die Einheit vom Gesamtergebnis, damit die Zahl groß und die Einheit klein stehen kann:
 * „183 Ringe“ → „183“ + „Ringe“. Der Text kommt fertig formatiert vom Server.
 */
export function gesamtTeile(text: string | null, einheit: string | null): GesamtTeile {
  if (!text) return { wert: "–", einheit: null };
  const sauber = text.trim();
  if (einheit && sauber.endsWith(` ${einheit}`)) {
    return { wert: sauber.slice(0, -einheit.length - 1), einheit };
  }
  return { wert: sauber, einheit: null };
}

/** Eintrag einer Ranglisten-Seite: Kopf einer Klasse, Zeile oder „weitere“. */
export type RanglistenEintrag =
  | { art: "klasse"; schluessel: string; gruppe: FeedGruppe; fortsetzung?: boolean }
  | { art: "zeile"; schluessel: string; zeile: FeedZeile }
  | { art: "mehr"; schluessel: string; anzahl: number };

/**
 * Macht aus den Wertungsgruppen eine flache Liste gleich hoher Einträge, damit sie sich nach der
 * verfügbaren Höhe in Seiten teilen lässt. Klassenköpfe nur, wenn es mehrere Gruppen gibt oder
 * die Gruppe einen Namen hat.
 */
export function ranglistenEintraege(rangliste: FeedRangliste): RanglistenEintrag[] {
  const eintraege: RanglistenEintrag[] = [];
  const mitKopf = rangliste.groups.length > 1;
  rangliste.groups.forEach((gruppe, nr) => {
    const id = gruppe.class_id ?? `gruppe-${nr}`;
    if (mitKopf && (gruppe.class_name || gruppe.class_short)) {
      eintraege.push({ art: "klasse", schluessel: `k-${id}`, gruppe });
    }
    for (const zeile of gruppe.rows) {
      eintraege.push({ art: "zeile", schluessel: `z-${zeile.start_id}`, zeile });
    }
    if (gruppe.more > 0)
      eintraege.push({ art: "mehr", schluessel: `m-${id}`, anzahl: gruppe.more });
  });
  return eintraege;
}

/**
 * Seiten aus Ranglisten-Einträgen: Ein Klassenkopf steht nie allein unten auf einer Seite,
 * sondern rutscht mit seiner ersten Zeile auf die nächste. Geht eine Klasse auf der nächsten Seite
 * weiter, steht ihr Kopf dort noch einmal (als Fortsetzung), damit man die Klasse erkennt.
 */
export function ranglistenSeiten(
  eintraege: readonly RanglistenEintrag[],
  proSeite: number | null,
): RanglistenEintrag[][] {
  if (proSeite === null || proSeite <= 1 || eintraege.length <= proSeite) return [[...eintraege]];
  const seiten: RanglistenEintrag[][] = [];
  let seite: RanglistenEintrag[] = [];
  let kopf: Extract<RanglistenEintrag, { art: "klasse" }> | null = null;
  for (const eintrag of eintraege) {
    if (eintrag.art === "klasse") kopf = eintrag;
    const voll = seite.length >= proSeite;
    const kopfZuletzt = eintrag.art === "klasse" && seite.length === proSeite - 1;
    if (voll || kopfZuletzt) {
      seiten.push(seite);
      seite = [];
      if (eintrag.art !== "klasse" && kopf) {
        seite.push({ ...kopf, schluessel: `${kopf.schluessel}-weiter`, fortsetzung: true });
      }
    }
    seite.push(eintrag);
  }
  if (seite.length > 0) seiten.push(seite);
  return seiten;
}

/** Position aus dem Feed in der Form, die `PositionsAblauf` erwartet. */
export function alsPosition(position: FeedPosition): Position {
  return {
    nr: position.nr,
    distanz_m: position.distance_m,
    scheibe: position.target,
    anschlaege: position.stances.map((anschlag) => ({
      haltung: anschlag.haltung,
      hand: anschlag.hand,
    })),
  };
}

/** Hat jede Serie des Abschnitts eine Position (Mehrdistanz, Parcours)? */
export function hatPositionen(abschnitt: FeedAbschnitt): boolean {
  return abschnitt.series.length > 0 && abschnitt.series.every((serie) => serie.position !== null);
}

/** Serien, nach denen Trefferaufnahme ist (1-basiert, wie `PositionsAblauf` sie erwartet). */
export function trefferaufnahmeNach(abschnitt: FeedAbschnitt): number[] {
  return abschnitt.series.filter((serie) => serie.hit_review_after).map((serie) => serie.number);
}

/**
 * Höhe der Podeststufe nach dem Platz, nicht nach der Stelle: Zwei geteilte Erste stehen beide
 * oben. Ohne Platz zählt die Stelle (1 bis 3).
 */
export function podestStufe(platz: number | null, stelle: number): 1 | 2 | 3 {
  const wert = platz ?? stelle;
  return wert <= 1 ? 1 : wert === 2 ? 2 : 3;
}

/** Podest-Reihenfolge der ersten drei: Zweiter links, Erster in der Mitte, Dritter rechts. */
export function podestReihenfolge<T>(erste: readonly T[]): { eintrag: T; rang: number }[] {
  const [eins, zwei, drei] = erste;
  const reihe: { eintrag: T; rang: number }[] = [];
  if (zwei !== undefined) reihe.push({ eintrag: zwei, rang: 2 });
  if (eins !== undefined) reihe.push({ eintrag: eins, rang: 1 });
  if (drei !== undefined) reihe.push({ eintrag: drei, rang: 3 });
  return reihe;
}
