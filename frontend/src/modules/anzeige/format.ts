import type { Position } from "../../components/anschlag/typen";
import { formatHundertstel, formatUhrzeit, formatZahl } from "../../lib/format";
import type {
  FeedAblauf,
  FeedAbschnitt,
  FeedBahn,
  FeedGruppe,
  FeedNaechsteBlock,
  FeedNaechsterEintrag,
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
  | { art: "mehr"; schluessel: string; anzahl: number }
  | {
      art: "ohne_kopf";
      schluessel: string;
      gruppe: FeedGruppe;
      /** Klasse mitnennen (mehrere Gruppen) */
      mitKlasse: boolean;
      fortsetzung?: boolean;
    }
  | { art: "ohne"; schluessel: string; zeile: FeedZeile };

type Kopf = Extract<RanglistenEintrag, { art: "klasse" | "ohne_kopf" }>;

/**
 * Macht aus den Wertungsgruppen eine flache Liste gleich hoher Einträge, damit sie sich nach der
 * verfügbaren Höhe in Seiten teilen lässt. Klassenköpfe nur, wenn es mehrere Gruppen gibt oder
 * die Gruppe einen Namen hat. Abgebrochene (`unplaced`) stehen je Gruppe in einem eigenen Block
 * „Ohne Platzierung“ hinter den Plätzen, nie dazwischen.
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
    const ohne = gruppe.unplaced;
    if (ohne.length > 0) {
      eintraege.push({ art: "ohne_kopf", schluessel: `o-${id}`, gruppe, mitKlasse: mitKopf });
      for (const zeile of ohne) {
        eintraege.push({ art: "ohne", schluessel: `u-${zeile.start_id}`, zeile });
      }
    }
  });
  return eintraege;
}

/**
 * Seiten aus Ranglisten-Einträgen: Ein Kopf (Klasse, „Ohne Platzierung“) steht nie allein unten
 * auf einer Seite, sondern rutscht mit seiner ersten Zeile auf die nächste. Geht der Block auf der
 * nächsten Seite weiter, steht sein Kopf dort noch einmal (als Fortsetzung).
 */
export function ranglistenSeiten(
  eintraege: readonly RanglistenEintrag[],
  proSeite: number | null,
): RanglistenEintrag[][] {
  return seitenMitKoepfen(
    eintraege,
    proSeite,
    (eintrag): eintrag is Kopf => eintrag.art === "klasse" || eintrag.art === "ohne_kopf",
    (kopf) => ({ ...kopf, schluessel: `${kopf.schluessel}-weiter`, fortsetzung: true }),
  );
}

/**
 * Teilt eine Liste mit Köpfen in Seiten: Ein Kopf steht nie allein unten auf einer Seite, und
 * geht sein Block auf der nächsten Seite weiter, steht dort `fortsetzung(kopf)` noch einmal.
 */
export function seitenMitKoepfen<T, K extends T>(
  eintraege: readonly T[],
  proSeite: number | null,
  istKopf: (eintrag: T) => eintrag is K,
  fortsetzung: (kopf: K) => T,
): T[][] {
  if (proSeite === null || proSeite <= 1 || eintraege.length <= proSeite) return [[...eintraege]];
  const seiten: T[][] = [];
  let seite: T[] = [];
  let kopf: K | null = null;
  for (const eintrag of eintraege) {
    const neuerKopf = istKopf(eintrag);
    if (neuerKopf) kopf = eintrag;
    const voll = seite.length >= proSeite;
    const kopfZuletzt = neuerKopf && seite.length === proSeite - 1;
    if (voll || kopfZuletzt) {
      seiten.push(seite);
      seite = [];
      if (!neuerKopf && kopf) seite.push(fortsetzung(kopf));
    }
    seite.push(eintrag);
  }
  if (seite.length > 0) seiten.push(seite);
  return seiten;
}

/** Eintrag der Liste „Als Nächstes“: Kopf eines Wettbewerbs, Person oder „weitere“. */
export type NaechsteEintrag =
  | { art: "kopf"; schluessel: string; block: FeedNaechsteBlock; fortsetzung?: boolean }
  | { art: "person"; schluessel: string; block: FeedNaechsteBlock; eintrag: FeedNaechsterEintrag }
  | { art: "mehr"; schluessel: string; anzahl: number };

/** „Als Nächstes“ als flache Liste gleich hoher Zeilen: je Wettbewerb ein Kopf, dann die Personen. */
export function naechsteEintraege(bloecke: readonly FeedNaechsteBlock[]): NaechsteEintrag[] {
  const eintraege: NaechsteEintrag[] = [];
  bloecke.forEach((block, nr) => {
    const id = `${block.competition_id}-${block.kind}-${nr}`;
    eintraege.push({ art: "kopf", schluessel: `k-${id}`, block });
    for (const eintrag of block.entries) {
      eintraege.push({ art: "person", schluessel: `p-${id}-${eintrag.start_id}`, block, eintrag });
    }
    if (block.more > 0) eintraege.push({ art: "mehr", schluessel: `m-${id}`, anzahl: block.more });
  });
  return eintraege;
}

export function naechsteSeiten(
  eintraege: readonly NaechsteEintrag[],
  proSeite: number | null,
): NaechsteEintrag[][] {
  return seitenMitKoepfen(
    eintraege,
    proSeite,
    (eintrag): eintrag is Extract<NaechsteEintrag, { art: "kopf" }> => eintrag.art === "kopf",
    (kopf) => ({ ...kopf, schluessel: `${kopf.schluessel}-weiter`, fortsetzung: true }),
  );
}

/** Die Zahl links in „Als Nächstes“: bei Zeitplan die Bahn, bei Reihenfolge der Platz. */
export function naechsteZahl(eintrag: FeedNaechsterEintrag): number {
  return "lane" in eintrag ? eintrag.lane : eintrag.position;
}

/**
 * Uhrzeit aus einem `*_local`-Feld des Feeds („2027-03-06T10:00:00+01:00“ → „10:00“). Der Server
 * hat schon in die Ortszeit des Turniers umgerechnet; hier wird nur noch die Uhrzeit abgelesen.
 */
export function uhrzeitLokal(lokal: string | null | undefined, sprache: string): string | null {
  const treffer = lokal ? /T(\d{2}):(\d{2})/.exec(lokal) : null;
  if (!treffer) return null;
  const nurUhrzeit = new Date(Date.UTC(2000, 0, 1, Number(treffer[1]), Number(treffer[2])));
  return new Intl.DateTimeFormat(sprache, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }).format(nurUhrzeit);
}

/** Uhrzeit aus dem Feed: die Ortszeit des Servers, sonst (ältere Server) der UTC-Zeitpunkt. */
export function feedUhrzeit(
  lokal: string | null | undefined,
  utc: string | null | undefined,
  sprache: string,
): string | null {
  const zeit = uhrzeitLokal(lokal, sprache);
  if (zeit !== null) return zeit;
  return utc ? formatUhrzeit(new Date(utc), sprache) : null;
}

/** Uhrzeit in der Zeitzone des Turniers (für die laufende Uhr); unbekannte Zone: Geräteuhr. */
export function uhrzeitInZone(
  datum: Date,
  zone: string | null | undefined,
  sprache: string,
): string {
  if (zone) {
    try {
      return new Intl.DateTimeFormat(sprache, {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: zone,
      }).format(datum);
    } catch {
      // Zone unbekannt: unten weiter mit der Geräteuhr.
    }
  }
  return formatUhrzeit(datum, sprache);
}

/** Wo eine Bahn im Ablauf gerade steht. */
export interface BahnFortschritt {
  /** Laufende Serie (1-basiert); bei `fertig` die letzte */
  serie: number;
  serien: number;
  fertig: boolean;
  /** Name des Abschnitts, nur wenn der Ablauf mehrere hat */
  abschnitt: string | null;
  /** Serien sind Positionen (Mehrdistanz, Parcours) */
  positionen: boolean;
}

/**
 * Fortschritt einer Bahn aus dem Feed: die laufende Serie aus `procedures[].current` (dieselbe,
 * die im Ablauf hervorgehoben ist), sonst aus `progress`. Ohne beides: `null` (nichts anzeigen).
 */
export function bahnFortschritt(
  bahn: FeedBahn,
  ablaeufe: readonly FeedAblauf[],
): BahnFortschritt | null {
  const start = bahn.start;
  if (!start) return null;
  const ablauf = ablaeufe.find((a) => a.competition_id === start.competition_id);
  const laufend = ablauf?.current?.find(
    (c) => c.lane === bahn.lane && c.start_id === start.start_id,
  );
  const fortschritt = bahn.progress ?? null;
  const abschnittId = laufend?.section_id ?? fortschritt?.section_id ?? null;
  const abschnitt = ablauf?.sections.find((a) => a.id === abschnittId) ?? null;
  const mehrere = (ablauf?.sections.length ?? 0) > 1;
  const name = mehrere && abschnitt ? abschnitt.name : null;
  const mitPositionen = abschnitt ? hatPositionen(abschnitt) : false;

  if (fortschritt?.complete) {
    const serien = fortschritt.series_total || abschnitt?.series_count || 0;
    return { serie: serien, serien, fertig: true, abschnitt: null, positionen: mitPositionen };
  }
  if (laufend) {
    const serien = abschnitt?.series_count ?? fortschritt?.series_total ?? 0;
    if (serien <= 0) return null;
    return {
      serie: Math.min(laufend.series_number, serien),
      serien,
      fertig: false,
      abschnitt: name,
      positionen: mitPositionen,
    };
  }
  if (fortschritt && fortschritt.series_total > 0) {
    const serien = fortschritt.series_total;
    return {
      serie: Math.min(fortschritt.series_done + 1, serien),
      serien,
      fertig: false,
      abschnitt: name,
      positionen: mitPositionen,
    };
  }
  return null;
}

/** Laufende Serien eines Abschnitts: Seriennummer → Bahnen (aufsteigend). */
export function laufendeSerien(ablauf: FeedAblauf, abschnittId: string): Map<number, number[]> {
  const serien = new Map<number, number[]>();
  for (const eintrag of ablauf.current ?? []) {
    if (eintrag.section_id !== abschnittId) continue;
    const bahnen = serien.get(eintrag.series_number) ?? [];
    bahnen.push(eintrag.lane);
    serien.set(eintrag.series_number, bahnen);
  }
  for (const bahnen of serien.values()) bahnen.sort((a, b) => a - b);
  return new Map([...serien.entries()].sort(([a], [b]) => a - b));
}

/**
 * Die Serie, die im Positions-Ablauf hervorgehoben wird (er kann nur eine): die mit den meisten
 * Bahnen, bei Gleichstand die frühere. Ohne laufende Serie `null`.
 */
export function hauptSerie(laufend: ReadonlyMap<number, readonly number[]>): number | null {
  let beste: number | null = null;
  let anzahl = 0;
  for (const [serie, bahnen] of laufend) {
    if (bahnen.length > anzahl) {
      beste = serie;
      anzahl = bahnen.length;
    }
  }
  return beste;
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

/**
 * Siegerliste einer Klasse: aufs Podest die ersten drei Plätze, die weiteren Plätze danach.
 * Abgebrochene (nicht angetreten, aufgegeben, disqualifiziert) liefert der Feed getrennt in
 * `unplaced`; sie stehen nie auf dem Podest und nie unter den Plätzen.
 */
export function siegerAufteilung(zeilen: readonly FeedZeile[]): {
  podest: FeedZeile[];
  rest: FeedZeile[];
} {
  const platziert = zeilen.filter((zeile) => zeile.group !== "unranked");
  return { podest: platziert.slice(0, 3), rest: platziert.slice(3) };
}

/**
 * Ob zur Zeile ein Ergebniswert gehört. „Nicht angetreten“ hat nie einen (der Feed liefert dann
 * `score_text: null`; ein „0,00“ wäre bei „niedrigster Wert gewinnt“ irreführend).
 */
export function mitErgebnis(zeile: Pick<FeedZeile, "abort_reason" | "score_text">): boolean {
  return zeile.score_text != null && zeile.abort_reason !== "dns";
}

/** Gibt es in der Gruppe Platzierte hinter dem Podest (Platz 4 und folgende)? */
export function mitWeiterenPlaetzen(zeilen: readonly FeedZeile[]): boolean {
  return zeilen.filter((zeile) => zeile.group !== "unranked").length > 3;
}

/** Längstes Wort eines Namens (Zeichen): Danach richtet sich die Schrift auf dem Podest. */
export function laengstesWort(text: string): number {
  return text.split(/\s+/).reduce((max, wort) => Math.max(max, wort.length), 0);
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
