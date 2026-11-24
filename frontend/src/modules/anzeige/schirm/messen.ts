import {
  createContext,
  type RefObject,
  useContext,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { type Begriffe, type Begriffssaetze, begriffeFuer } from "../../../lib/begriffe";
import { inSeiten, seiteZurZeit, type Takt, zeilenProSeite } from "../rotation";

/** Was alle Szenen brauchen: Uhr, Ausrichtung, Sprache, formelle Wörter. */
export interface SchirmLage {
  /** Geräteuhr in ms, tickt jede Sekunde (für Seiten und Restzeit) */
  jetzt: number;
  /** Serverzeit minus Geräteuhr in ms */
  versatzMs: number;
  /** Höher als breit (Fernseher hochkant) */
  hochkant: boolean;
  /**
   * Vergrößerung gegenüber Full HD (kürzere Seite / 1080, mindestens 1). Für Bausteine mit festen
   * Höchstgrößen in Pixeln, die sonst auf 4K kleiner wirken würden.
   */
  faktor: number;
  sprache: string;
  /** Begriffssätze des Servers (`GET /terms`); `null`, solange nichts da ist (dann Rückfall) */
  begriffe: Begriffssaetze | null;
}

export const SchirmKontext = createContext<SchirmLage>({
  jetzt: 0,
  versatzMs: 0,
  hochkant: false,
  faktor: 1,
  sprache: "de",
  begriffe: null,
});

export function useSchirm(): SchirmLage {
  return useContext(SchirmKontext);
}

/**
 * Formelle Wörter des Schirms für einen Verband (`federation` aus dem Feed): Schützenstand,
 * Durchgang, Serie … nach dem Regelwerk des Verbands, ohne Verband der Standardsatz.
 */
export function useWoerter(verband?: string | null): Begriffe {
  const { begriffe } = useSchirm();
  return begriffeFuer(begriffe, verband);
}

/** Größe eines Elements, laufend gemessen. Ohne Layout (Tests) bleibt sie 0 × 0. */
export function useGroesse<T extends HTMLElement>(): [
  RefObject<T | null>,
  { breite: number; hoehe: number },
] {
  const ref = useRef<T>(null);
  const [groesse, setGroesse] = useState({ breite: 0, hoehe: 0 });
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const messen = () =>
      setGroesse((alt) =>
        alt.breite === element.clientWidth && alt.hoehe === element.clientHeight
          ? alt
          : { breite: element.clientWidth, hoehe: element.clientHeight },
      );
    messen();
    const beobachter = new ResizeObserver(messen);
    beobachter.observe(element);
    return () => beobachter.disconnect();
  }, []);
  return [ref, groesse];
}

function spaltenAus(stil: CSSStyleDeclaration): number {
  const vorlage = stil.gridTemplateColumns;
  if (!vorlage || vorlage === "none") return 1;
  return Math.max(1, vorlage.split(" ").filter(Boolean).length);
}

export interface Seiten<T> {
  ref: RefObject<HTMLDivElement | null>;
  /** Einträge der aktuellen Seite */
  eintraege: T[];
  seite: number;
  seiten: number;
  /** Zeilen je Spalte (für `grid-template-rows` bei spaltenweisem Fluss); `null` = ungemessen */
  zeilen: number | null;
  /** Spalten des Rasters (1 ohne Raster) */
  spalten: number;
}

/**
 * Blättert eine Liste gleich hoher Zeilen seitenweise, statt sie abzuschneiden. Gemessen wird die
 * Höhe des Listen-Elements (`ref`) und die erste Zeile darin (`data-zeile`); Spalten zählen mit,
 * wenn die Liste ein Raster ist. Die Seiten teilen sich die Zeitscheibe `takt` gleichmäßig.
 * `teilen` erlaubt eine eigene Aufteilung (z. B. Klassenköpfe nicht allein unten).
 */
export function useSeiten<T>(
  liste: readonly T[],
  takt: Takt,
  teilen: (liste: readonly T[], proSeite: number | null) => T[][] = inSeiten,
): Seiten<T> {
  const { jetzt } = useSchirm();
  const ref = useRef<HTMLDivElement>(null);
  const [mass, setMass] = useState<{ zeilen: number | null; spalten: number }>({
    zeilen: null,
    spalten: 1,
  });
  const hatZeilen = liste.length > 0;

  // Neu messen, sobald es Zeilen gibt: vorher fehlt die Zeilenhöhe.
  // biome-ignore lint/correctness/useExhaustiveDependencies: hatZeilen löst die Messung aus
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const messen = () => {
      const zeile = element.querySelector<HTMLElement>("[data-zeile]");
      const stil = getComputedStyle(element);
      const abstand = Number.parseFloat(stil.rowGap) || 0;
      const zeilen = zeilenProSeite(element.clientHeight, zeile?.offsetHeight ?? 0, abstand);
      const spalten = spaltenAus(stil);
      setMass((alt) =>
        alt.zeilen === zeilen && alt.spalten === spalten ? alt : { zeilen, spalten },
      );
    };
    messen();
    const beobachter = new ResizeObserver(messen);
    beobachter.observe(element);
    const zeile = element.querySelector<HTMLElement>("[data-zeile]");
    if (zeile) beobachter.observe(zeile);
    return () => beobachter.disconnect();
  }, [hatZeilen]);

  const proSeite = mass.zeilen === null ? null : mass.zeilen * mass.spalten;
  const seitenListe = teilen(liste, proSeite);
  const seite = seiteZurZeit(takt, jetzt, seitenListe.length);
  return {
    ref,
    eintraege: seitenListe[seite] ?? [],
    seite,
    seiten: seitenListe.length,
    zeilen: mass.zeilen,
    spalten: mass.spalten,
  };
}
