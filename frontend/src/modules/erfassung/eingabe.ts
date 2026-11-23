/**
 * Tastenlogik des Terminals: Ziffernfeld und Hardware-Tastatur, ohne React, einzeln getestet.
 *
 * - Zahlen (stehende Scheiben, Seriensumme, Zehner): Ziffern tippen; kann keine weitere Ziffer den
 *   Wert noch ändern (Höchstwert erreicht oder „0“), schaltet das Terminal von selbst weiter. Bei
 *   einstelligen Feldern (z. B. stehende Scheiben 0 bis 5) also nach jeder Ziffer, auch nach „0“.
 * - „Weiter“ direkt nach dem selbsttätigen Weiterschalten bestätigt nur und bleibt im neuen Feld:
 *   Wer aus Gewohnheit nach der Ziffer noch Enter oder „Weiter“ drückt, überspringt kein Feld.
 *   Ebenso ein Komma mit Nullen: Wer den Höchstwert ausschreibt („109,0“), hat nach „109“ schon
 *   das nächste Feld; „,0“ gehört noch zum vorigen Wert und landet nicht als „0“ im nächsten.
 * - Selbsttätig weiter geht es nur in ein leeres Feld. Hat das nächste Feld schon einen Wert, bleibt
 *   das Terminal stehen (Hinweis); erst Enter oder ein Tipp auf das Feld führt dorthin. So wird nie
 *   ein vorhandener Wert ohne ausdrückliche Auswahl überschrieben.
 * - Rück löscht nur im aktiven Feld; in einem leeren Feld passiert nichts (kein Sprung zurück).
 * - Zeiten: Sekunden mit Komma („12,84“), an den Server in Hundertstelsekunden (1284).
 * - Schüsse: erlaubte Werte als Tasten; auf der Tastatur „1“ „0“ für 10 und „x“ für den Innenzehner.
 * - Kommazahlen (Zehntelwertung: Schüsse mit `decimals`, Seriensumme `decimal`): Komma, Punkt oder
 *   Komma des Ziffernblocks; Grenzen aus `value_min`/`value_max`/`zero_allowed`. Gerechnet wird in
 *   ganzen Einheiten (Zehnteln), an den Server geht Text mit Punkt („10.4“), nie eine
 *   Gleitkommazahl. Weiter geht es erst, wenn keine Ziffer den Wert mehr ändern kann (nach der
 *   Zehntelstelle oder nach einer „0“, die nur 0 bleiben kann). Passt eine Ziffer nur hinter das
 *   Komma („9“ „8“ bei höchstens 10,9), steht das Komma von selbst: „9,8“.
 */
import { formatDezimal, formatHundertstel } from "../../lib/format";
import type { FeldBeschreibung } from "./api";
import type { Schusswert } from "./rohwerte";

export type Taste =
  | { art: "ziffer"; ziffer: string }
  | { art: "komma" }
  | { art: "loeschen" }
  | { art: "weiter" }
  | { art: "zurueck" };

/** Eingabe in einem Zahlen- oder Zeitfeld. `frisch`: Der nächste Tastendruck ersetzt den Wert. */
export interface ZahlEingabe {
  text: string;
  frisch: boolean;
  /** Feld eben durch selbsttätiges Weiterschalten erreicht: „Weiter“ bestätigt nur. */
  angekommen?: boolean;
  /**
   * Wert fertig, aber das nächste Feld hat schon einen Wert: Weitere Ziffern gehören vermutlich
   * dorthin und werden abgelehnt, statt diesen Wert zu ändern. Rück, Enter oder Antippen lösen das.
   */
  voll?: boolean;
  /**
   * Nach dem selbsttätigen Weiterschalten kam ein Komma: Es und folgende Nullen gehören noch zum
   * vorigen Wert („109,0“) und werden übergangen. Die erste andere Ziffer beginnt neu.
   */
  nachlauf?: boolean;
}

export const FRISCH: ZahlEingabe = { text: "", frisch: true };
/** Eingabe im Feld, das nach selbsttätigem Weiterschalten aktiv ist. */
export const ANGEKOMMEN: ZahlEingabe = { text: "", frisch: true, angekommen: true };

/**
 * Kurzer Hinweis am Ziffernfeld: warum eine Taste nicht passt, oder („naechstes_belegt“) warum das
 * Terminal nicht selbst weitergeschaltet hat.
 */
export type Ablehnung = "zu_gross" | "zu_klein" | "leer" | "unpassend" | "naechstes_belegt";

export interface ZahlErgebnis {
  eingabe: ZahlEingabe;
  /**
   * Neuer Wert des Feldes (`undefined` = leer); nur gesetzt, wenn `geaendert`. Zahl bei ganzen
   * Zahlen und Zeiten, Text mit Punkt („10.4“) bei Kommazahlen.
   */
  wert?: number | string;
  geaendert: boolean;
  /**
   * Zum nächsten Feld weiterschalten; `eingabe` ist dann die Eingabe für das neue Feld
   * (`ANGEKOMMEN` nach selbsttätigem Weiterschalten, sonst `FRISCH`).
   */
  weiter: boolean;
  /** Zum vorigen Feld (nur mit der Taste „zurück“, nie durch Löschen) */
  zurueck: boolean;
  /** Taste passt nicht (z. B. Wert über dem Höchstwert) */
  abgelehnt: boolean;
  grund?: Ablehnung;
}

const MAX_SEKUNDEN_STELLEN = 4;

/** Komma direkt nach dem selbsttätigen Weiterschalten: übergehen (siehe `ZahlEingabe.nachlauf`). */
const NACHLAUF: ZahlEingabe = { ...ANGEKOMMEN, nachlauf: true };

/**
 * Nachlauf des vorigen Werts („,0“ nach „109“): Komma direkt nach dem Ankommen und Nullen danach
 * werden übergangen. Sonst `null`; eine andere Ziffer beginnt dann frisch.
 */
function nachlauf(eingabe: ZahlEingabe, taste: Taste): ZahlErgebnis | null {
  if (taste.art === "komma" && eingabe.angekommen && !eingabe.nachlauf) {
    return ergebnis({ eingabe: NACHLAUF });
  }
  if (eingabe.nachlauf && taste.art === "ziffer" && taste.ziffer === "0") {
    return ergebnis({ eingabe: NACHLAUF });
  }
  // „109,0“ und dann Enter: bestätigt wie direkt nach dem Ankommen, springt nicht.
  if (eingabe.nachlauf && taste.art === "weiter") return ergebnis({ eingabe: FRISCH });
  return null;
}

/** Hundertstelsekunden als Eingabetext: `1284` → „12,84“ (Komma der aktiven Sprache). */
export function zeitText(hundertstel: number): string {
  return formatHundertstel(hundertstel).replace(/\s/g, "");
}

/** „12,84“ oder „12.84“ → 1284; „12,“ → 1200; leer oder unlesbar → `undefined`. */
export function zeitAusText(text: string): number | undefined {
  const treffer = /^(\d*)(?:[.,](\d{0,2}))?$/.exec(text.trim());
  if (!treffer || text.trim() === "" || (treffer[1] === "" && !treffer[2])) return undefined;
  const sekunden = Number(treffer[1] || "0");
  const hundertstel = Number((treffer[2] ?? "").padEnd(2, "0"));
  return sekunden * 100 + hundertstel;
}

export function ganzAusText(text: string): number | undefined {
  return /^\d+$/.test(text) ? Number(text) : undefined;
}

// --- Kommazahlen ---------------------------------------------------------------------------------

/**
 * Ob ein Feld Kommazahlen nimmt: Seriensumme `decimal` oder Schüsse mit Nachkommastellen ohne
 * feste Ringwerte (Zehntelwertung). Ganze Ringe (BDS) sind es nie.
 */
export function istKommaFeld(feld: FeldBeschreibung): boolean {
  if (feld.kind === "decimal") return true;
  return (
    feld.kind === "shots" && (feld.decimals ?? 0) > 0 && (feld.allowed_values ?? []).length === 0
  );
}

/** Ein Wert je Ziel (Treffer 1, Fehler 0) statt Ringen je Schuss. */
export function istJeZiel(feld: FeldBeschreibung): boolean {
  return feld.kind === "shots" && feld.per_target === true;
}

/** Nachkommastellen eines Kommafelds (Zehntelwertung: 1). */
export function stellenVon(feld: FeldBeschreibung): number {
  return Math.max(0, feld.decimals ?? (feld.kind === "decimal" ? 1 : 0));
}

/**
 * Kommazahl als ganze Zahl in Einheiten der letzten Stelle („10,4“ bei 1 Stelle → 104). Nimmt Text
 * mit Komma oder Punkt und Zahlen; mehr Nachkommastellen als erlaubt (außer Nullen), negativ oder
 * unlesbar → `undefined`. So wird nie mit Gleitkommazahlen gerechnet.
 */
export function einheitenAus(wert: unknown, stellen: number): number | undefined {
  if (typeof wert === "number") {
    if (!Number.isFinite(wert) || wert < 0) return undefined;
    const einheiten = Math.round(wert * 10 ** stellen);
    return Math.abs(einheiten - wert * 10 ** stellen) < 1e-6 ? einheiten : undefined;
  }
  if (typeof wert !== "string") return undefined;
  const treffer = /^(\d*)(?:[.,](\d*))?$/.exec(wert.trim());
  if (!treffer) return undefined;
  const ganz = treffer[1] ?? "";
  const nach = (treffer[2] ?? "").replace(/0+$/, "");
  if (ganz === "" && (treffer[2] ?? "") === "") return undefined;
  if (nach.length > stellen) return undefined;
  return Number(ganz || "0") * 10 ** stellen + Number(nach.padEnd(stellen, "0") || "0");
}

/** Einheiten → Text für den Server: 104 → „10.4“, 0 → „0.0“ (bei 1 Stelle). */
export function einheitenRoh(einheiten: number, stellen: number): string {
  if (stellen === 0) return String(einheiten);
  const teiler = 10 ** stellen;
  return `${Math.floor(einheiten / teiler)}.${String(einheiten % teiler).padStart(stellen, "0")}`;
}

/** Einheiten → Anzeige in der Schreibweise der Sprache: 104 → „10,4“, 10909 → „1.090,9“. */
export function einheitenText(einheiten: number, stellen: number): string {
  return formatDezimal(einheiten / 10 ** stellen, stellen);
}

/** Summe von Kommazahlen in Einheiten (ganzzahlig, ohne Gleitkommafehler); Unlesbares zählt nicht. */
export function summeEinheiten(werte: readonly unknown[], stellen: number): number {
  return werte.reduce<number>((summe, wert) => summe + (einheitenAus(wert, stellen) ?? 0), 0);
}

export interface KommaGrenzen {
  stellen: number;
  /** Untergrenze in Einheiten (ohne die 0, die `null` zusätzlich erlaubt) */
  min: number | null;
  max: number | null;
  /** 0 ist zusätzlich zum Bereich erlaubt (Fehlschuss) */
  null: boolean;
}

export function kommaGrenzen(feld: FeldBeschreibung): KommaGrenzen {
  const stellen = stellenVon(feld);
  const lesen = (wert: string | null | undefined) =>
    wert == null ? null : (einheitenAus(String(wert), stellen) ?? null);
  return {
    stellen,
    min: lesen(feld.value_min),
    max: lesen(feld.value_max),
    null: feld.zero_allowed === true,
  };
}

function imBereich(einheiten: number, g: KommaGrenzen): boolean {
  if (g.max !== null && einheiten > g.max) return false;
  if (g.null && einheiten === 0) return true;
  return g.min === null || einheiten >= g.min;
}

/** Grenzen als Text für Hinweise: `{ min: "1,0", max: "10,9", null: true }`. */
export function kommaBereich(feld: FeldBeschreibung): {
  min: string | null;
  max: string | null;
  null: boolean;
} {
  const g = kommaGrenzen(feld);
  return {
    min: g.min === null ? null : einheitenText(g.min, g.stellen),
    max: g.max === null ? null : einheitenText(g.max, g.stellen),
    // „0 oder 1,0 bis 10,9“ nur, wenn die 0 nicht ohnehin im Bereich liegt.
    null: g.null && (g.min ?? 0) > 0,
  };
}

/** Ziffer an eine Kommazahl hängen; `null`, wenn keine Stelle mehr frei ist. */
function kommaAnhaengen(text: string, ziffer: string, g: KommaGrenzen): string | null {
  if (/[.,]/.test(text)) {
    const nach = text.split(/[.,]/)[1] ?? "";
    return nach.length >= g.stellen ? null : text + ziffer;
  }
  // „05“ ist keine Zahl: Nach einer „0“ kann nur das Komma kommen.
  if (text === "0") return g.stellen > 0 ? `0,${ziffer}` : null;
  const kandidat = text + ziffer;
  // Passt die Ziffer nur hinter das Komma (9 + 8 bei höchstens 10,9), steht das Komma von selbst.
  const einheiten = einheitenAus(kandidat, g.stellen);
  if (
    text !== "" &&
    g.stellen > 0 &&
    g.max !== null &&
    einheiten !== undefined &&
    einheiten > g.max
  ) {
    return `${text},${ziffer}`;
  }
  return kandidat;
}

function kommaVollstaendig(text: string, g: KommaGrenzen): boolean {
  return (text.split(/[.,]/)[1] ?? "").length >= g.stellen && /[.,]/.test(text);
}

/**
 * Ob eine weitere Taste (Ziffer oder Komma mit Ziffer) den Wert noch ändern kann. Sonst ist er
 * fertig, und das Feld schaltet weiter: nach der Zehntelstelle, nach „0“ bei „0 oder 1,0 bis 10,9“.
 */
function kommaKannWachsen(text: string, g: KommaGrenzen): boolean {
  const jetzt = einheitenAus(text, g.stellen);
  const moeglich = (kandidat: string | null) => {
    if (kandidat === null) return false;
    const einheiten = einheitenAus(kandidat, g.stellen);
    if (einheiten === undefined || einheiten === jetzt) return false;
    if (g.max !== null && einheiten > g.max) return false;
    return !kommaVollstaendig(kandidat, g) || imBereich(einheiten, g);
  };
  for (let ziffer = 0; ziffer <= 9; ziffer++) {
    if (moeglich(kommaAnhaengen(text, String(ziffer), g))) return true;
    if (g.stellen > 0 && !/[.,]/.test(text) && moeglich(`${text || "0"},${ziffer}`)) return true;
  }
  return false;
}

/** Wert zum Speichern aus dem Eingabetext: Text mit Punkt, oder `undefined` (leer, noch kein Wert). */
function kommaWert(text: string, g: KommaGrenzen): string | undefined {
  // „0,“ oder „,“ allein ist noch keine Zahl: kein Fehlschuss, nur weil das Komma getippt wurde.
  if (/^0?[.,]$/.test(text)) return undefined;
  const einheiten = einheitenAus(text, g.stellen);
  if (einheiten === undefined || !imBereich(einheiten, g)) return undefined;
  return einheitenRoh(einheiten, g.stellen);
}

// --- Anzeige und Text der Felder -----------------------------------------------------------------

/** Anzeigetext eines Feldwerts. */
export function wertText(feld: FeldBeschreibung, wert: unknown): string {
  if (wert === undefined || wert === null) return "";
  if (feld.kind === "time" && typeof wert === "number") return zeitText(wert);
  if (istKommaFeld(feld)) {
    const einheiten = einheitenAus(wert, stellenVon(feld));
    return einheiten === undefined ? String(wert) : einheitenText(einheiten, stellenVon(feld));
  }
  return String(wert);
}

function textAus(feld: FeldBeschreibung, wert: unknown): string {
  if (wert === undefined || wert === null) return "";
  if (istKommaFeld(feld)) {
    const einheiten = einheitenAus(wert, stellenVon(feld));
    // Zum Bearbeiten ohne Tausenderpunkte, mit Komma.
    return einheiten === undefined
      ? ""
      : einheitenRoh(einheiten, stellenVon(feld)).replace(".", ",");
  }
  if (typeof wert !== "number") return "";
  // Zum Bearbeiten ohne Tausenderpunkte, Komma bleibt.
  return feld.kind === "time" ? zeitText(wert).replace(/\./g, "") : String(wert);
}

function wertAusText(feld: FeldBeschreibung, text: string): number | undefined {
  return feld.kind === "time" ? zeitAusText(text) : ganzAusText(text);
}

function ergebnis(teil: Partial<ZahlErgebnis> & { eingabe: ZahlEingabe }): ZahlErgebnis {
  return { geaendert: false, weiter: false, zurueck: false, abgelehnt: false, ...teil };
}

/**
 * Ob eine weitere Ziffer den Wert noch ändern kann (sonst schaltet das Feld weiter). „0“ kann nicht
 * mehr wachsen (führende Nullen fallen weg); über dem Höchstwert passt nichts mehr.
 */
function weitereZifferMoeglich(feld: FeldBeschreibung, wert: number): boolean {
  if (feld.kind !== "integer") return true;
  if (wert === 0) return false;
  if (feld.max == null) return true;
  return wert * 10 <= feld.max;
}

/**
 * Eine Taste in einem Zahlen- oder Zeitfeld. `aktuell`: gespeicherter Wert des Feldes;
 * `naechstesBelegt`: Das Feld danach hat schon einen Wert (dann kein selbsttätiges Weiterschalten).
 */
export function zahlTaste(
  feld: FeldBeschreibung,
  eingabe: ZahlEingabe,
  aktuell: unknown,
  taste: Taste,
  naechstesBelegt = false,
): ZahlErgebnis {
  const uebergangen = nachlauf(eingabe, taste);
  if (uebergangen) return uebergangen;
  if (eingabe.nachlauf) eingabe = { ...eingabe, angekommen: false, nachlauf: false };
  if (istKommaFeld(feld)) return kommaTaste(feld, eingabe, aktuell, taste, naechstesBelegt);
  const zeit = feld.kind === "time";
  switch (taste.art) {
    case "weiter":
      // Gerade selbsttätig hierher gekommen: „Weiter“ bestätigt das vorige Feld, springt nicht.
      if (eingabe.angekommen) return ergebnis({ eingabe: FRISCH });
      return ergebnis({ eingabe: FRISCH, weiter: true });
    case "zurueck":
      return ergebnis({ eingabe: FRISCH, zurueck: true });
    case "loeschen": {
      const basis = eingabe.frisch ? textAus(feld, aktuell) : eingabe.text;
      // Leeres Feld: nichts tun. Rück springt nie ins vorige Feld und löscht dort weiter.
      if (basis === "") return ergebnis({ eingabe: FRISCH, abgelehnt: true, grund: "leer" });
      const text = basis.slice(0, -1);
      const wert = wertAusText(feld, text);
      return ergebnis({
        eingabe: { text, frisch: false },
        wert: zeit && wert === 0 ? undefined : wert,
        geaendert: true,
      });
    }
    case "komma": {
      if (!zeit) return ergebnis({ eingabe, abgelehnt: true, grund: "unpassend" });
      const basis = eingabe.frisch ? "" : eingabe.text;
      if (/[.,]/.test(basis)) return ergebnis({ eingabe, abgelehnt: true, grund: "unpassend" });
      const text = `${basis || "0"},`;
      const wert = wertAusText(feld, text);
      return ergebnis({
        eingabe: { text, frisch: false },
        wert: wert === 0 ? undefined : wert,
        geaendert: true,
      });
    }
    case "ziffer": {
      if (!/^\d$/.test(taste.ziffer)) return ergebnis({ eingabe, abgelehnt: true });
      if (eingabe.voll) return ergebnis({ eingabe, abgelehnt: true, grund: "naechstes_belegt" });
      const basis = eingabe.frisch ? "" : eingabe.text;
      let text = basis + taste.ziffer;
      if (zeit) {
        const [ganz = "", nach] = text.split(/[.,]/);
        if (ganz.replace(/^0+(?=\d)/, "").length > MAX_SEKUNDEN_STELLEN) {
          return ergebnis({ eingabe, abgelehnt: true });
        }
        if (nach !== undefined && nach.length > 2) return ergebnis({ eingabe, abgelehnt: true });
      } else {
        text = text.replace(/^0+(?=\d)/, "");
      }
      const wert = wertAusText(feld, text);
      if (wert === undefined) return ergebnis({ eingabe, abgelehnt: true });
      // „0,0…“ ist noch keine Zeit; der Server nimmt nur Zeiten über 0.
      if (zeit && wert === 0) {
        return ergebnis({ eingabe: { text, frisch: false }, wert: undefined, geaendert: true });
      }
      if (!zeit && feld.max != null && wert > feld.max) {
        return ergebnis({ eingabe, abgelehnt: true, grund: "zu_gross" });
      }
      const fertig = !zeit && !weitereZifferMoeglich(feld, wert);
      const weiter = fertig && !naechstesBelegt;
      return ergebnis({
        eingabe: weiter
          ? ANGEKOMMEN
          : fertig && naechstesBelegt
            ? { text, frisch: false, voll: true }
            : { text, frisch: false },
        wert,
        geaendert: true,
        weiter,
        ...(fertig && naechstesBelegt ? { grund: "naechstes_belegt" as const } : {}),
      });
    }
  }
}

/** Eine Taste in einem Kommafeld (Zehntelwertung); Ablauf wie bei ganzen Zahlen. */
function kommaTaste(
  feld: FeldBeschreibung,
  eingabe: ZahlEingabe,
  aktuell: unknown,
  taste: Taste,
  naechstesBelegt: boolean,
): ZahlErgebnis {
  const g = kommaGrenzen(feld);
  switch (taste.art) {
    case "weiter":
      if (eingabe.angekommen) return ergebnis({ eingabe: FRISCH });
      return ergebnis({ eingabe: FRISCH, weiter: true });
    case "zurueck":
      return ergebnis({ eingabe: FRISCH, zurueck: true });
    case "loeschen": {
      const basis = eingabe.frisch ? textAus(feld, aktuell) : eingabe.text;
      if (basis === "") return ergebnis({ eingabe: FRISCH, abgelehnt: true, grund: "leer" });
      const text = basis.slice(0, -1);
      return ergebnis({
        eingabe: { text, frisch: false },
        wert: kommaWert(text, g),
        geaendert: true,
      });
    }
    case "komma": {
      if (g.stellen === 0) return ergebnis({ eingabe, abgelehnt: true, grund: "unpassend" });
      if (eingabe.voll) return ergebnis({ eingabe, abgelehnt: true, grund: "naechstes_belegt" });
      const basis = eingabe.frisch ? "" : eingabe.text;
      if (/[.,]/.test(basis)) return ergebnis({ eingabe, abgelehnt: true, grund: "unpassend" });
      const text = `${basis || "0"},`;
      return ergebnis({
        eingabe: { text, frisch: false },
        wert: kommaWert(text, g),
        geaendert: true,
      });
    }
    case "ziffer": {
      if (!/^\d$/.test(taste.ziffer)) return ergebnis({ eingabe, abgelehnt: true });
      if (eingabe.voll) return ergebnis({ eingabe, abgelehnt: true, grund: "naechstes_belegt" });
      const basis = eingabe.frisch ? "" : eingabe.text;
      const text = kommaAnhaengen(basis, taste.ziffer, g);
      if (text === null) return ergebnis({ eingabe, abgelehnt: true, grund: "unpassend" });
      const einheiten = einheitenAus(text, g.stellen);
      if (einheiten === undefined) return ergebnis({ eingabe, abgelehnt: true });
      if (g.max !== null && einheiten > g.max) {
        return ergebnis({ eingabe, abgelehnt: true, grund: "zu_gross" });
      }
      const fertig = !kommaKannWachsen(text, g);
      // Unter der Untergrenze (z. B. „0,5“ bei „0 oder 1,0 bis 10,9“) und nicht mehr zu retten.
      if (!imBereich(einheiten, g) && (fertig || kommaVollstaendig(text, g))) {
        return ergebnis({ eingabe, abgelehnt: true, grund: "zu_klein" });
      }
      const weiter = fertig && !naechstesBelegt;
      return ergebnis({
        eingabe: weiter
          ? ANGEKOMMEN
          : fertig && naechstesBelegt
            ? { text, frisch: false, voll: true }
            : { text, frisch: false },
        wert: kommaWert(text, g),
        geaendert: true,
        weiter,
        ...(fertig && naechstesBelegt ? { grund: "naechstes_belegt" as const } : {}),
      });
    }
  }
}

/** Welche Ziffern im Zahlenfeld gerade passen (für das Ziffernfeld). */
export function zifferErlaubt(
  feld: FeldBeschreibung,
  eingabe: ZahlEingabe,
  ziffer: string,
): boolean {
  return !zahlTaste(feld, eingabe, undefined, { art: "ziffer", ziffer }).abgelehnt;
}

// --- Schüsse -------------------------------------------------------------------------------------

export interface SchussErgebnis {
  /** Angefangene Eingabe auf der Tastatur, z. B. „1“ vor der „0“ */
  puffer: string;
  /** Werte, die jetzt der Reihe nach eingetragen werden */
  werte: Schusswert[];
}

function schussTexte(erlaubt: readonly Schusswert[]): string[] {
  return erlaubt.map((wert) => String(wert).toUpperCase());
}

function schussWert(erlaubt: readonly Schusswert[], text: string): Schusswert | undefined {
  return erlaubt.find((wert) => String(wert).toUpperCase() === text);
}

/**
 * Eine Taste der Tastatur bei Schüssen. „1“ wartet, solange „10“ möglich ist; jede andere Taste
 * oder `schussPufferAbschliessen` trägt die „1“ ein.
 */
export function schussTaste(
  erlaubt: readonly Schusswert[],
  puffer: string,
  zeichen: string,
): SchussErgebnis {
  const texte = schussTexte(erlaubt);
  const kandidat = puffer + zeichen.toUpperCase();
  const laenger = texte.some((text) => text !== kandidat && text.startsWith(kandidat));
  const wert = schussWert(erlaubt, kandidat);
  if (wert !== undefined && !laenger) return { puffer: "", werte: [wert] };
  if (laenger) return { puffer: kandidat, werte: [] };
  if (puffer !== "") {
    const frueher = schussWert(erlaubt, puffer);
    const rest = schussTaste(erlaubt, "", zeichen);
    return {
      puffer: rest.puffer,
      werte: [...(frueher !== undefined ? [frueher] : []), ...rest.werte],
    };
  }
  return { puffer: "", werte: [] };
}

/** Trägt eine angefangene Eingabe ein, wenn sie für sich ein erlaubter Wert ist. */
export function schussPufferAbschliessen(
  erlaubt: readonly Schusswert[],
  puffer: string,
): Schusswert | undefined {
  return puffer === "" ? undefined : schussWert(erlaubt, puffer);
}

// --- Tastatur ------------------------------------------------------------------------------------

/** Taste der Hardware-Tastatur → Taste des Terminals (oder `null`, wenn sie nichts bedeutet). */
export function tasteAusTastatur(key: string): Taste | { art: "zeichen"; zeichen: string } | null {
  if (/^\d$/.test(key)) return { art: "ziffer", ziffer: key };
  if (key === "," || key === "." || key === "Decimal") return { art: "komma" };
  if (key === "Backspace" || key === "Delete") return { art: "loeschen" };
  if (key === "Enter" || key === "ArrowRight" || key === "ArrowDown") return { art: "weiter" };
  if (key === "ArrowLeft" || key === "ArrowUp") return { art: "zurueck" };
  if (key.length === 1 && /[a-z]/i.test(key)) return { art: "zeichen", zeichen: key };
  return null;
}
