import type { Position } from "../../components/anschlag/typen";
import { formatHundertstel, formatUhrzeit, formatZahl } from "../../lib/format";
import type {
  FeedAblauf,
  FeedAbschnitt,
  FeedBahn,
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
    for (const zeile of mitAbgebrochenenAmEnde(gruppe.rows)) {
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
 * Abgebrochene Starts (nicht angetreten, aufgegeben, disqualifiziert) haben nie einen Platz: Sie
 * stehen am Ende ihrer Gruppe (`group: unranked`). Der Server liefert sie schon so; die Reihenfolge
 * der übrigen bleibt unverändert.
 */
export function mitAbgebrochenenAmEnde(zeilen: readonly FeedZeile[]): FeedZeile[] {
  return [
    ...zeilen.filter((zeile) => zeile.group !== "unranked"),
    ...zeilen.filter((zeile) => zeile.group === "unranked"),
  ];
}

/** Siegerliste einer Klasse: aufs Podest nur Platzierte (höchstens drei), alle übrigen danach. */
export function siegerAufteilung(zeilen: readonly FeedZeile[]): {
  podest: FeedZeile[];
  rest: FeedZeile[];
} {
  const platziert = zeilen.filter((zeile) => zeile.group !== "unranked");
  return {
    podest: platziert.slice(0, 3),
    rest: [...platziert.slice(3), ...zeilen.filter((zeile) => zeile.group === "unranked")],
  };
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
