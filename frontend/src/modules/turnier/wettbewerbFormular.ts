import type { Abschnitt, Variante } from "../../api/typen";
import i18n, { aktiveSprache } from "../../i18n";
import type {
  Definition,
  Erfassungsart,
  MehrfachRegel,
  Planung,
  Wettbewerb,
  WettbewerbAenderung,
} from "./typen";

/**
 * Formular eines Wettbewerbs und die Umwandlung von und zur API. Feldnamen der Fehler entsprechen
 * den API-Feldern, damit Meldungen des Servers am richtigen Feld landen.
 */
export interface WettbewerbFormular {
  name: string;
  range_id: string | null;
  capture_mode: Erfassungsart;
  multi_start: boolean;
  max_starts: number;
  multi_start_rule: MehrfachRegel;
  /** Cent; `null` = Feld leer */
  fee_first_cents: number | null;
  fee_repeat_cents: number | null;
  class_ids: string[];
  combined_ranking: boolean;
  planning: Planung;
  heat_minutes: number | null;
  changeover_minutes: number;
  abschnitte: Abschnitt[];
}

export type AbschnittFeld = keyof Abschnitt;

/** Wie ein Feld eines Abschnitts eingegeben wird. */
export type FeldArt =
  | "ganz"
  | "sekunden"
  | "meter"
  | "schalter"
  | "liste_sekunden"
  | "liste_meter"
  | "liste_ganz";

export interface FeldBeschreibung {
  feld: AbschnittFeld;
  art: FeldArt;
  gruppe: "serien" | "schuss" | "zeit" | "zuschlag" | "wertung";
  /** Liste mit einem Wert je Serie */
  jeSerie?: boolean;
}

/**
 * Felder eines Abschnitts, die das Formular kennt, in Anzeigereihenfolge. Angezeigt wird nur, was
 * der Abschnitt hat (oder im Katalog hat). `positionen` bleibt unverändert erhalten.
 */
export const ABSCHNITT_FELDER: readonly FeldBeschreibung[] = [
  { feld: "serien", art: "ganz", gruppe: "serien" },
  { feld: "schuss_je_serie", art: "ganz", gruppe: "schuss" },
  { feld: "max_schuss_je_serie", art: "ganz", gruppe: "schuss" },
  { feld: "ziele_je_serie", art: "ganz", gruppe: "schuss" },
  { feld: "ringwerte", art: "liste_ganz", gruppe: "schuss" },
  { feld: "distanzen_m", art: "liste_meter", gruppe: "schuss", jeSerie: true },
  { feld: "zeit_je_serie_s", art: "sekunden", gruppe: "zeit" },
  { feld: "zeiten_s", art: "liste_sekunden", gruppe: "zeit", jeSerie: true },
  { feld: "max_zeit_je_serie_s", art: "sekunden", gruppe: "zeit" },
  { feld: "zeit_je_schuss_s", art: "sekunden", gruppe: "zeit" },
  { feld: "pause_zwischen_schuessen_s", art: "sekunden", gruppe: "zeit" },
  { feld: "sollzeit_s", art: "sekunden", gruppe: "zeit" },
  { feld: "max_gesamtzeit_s", art: "sekunden", gruppe: "zeit" },
  { feld: "zeit_bei_abbruch_s", art: "sekunden", gruppe: "zeit" },
  { feld: "zeit_wird_gemessen", art: "schalter", gruppe: "zeit" },
  { feld: "zuschlag_je_stehender_scheibe_s", art: "sekunden", gruppe: "zuschlag" },
  { feld: "zuschlag_stoerung_vor_erstem_schuss_s", art: "sekunden", gruppe: "zuschlag" },
];

/** Turnier-Einstellungen je Abschnitt; gibt es immer, auch wenn der Katalog sie nicht setzt. */
export const TURNIER_FELDER = ["serien_gewertet", "trefferaufnahme_nach"] as const;

const LISTEN_JE_SERIE = ["zeiten_s", "distanzen_m", "positionen"] as const;

function kopie<T>(wert: T): T {
  return structuredClone(wert);
}

export function ausWettbewerb(wettbewerb: Wettbewerb): WettbewerbFormular {
  return {
    name: wettbewerb.name,
    range_id: wettbewerb.range_id,
    capture_mode: wettbewerb.capture_mode,
    multi_start: wettbewerb.multi_start,
    max_starts: wettbewerb.max_starts,
    multi_start_rule: wettbewerb.multi_start_rule,
    fee_first_cents: wettbewerb.fee_first_cents,
    fee_repeat_cents: wettbewerb.fee_repeat_cents,
    class_ids: [...wettbewerb.class_ids],
    combined_ranking: wettbewerb.combined_ranking,
    planning: wettbewerb.planning,
    heat_minutes: wettbewerb.heat_minutes,
    changeover_minutes: wettbewerb.changeover_minutes,
    abschnitte: kopie(wettbewerb.definition.variant.abschnitte),
  };
}

/** Entfernt leere Felder: Die API speichert nicht gesetzte Katalogfelder gar nicht erst. */
export function bereinigeAbschnitt(abschnitt: Abschnitt): Abschnitt {
  const ergebnis: Record<string, unknown> = {};
  for (const [feld, wert] of Object.entries(abschnitt)) {
    if (wert === null || wert === undefined) continue;
    if (Array.isArray(wert) && wert.length === 0 && feld === "trefferaufnahme_nach") continue;
    ergebnis[feld] = wert;
  }
  return ergebnis as Abschnitt;
}

function gleich(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function ablaufGeaendert(formular: WettbewerbFormular, wettbewerb: Wettbewerb): boolean {
  return !gleich(
    formular.abschnitte.map(bereinigeAbschnitt),
    wettbewerb.definition.variant.abschnitte.map(bereinigeAbschnitt),
  );
}

/**
 * Wertungsrelevante Änderung (Backend `SCORING_FIELDS`): Ablauf, Erfassungsart, Mehrfachstart und
 * gemeinsame Wertung. Bei einem laufenden Turnier verlangt der Server dafür einen Grund.
 */
export function wertungGeaendert(formular: WettbewerbFormular, wettbewerb: Wettbewerb): boolean {
  const neu = aenderungen(formular, wettbewerb);
  return (
    neu.definition !== undefined ||
    neu.capture_mode !== undefined ||
    neu.multi_start !== undefined ||
    neu.max_starts !== undefined ||
    neu.multi_start_rule !== undefined ||
    neu.combined_ranking !== undefined
  );
}

/** Nur die geänderten Felder als Teiländerung für `PATCH …/competitions/{id}`. */
export function aenderungen(
  formular: WettbewerbFormular,
  wettbewerb: Wettbewerb,
): WettbewerbAenderung {
  const neu: WettbewerbAenderung = {};
  const name = formular.name.trim();
  if (name !== wettbewerb.name) neu.name = name;
  if (formular.range_id !== wettbewerb.range_id) neu.range_id = formular.range_id;
  if (formular.capture_mode !== wettbewerb.capture_mode) neu.capture_mode = formular.capture_mode;
  if (formular.multi_start !== wettbewerb.multi_start) neu.multi_start = formular.multi_start;
  const maxStarts = formular.multi_start ? formular.max_starts : 1;
  if (maxStarts !== wettbewerb.max_starts) neu.max_starts = maxStarts;
  if (formular.multi_start_rule !== wettbewerb.multi_start_rule) {
    neu.multi_start_rule = formular.multi_start_rule;
  }
  if (
    formular.fee_first_cents !== null &&
    formular.fee_first_cents !== wettbewerb.fee_first_cents
  ) {
    neu.fee_first_cents = formular.fee_first_cents;
  }
  if (
    formular.fee_repeat_cents !== null &&
    formular.fee_repeat_cents !== wettbewerb.fee_repeat_cents
  ) {
    neu.fee_repeat_cents = formular.fee_repeat_cents;
  }
  if (!gleich([...formular.class_ids].sort(), [...wettbewerb.class_ids].sort())) {
    neu.class_ids = formular.class_ids;
  }
  if (formular.combined_ranking !== wettbewerb.combined_ranking) {
    neu.combined_ranking = formular.combined_ranking;
  }
  if (formular.planning !== wettbewerb.planning) neu.planning = formular.planning;
  if (formular.heat_minutes !== wettbewerb.heat_minutes) neu.heat_minutes = formular.heat_minutes;
  if (formular.changeover_minutes !== wettbewerb.changeover_minutes) {
    neu.changeover_minutes = formular.changeover_minutes;
  }
  if (ablaufGeaendert(formular, wettbewerb)) neu.definition = neueDefinition(formular, wettbewerb);
  return neu;
}

/** Definition mit dem geänderten Ablauf. `source` bleibt weg; der Server behält die Herkunft. */
export function neueDefinition(formular: WettbewerbFormular, wettbewerb: Wettbewerb): Definition {
  const { source: _herkunft, ...rest } = wettbewerb.definition;
  return {
    ...rest,
    variant: {
      ...wettbewerb.definition.variant,
      abschnitte: formular.abschnitte.map(bereinigeAbschnitt),
    },
  };
}

// --- Ablauf bearbeiten -------------------------------------------------------------------------

/** Passt die Listen „je Serie“ an eine neue Serienzahl an (kürzen oder letzten Wert wiederholen). */
export function setzeSerien(abschnitt: Abschnitt, serien: number): Abschnitt {
  const neu: Abschnitt = { ...abschnitt, serien };
  for (const feld of LISTEN_JE_SERIE) {
    const liste = abschnitt[feld] as unknown[] | null | undefined;
    if (!Array.isArray(liste) || liste.length === 0) continue;
    const angepasst = liste.slice(0, serien);
    while (angepasst.length < serien) angepasst.push(kopie(liste[liste.length - 1]));
    (neu as Record<string, unknown>)[feld] = angepasst;
  }
  if (typeof neu.serien_gewertet === "number" && neu.serien_gewertet > serien) {
    neu.serien_gewertet = serien;
  }
  if (Array.isArray(neu.trefferaufnahme_nach)) {
    neu.trefferaufnahme_nach = neu.trefferaufnahme_nach.filter((nr) => nr <= serien);
  }
  return neu;
}

/** Schaltet „Trefferaufnahme nach Serie n“ um; die Liste bleibt aufsteigend. */
export function schalteTrefferaufnahme(abschnitt: Abschnitt, serie: number): Abschnitt {
  const vorher = abschnitt.trefferaufnahme_nach ?? [];
  const neu = vorher.includes(serie)
    ? vorher.filter((nr) => nr !== serie)
    : [...vorher, serie].sort((a, b) => a - b);
  return { ...abschnitt, trefferaufnahme_nach: neu.length > 0 ? neu : null };
}

/** Felder, die für einen Abschnitt angezeigt werden: was er hat oder im Katalog hat. */
export function sichtbareFelder(
  abschnitt: Abschnitt,
  original: Abschnitt | undefined,
  katalog: Abschnitt | undefined,
): FeldBeschreibung[] {
  const vorhanden = (quelle: Abschnitt | undefined, feld: AbschnittFeld) =>
    quelle !== undefined && quelle[feld] !== null && quelle[feld] !== undefined;
  return ABSCHNITT_FELDER.filter(
    ({ feld }) =>
      feld === "serien" ||
      vorhanden(abschnitt, feld) ||
      vorhanden(original, feld) ||
      vorhanden(katalog, feld),
  );
}

// --- Prüfen ------------------------------------------------------------------------------------

export const abschnittPfad = (index: number, feld?: string) =>
  `definition.variant.abschnitte.${index}${feld ? `.${feld}` : ""}`;

function istPositiv(wert: unknown): boolean {
  return typeof wert === "number" && Number.isFinite(wert) && wert > 0;
}

/**
 * Prüft das Formular vor dem Senden. Ergebnis: Feldpfad → Meldung (leer = alles in Ordnung).
 * Die Regeln entsprechen denen des Servers; der Server prüft trotzdem selbst.
 */
export function pruefeFormular(formular: WettbewerbFormular): Record<string, string> {
  const t = i18n.getFixedT(aktiveSprache(), "turnier", "pruefung");
  const fehler: Record<string, string> = {};
  if (formular.name.trim() === "") fehler.name = t("pflicht");
  if (formular.fee_first_cents === null) fehler.fee_first_cents = t("betrag");
  if (formular.multi_start && formular.fee_repeat_cents === null) {
    fehler.fee_repeat_cents = t("betrag");
  }
  if (formular.multi_start && !(formular.max_starts >= 2)) fehler.max_starts = t("max_starts");
  if (formular.planning === "schedule" && !istPositiv(formular.heat_minutes)) {
    fehler.heat_minutes = t("durchgang");
  }
  if (!(formular.changeover_minutes >= 0)) fehler.changeover_minutes = t("nicht_negativ");

  formular.abschnitte.forEach((abschnitt, index) => {
    const pfad = (feld: string) => abschnittPfad(index, feld);
    if (!Number.isInteger(abschnitt.serien) || abschnitt.serien < 1) {
      fehler[pfad("serien")] = t("serien");
      return;
    }
    if (
      abschnitt.serien_gewertet !== null &&
      abschnitt.serien_gewertet !== undefined &&
      (abschnitt.serien_gewertet < 1 || abschnitt.serien_gewertet > abschnitt.serien)
    ) {
      fehler[pfad("serien_gewertet")] = t("serien_gewertet", { serien: abschnitt.serien });
    }
    for (const { feld, art } of ABSCHNITT_FELDER) {
      const wert = abschnitt[feld];
      if (wert === null || wert === undefined || feld === "serien") continue;
      if (art === "schalter") continue;
      if (art === "liste_ganz") {
        const liste = wert as number[];
        const absteigend = liste.every((zahl, i) => i === 0 || (liste[i - 1] ?? 0) > zahl);
        if (liste.length === 0 || !absteigend || liste.some((zahl) => !Number.isInteger(zahl))) {
          fehler[pfad(feld)] = t("ringwerte");
        }
        continue;
      }
      if (art === "liste_sekunden" || art === "liste_meter") {
        if ((wert as unknown[]).some((eintrag) => !istPositiv(eintrag))) {
          fehler[pfad(feld)] = t("liste_positiv");
        }
        continue;
      }
      const erlaubtNull = feld === "zuschlag_je_stehender_scheibe_s";
      const ok = erlaubtNull ? typeof wert === "number" && wert >= 0 : istPositiv(wert);
      if (!ok || (art === "ganz" && !Number.isInteger(wert))) {
        fehler[pfad(feld)] = art === "ganz" ? t("ganz_positiv") : t("positiv");
      }
    }
  });
  return fehler;
}

/** Alle Feldpfade, die das Formular zeigen kann; für die Zuordnung der Serverfehler. */
export function bekannteFelder(formular: WettbewerbFormular): string[] {
  const felder = [
    "name",
    "range_id",
    "capture_mode",
    "multi_start",
    "max_starts",
    "multi_start_rule",
    "fee_first_cents",
    "fee_repeat_cents",
    "class_ids",
    "combined_ranking",
    "planning",
    "heat_minutes",
    "changeover_minutes",
    "reason",
  ];
  formular.abschnitte.forEach((_, index) => {
    felder.push(abschnittPfad(index));
    for (const { feld } of ABSCHNITT_FELDER) felder.push(abschnittPfad(index, feld));
    for (const feld of TURNIER_FELDER) felder.push(abschnittPfad(index, feld));
  });
  return felder;
}

// --- Aufteilung des Formulars -------------------------------------------------------------------

/** Felder, die immer sichtbar oben stehen: was fast jeder Wettbewerb braucht. */
const FELDER_OBEN = [
  "range_id",
  "fee_first_cents",
  "fee_repeat_cents",
  "multi_start",
  "max_starts",
  "class_ids",
] as const;

/**
 * Liegt ein Feld (API-Name oder Fehlerpfad) im zugeklappten Teil „Erweitert“? Der Name steht bei
 * eigenen Wettbewerben oben, bei Katalog-Wettbewerben unter „Erweitert“. Allgemeine Fehler (`""`)
 * und der Grund gehören zu keinem Teil.
 */
export function erweiterteFelder(ausKatalog: boolean): (feld: string) => boolean {
  const oben = new Set<string>([...FELDER_OBEN, "", "reason"]);
  if (!ausKatalog) oben.add("name");
  return (feld) => !oben.has(feld);
}

// --- Abweichungen vom Katalog -------------------------------------------------------------------

export interface Abweichung {
  abschnitt: string;
  feld: string;
  katalog: unknown;
  turnier: unknown;
}

/**
 * Vergleicht den Ablauf mit der Katalog-Variante gleicher ID. Ohne Katalogvariante (eigener
 * Wettbewerb oder Variante nicht mehr im Katalog) gibt es nichts zu vergleichen: `null`.
 */
export function abweichungen(
  abschnitte: readonly Abschnitt[],
  katalog: Variante | undefined,
): Abweichung[] | null {
  if (!katalog) return null;
  const liste: Abweichung[] = [];
  const katalogNachId = new Map(katalog.abschnitte.map((eintrag) => [eintrag.id, eintrag]));
  for (const abschnitt of abschnitte) {
    const vorlage = katalogNachId.get(abschnitt.id);
    const eigen = bereinigeAbschnitt(abschnitt) as Record<string, unknown>;
    const kat = (vorlage ? bereinigeAbschnitt(vorlage) : {}) as Record<string, unknown>;
    for (const feld of new Set([...Object.keys(eigen), ...Object.keys(kat)])) {
      if (feld === "id" || feld === "name") continue;
      if (!gleich(eigen[feld], kat[feld])) {
        liste.push({ abschnitt: abschnitt.id, feld, katalog: kat[feld], turnier: eigen[feld] });
      }
    }
  }
  return liste;
}
