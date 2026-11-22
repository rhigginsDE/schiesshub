/**
 * Eingabefelder und Rohwerte des Terminals: ohne React, einzeln getestet.
 *
 * Alles hier richtet sich nach der Formularbeschreibung des Servers (`GET …/form`). Es gibt keine
 * Sonderfälle je Disziplin und keine Summen: Was ein Wert bedeutet, rechnet der Server.
 *
 * Der Entwurf hat dieselbe Form wie die Rohwerte (`{sections: {<id>: {series: […], time_cs}}}`),
 * kann aber Werte enthalten, die der gewählte Serienstatus nicht braucht (sie bleiben erhalten,
 * falls der Status zurückgestellt wird). `rohwerteAus` macht daraus, was gesendet wird.
 */
import type {
  AbschnittForm,
  FeldBeschreibung,
  Formular,
  Rohwerte,
  SerieForm,
  StatusOption,
} from "./api";

/** Ein Schusswert: Ringzahl oder „X“ (Innenzehner). */
export type Schusswert = number | string;

export type SerieEntwurf = Record<string, unknown>;

export interface AbschnittEntwurf {
  series: (SerieEntwurf | null)[];
  time_cs?: number;
}

export interface Entwurf {
  sections: Record<string, AbschnittEntwurf>;
}

/** Ein Eingabeplatz: ein Feld einer Serie, ein einzelner Schuss oder ein Feld des Abschnitts. */
export interface FeldRef {
  /** Eindeutig und gleich dem Pfad in Fehlermeldungen: `sections.x.series.2.standing`, `….shots.3` */
  id: string;
  abschnitt: string;
  /** Index der Serie; `null` für Felder des ganzen Abschnitts (Gesamtzeit) */
  serie: number | null;
  key: string;
  /** Nur bei Schüssen: Index des Schusses in der Serie */
  schuss?: number;
  feld: FeldBeschreibung;
}

export const NORMAL = "normal";
const RING_SUMME = ["sum", "tens", "inner_tens"] as const;

/** `sections.fallscheibe.series[2]` → `sections.fallscheibe.series.2` (wie die Feldfehler des Clients). */
export function normalerPfad(pfad: string): string {
  return pfad.replace(/\[(\d+)\]/g, ".$1").replace(/^raw\.?/, "");
}

export function serienPfad(abschnitt: string, serie: number): string {
  return `sections.${abschnitt}.series.${serie}`;
}

export function feldId(abschnitt: string, serie: number | null, key: string, schuss?: number) {
  const basis = serie === null ? `sections.${abschnitt}` : serienPfad(abschnitt, serie);
  return schuss === undefined ? `${basis}.${key}` : `${basis}.${key}.${schuss}`;
}

// --- Entwurf lesen und ändern ------------------------------------------------------------------

function istObjekt(wert: unknown): wert is Record<string, unknown> {
  return typeof wert === "object" && wert !== null && !Array.isArray(wert);
}

/** Entwurf aus den Rohwerten des Servers (unbekannte Teile bleiben, wie sie sind). */
export function entwurfAus(raw: Rohwerte | null | undefined): Entwurf {
  const sections: Record<string, AbschnittEntwurf> = {};
  const quelle = istObjekt(raw) && istObjekt(raw.sections) ? raw.sections : {};
  for (const [id, abschnitt] of Object.entries(quelle)) {
    if (!istObjekt(abschnitt)) continue;
    const series = Array.isArray(abschnitt.series)
      ? abschnitt.series.map((serie) => (istObjekt(serie) ? { ...serie } : null))
      : [];
    const eintrag: AbschnittEntwurf = { series };
    if (typeof abschnitt.time_cs === "number") eintrag.time_cs = abschnitt.time_cs;
    sections[id] = eintrag;
  }
  return { sections };
}

export function serieAus(entwurf: Entwurf, abschnitt: string, serie: number): SerieEntwurf {
  return entwurf.sections[abschnitt]?.series[serie] ?? {};
}

export function schuesseAus(serie: SerieEntwurf): Schusswert[] {
  return Array.isArray(serie.shots) ? (serie.shots as Schusswert[]) : [];
}

/** Wert eines Eingabeplatzes (Schuss, Zahl, Zeit, Status) oder `undefined`. */
export function wertAus(
  entwurf: Entwurf,
  ref: Pick<FeldRef, "abschnitt" | "serie" | "key" | "schuss">,
) {
  if (ref.serie === null) {
    return ref.key === "time_cs" ? entwurf.sections[ref.abschnitt]?.time_cs : undefined;
  }
  const serie = serieAus(entwurf, ref.abschnitt, ref.serie);
  if (ref.schuss !== undefined) return schuesseAus(serie)[ref.schuss];
  return serie[ref.key];
}

function mitAbschnitt(
  entwurf: Entwurf,
  abschnitt: string,
  aendern: (alt: AbschnittEntwurf) => AbschnittEntwurf,
): Entwurf {
  const alt = entwurf.sections[abschnitt] ?? { series: [] };
  return { sections: { ...entwurf.sections, [abschnitt]: aendern(alt) } };
}

function mitSerie(
  entwurf: Entwurf,
  abschnitt: string,
  serie: number,
  aendern: (alt: SerieEntwurf) => SerieEntwurf,
): Entwurf {
  return mitAbschnitt(entwurf, abschnitt, (alt) => {
    const series = [...alt.series];
    while (series.length <= serie) series.push(null);
    series[serie] = aendern({ ...(series[serie] ?? {}) });
    return { ...alt, series };
  });
}

/**
 * Setzt einen Wert (`undefined` löscht ihn). Wer in einer Serie Schüsse eingibt, ersetzt eine
 * vorher erfasste Seriensumme und umgekehrt: Der Server nimmt je Serie nur eins von beiden.
 */
export function setzeWert(
  entwurf: Entwurf,
  ref: Pick<FeldRef, "abschnitt" | "serie" | "key" | "schuss">,
  wert: unknown,
): Entwurf {
  if (ref.serie === null) {
    return mitAbschnitt(entwurf, ref.abschnitt, (alt) => {
      const neu = { ...alt };
      if (typeof wert === "number") neu.time_cs = wert;
      else delete neu.time_cs;
      return neu;
    });
  }
  return mitSerie(entwurf, ref.abschnitt, ref.serie, (serie) => {
    if (ref.key === "shots" && ref.schuss !== undefined) {
      for (const key of RING_SUMME) delete serie[key];
      const schuesse = [...schuesseAus(serie)];
      if (wert === undefined) schuesse.splice(ref.schuss);
      else if (ref.schuss <= schuesse.length) schuesse[ref.schuss] = wert as Schusswert;
      if (schuesse.length > 0) serie.shots = schuesse;
      else delete serie.shots;
      return serie;
    }
    if ((RING_SUMME as readonly string[]).includes(ref.key)) delete serie.shots;
    if (wert === undefined || (ref.key === "status" && wert === NORMAL)) delete serie[ref.key];
    else serie[ref.key] = wert;
    return serie;
  });
}

// --- Status und Pflichtfelder --------------------------------------------------------------------

export function statusFeld(serie: SerieForm): FeldBeschreibung | undefined {
  return serie.fields.find((feld) => feld.kind === "choice" && feld.key === "status");
}

/** Gewählter Ablauf der Serie; fehlt er, gilt „normal“. */
export function statusAus(
  entwurf: Entwurf,
  abschnitt: string,
  serie: SerieForm,
): StatusOption | null {
  const feld = statusFeld(serie);
  if (!feld?.options) return null;
  const gewaehlt = serieAus(entwurf, abschnitt, serie.index).status ?? NORMAL;
  return feld.options.find((option) => option.key === gewaehlt) ?? null;
}

/**
 * Ob ein Feld beim gewählten Status gebraucht wird. Im Regelfall gelten alle Felder der Serie
 * (auch freiwillige wie Zehner), sonst nur die `required_fields` des Status.
 */
export function feldAktiv(option: StatusOption | null, key: string): boolean {
  if (key === "status") return true;
  if (!option || option.key === NORMAL) return true;
  return option.required_fields.includes(key);
}

// --- Rohwerte bauen ----------------------------------------------------------------------------

function leer(serie: SerieEntwurf): boolean {
  return Object.keys(serie).length === 0;
}

/**
 * Die Rohwerte zum Senden: nur Werte, die der Status der Serie braucht; leere Serien als `null`,
 * leere Abschnitte und nachlaufende leere Serien entfallen. Teile, die das Formular nicht kennt
 * (z. B. nach einer Änderung der Wertung), bleiben stehen; der Server meldet sie dann.
 */
export function rohwerteAus(form: Formular, entwurf: Entwurf): Rohwerte {
  const sections: Record<string, unknown> = {};
  const bekannte = new Set(form.sections.map((abschnitt) => abschnitt.id));
  for (const abschnitt of form.sections) {
    const eintrag = entwurf.sections[abschnitt.id];
    if (!eintrag) continue;
    const series: (SerieEntwurf | null)[] = eintrag.series.map((serie, index) => {
      if (!serie) return null;
      const formSerie = abschnitt.series.find((s) => s.index === index);
      const option = formSerie ? statusAus(entwurf, abschnitt.id, formSerie) : null;
      const neu: SerieEntwurf = {};
      for (const [key, wert] of Object.entries(serie)) {
        if (wert === undefined) continue;
        if (key === "shots" && Array.isArray(wert) && wert.length === 0) continue;
        // Zehner und Innenzehner gehören zur Seriensumme: Sie gehen mit, wenn die Summe gilt.
        const zurSumme =
          (RING_SUMME as readonly string[]).includes(key) && feldAktiv(option, "sum");
        if (!feldAktiv(option, key) && !zurSumme) continue;
        neu[key] = wert;
      }
      return leer(neu) ? null : neu;
    });
    while (series.length > 0 && series[series.length - 1] === null) series.pop();
    const ziel: Record<string, unknown> = {};
    if (series.length > 0) ziel.series = series;
    if (eintrag.time_cs !== undefined) ziel.time_cs = eintrag.time_cs;
    if (Object.keys(ziel).length > 0) sections[abschnitt.id] = ziel;
  }
  for (const [id, eintrag] of Object.entries(entwurf.sections)) {
    if (!bekannte.has(id)) sections[id] = eintrag;
  }
  return Object.keys(sections).length > 0 ? { sections } : {};
}

/** Text mit sortierten Schlüsseln, um Rohwerte zu vergleichen. */
export function stabil(wert: unknown): string {
  if (Array.isArray(wert)) return `[${wert.map(stabil).join(",")}]`;
  if (istObjekt(wert)) {
    return `{${Object.keys(wert)
      .sort()
      .filter((key) => wert[key] !== undefined)
      .map((key) => `${JSON.stringify(key)}:${stabil(wert[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(wert ?? null);
}

/** Ob zwei Rohwerte inhaltlich gleich sind (leere Hüllen zählen als nichts). */
export function gleicheRohwerte(a: Rohwerte | null | undefined, b: Rohwerte | null | undefined) {
  const norm = (raw: Rohwerte | null | undefined) => {
    if (!istObjekt(raw)) return "{}";
    if (istObjekt(raw.sections) && Object.keys(raw.sections).length === 0) return "{}";
    return stabil(raw);
  };
  return norm(a) === norm(b);
}

// --- Reihenfolge der Eingabeplätze ---------------------------------------------------------------

export interface ReihenfolgeOptionen {
  /** Gestrichene Serien, die aufgeklappt sind (`sections.x.series.3`); sonst werden sie übersprungen */
  aufgeklappt?: ReadonlySet<string>;
}

/** Felder einer Serie in Eingabereihenfolge (ohne Status-Auswahl und ohne deaktivierte Felder). */
export function serienFelder(
  entwurf: Entwurf,
  abschnitt: AbschnittForm,
  serie: SerieForm,
): FeldRef[] {
  const option = statusAus(entwurf, abschnitt.id, serie);
  const refs: FeldRef[] = [];
  for (const feld of serie.fields) {
    if (feld.kind === "choice" || !feldAktiv(option, feld.key)) continue;
    if (feld.kind === "shots") {
      for (let schuss = 0; schuss < (feld.count ?? 0); schuss++) {
        refs.push({
          id: feldId(abschnitt.id, serie.index, feld.key, schuss),
          abschnitt: abschnitt.id,
          serie: serie.index,
          key: feld.key,
          schuss,
          feld,
        });
      }
    } else {
      refs.push({
        id: feldId(abschnitt.id, serie.index, feld.key),
        abschnitt: abschnitt.id,
        serie: serie.index,
        key: feld.key,
        feld,
      });
    }
  }
  return refs;
}

/** Alle Eingabeplätze in der Reihenfolge, in der das Terminal weiterschaltet. */
export function reihenfolge(
  form: Formular,
  entwurf: Entwurf,
  optionen: ReihenfolgeOptionen = {},
): FeldRef[] {
  const refs: FeldRef[] = [];
  for (const abschnitt of form.sections) {
    for (const serie of abschnitt.series) {
      if (serie.struck && !optionen.aufgeklappt?.has(serienPfad(abschnitt.id, serie.index))) {
        continue;
      }
      refs.push(...serienFelder(entwurf, abschnitt, serie));
    }
    // Die Gesamtzeit eines Parcours steht nach seinen Serien.
    for (const feld of abschnitt.fields) {
      if (feld.kind === "choice") continue;
      refs.push({
        id: feldId(abschnitt.id, null, feld.key),
        abschnitt: abschnitt.id,
        serie: null,
        key: feld.key,
        feld,
      });
    }
  }
  return refs;
}

/** Ob ein Eingabeplatz schon einen Wert hat. */
export function hatWert(entwurf: Entwurf, ref: FeldRef): boolean {
  const wert = wertAus(entwurf, ref);
  return wert !== undefined && wert !== null;
}

/**
 * Wohin ein angetippter Schuss führt: Schüsse werden der Reihe nach erfasst, ein Tipp hinter die
 * erste Lücke springt zur Lücke.
 */
export function erreichbar(entwurf: Entwurf, ref: FeldRef): FeldRef {
  if (ref.schuss === undefined || ref.serie === null) return ref;
  const anzahl = schuesseAus(serieAus(entwurf, ref.abschnitt, ref.serie)).length;
  if (ref.schuss <= anzahl) return ref;
  return { ...ref, schuss: anzahl, id: feldId(ref.abschnitt, ref.serie, ref.key, anzahl) };
}

/** Erstes Feld ohne Wert (Pflichtfelder zuerst), sonst das erste Feld. */
export function erstesOffenes(refs: readonly FeldRef[], entwurf: Entwurf): FeldRef | null {
  return (
    refs.find((ref) => ref.feld.required && !hatWert(entwurf, ref)) ??
    refs.find((ref) => !hatWert(entwurf, ref)) ??
    refs[0] ??
    null
  );
}

export function naechstes(refs: readonly FeldRef[], id: string | null): FeldRef | null {
  const index = refs.findIndex((ref) => ref.id === id);
  return index >= 0 ? (refs[index + 1] ?? null) : null;
}

export function voriges(refs: readonly FeldRef[], id: string | null): FeldRef | null {
  const index = refs.findIndex((ref) => ref.id === id);
  return index > 0 ? (refs[index - 1] ?? null) : null;
}

// --- Fehler und Hinweise am Feld -----------------------------------------------------------------

export interface PfadMeldung {
  /** Normalisierter Pfad ohne `raw.` (`sections.x.series.2.standing`); leer = ganzer Start */
  pfad: string;
  meldung: string;
}

/** Meldungen genau für diesen Pfad oder darunter. */
export function meldungenFuer(meldungen: readonly PfadMeldung[], pfad: string): PfadMeldung[] {
  return meldungen.filter((m) => m.pfad === pfad || m.pfad.startsWith(`${pfad}.`));
}

/** Meldungen, die zu keinem Feld und keiner Serie der Maske gehören. */
export function uebrigeMeldungen(form: Formular, meldungen: readonly PfadMeldung[]): PfadMeldung[] {
  const pfade: string[] = [];
  for (const abschnitt of form.sections) {
    for (const serie of abschnitt.series) pfade.push(serienPfad(abschnitt.id, serie.index));
    for (const feld of abschnitt.fields) pfade.push(feldId(abschnitt.id, null, feld.key));
  }
  return meldungen.filter(
    (m) => !pfade.some((pfad) => m.pfad === pfad || m.pfad.startsWith(`${pfad}.`)),
  );
}

// --- Verlauf -------------------------------------------------------------------------------------

export interface AenderungsOrt {
  /** „Serie 2 · Zeit“, „Serie 1 · Schuss 3“, „Parcours · Gesamtzeit“; sonst der Pfad */
  text: string;
  /** Beschreibung des Feldes (für die Anzeige des Werts, z. B. Zeit) */
  feld: FeldBeschreibung | null;
}

/** Ort einer Änderung im Verlauf (`sections.x.series[1].shots[2]`) in Worten der Maske. */
export function aenderungsOrt(
  form: Formular,
  pfad: string,
  schussText: (nr: number) => string,
): AenderungsOrt {
  const teile = normalerPfad(pfad).split(".");
  const abschnitt = form.sections.find((a) => a.id === teile[1]);
  if (teile[0] !== "sections" || !abschnitt) return { text: pfad, feld: null };
  if (teile[2] === "series" && teile[3] !== undefined) {
    const serie = abschnitt.series.find((s) => s.index === Number(teile[3]));
    if (!serie) return { text: pfad, feld: null };
    const key = teile[4];
    if (!key) return { text: serie.label, feld: null };
    const feld = serie.fields.find((f) => f.key === key) ?? null;
    if (key === "shots" && teile[5] !== undefined) {
      return { text: `${serie.label} · ${schussText(Number(teile[5]) + 1)}`, feld };
    }
    return { text: `${serie.label} · ${feld?.label ?? key}`, feld };
  }
  const key = teile[2];
  const feld = abschnitt.fields.find((f) => f.key === key) ?? null;
  return { text: `${abschnitt.name} · ${feld?.label ?? key ?? ""}`, feld };
}
