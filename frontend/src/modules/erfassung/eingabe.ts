/**
 * Tastenlogik des Terminals: Ziffernfeld und Hardware-Tastatur, ohne React, einzeln getestet.
 *
 * - Zahlen (stehende Scheiben, Seriensumme, Zehner): Ziffern tippen; kann keine weitere Ziffer den
 *   Wert noch ändern (Höchstwert erreicht oder „0“), schaltet das Terminal von selbst weiter. Bei
 *   einstelligen Feldern (z. B. stehende Scheiben 0 bis 5) also nach jeder Ziffer, auch nach „0“.
 * - „Weiter“ direkt nach dem selbsttätigen Weiterschalten bestätigt nur und bleibt im neuen Feld:
 *   Wer aus Gewohnheit nach der Ziffer noch Enter oder „Weiter“ drückt, überspringt kein Feld.
 * - Rück löscht nur im aktiven Feld; in einem leeren Feld passiert nichts (kein Sprung zurück).
 * - Zeiten: Sekunden mit Komma („12,84“), an den Server in Hundertstelsekunden (1284).
 * - Schüsse: erlaubte Werte als Tasten; auf der Tastatur „1“ „0“ für 10 und „x“ für den Innenzehner.
 */
import { formatHundertstel } from "../../lib/format";
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
}

export const FRISCH: ZahlEingabe = { text: "", frisch: true };
/** Eingabe im Feld, das nach selbsttätigem Weiterschalten aktiv ist. */
export const ANGEKOMMEN: ZahlEingabe = { text: "", frisch: true, angekommen: true };

/** Warum eine Taste nicht passt (für einen kurzen Hinweis am Ziffernfeld). */
export type Ablehnung = "zu_gross" | "leer" | "unpassend";

export interface ZahlErgebnis {
  eingabe: ZahlEingabe;
  /** Neuer Wert des Feldes (`undefined` = leer); nur gesetzt, wenn `geaendert` */
  wert?: number;
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

/** Anzeigetext eines Feldwerts. */
export function wertText(feld: FeldBeschreibung, wert: unknown): string {
  if (wert === undefined || wert === null) return "";
  if (feld.kind === "time" && typeof wert === "number") return zeitText(wert);
  return String(wert);
}

function textAus(feld: FeldBeschreibung, wert: number | undefined): string {
  if (wert === undefined) return "";
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

/** Eine Taste in einem Zahlen- oder Zeitfeld. `aktuell`: gespeicherter Wert des Feldes. */
export function zahlTaste(
  feld: FeldBeschreibung,
  eingabe: ZahlEingabe,
  aktuell: number | undefined,
  taste: Taste,
): ZahlErgebnis {
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
      const weiter = !zeit && !weitereZifferMoeglich(feld, wert);
      return ergebnis({
        eingabe: weiter ? ANGEKOMMEN : { text, frisch: false },
        wert,
        geaendert: true,
        weiter,
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
