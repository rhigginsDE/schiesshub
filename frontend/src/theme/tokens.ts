/**
 * Zentrale Farb- und Formwerte. Einzige Quelle für Markenfarben;
 * daraus entstehen das Mantine-Theme (theme.ts) und die CSS-Variablen `--sh-*` (cssVariables.ts).
 */

export const marke = {
  gruen: "#6CBB24",
  gruenHell: "#8DD03A",
  /** Grün als Text auf hellem Grund (Kontrast zu Weiß > 4,5:1). */
  gruenText: "#3E7413",
  nacht: "#0B131B",
  nacht2: "#121D29",
  nacht3: "#1B2836",
  linie: "#273647",
  /** Gold ist Platz 1 und Auszeichnungen vorbehalten. */
  gold: "#D4A93C",
  goldHell: "#F3DB82",
  weiss: "#F8F9FA",
} as const;

export const radius = { s: 6, m: 10, l: 16 } as const;

/**
 * Schriftgrößen in px nach Markenhandbuch. `klein` ist die Untergrenze für alles, was man lesen
 * muss; `label` nur für Großbuchstaben-Beschriftungen (`.h-label`).
 */
export const schriftgroesse = { text: 16, klein: 13, label: 12 } as const;

export const schriften = {
  display: '"Exo 2", "Segoe UI", system-ui, sans-serif',
  text: '"Inter", "Segoe UI", system-ui, -apple-system, sans-serif',
  mono: '"JetBrains Mono", ui-monospace, "Cascadia Mono", Consolas, monospace',
} as const;

export interface Farbschema {
  /** Seitenhintergrund */
  bg: string;
  /** Flächen (Panels, Kopfzeile) */
  flaeche: string;
  /** Hervorgehobene Fläche (Auswahl, Hover, neutrale Chips) */
  flaeche2: string;
  linie: string;
  /** Kräftigere Linie für Eingabefelder und Schalter (mindestens 3 : 1 zu allen Flächen) */
  linieStark: string;
  text: string;
  textWeich: string;
  textGedaempft: string;
  /** Markengrün als Fläche (Primär-Button) */
  akzent: string;
  akzentHover: string;
  /** Schrift auf Markengrün */
  aufAkzent: string;
  /** Grün als Text oder Symbol */
  akzentText: string;
  /** Äußerer Fokusrahmen (2 px): mindestens 3 : 1 zu allen Flächen */
  fokus: string;
  /**
   * Innerer Fokusrahmen im Abstand zwischen Element und Rahmen: trennt den Rahmen auch von
   * grünen Flächen (Primär-Button, Schalter), mindestens 3 : 1 zu Akzent und zum äußeren Rahmen.
   */
  fokusInnen: string;
  akzentFlaeche: string;
  warn: string;
  warnFlaeche: string;
  warnLinie: string;
  krit: string;
  kritFlaeche: string;
  kritLinie: string;
  info: string;
  infoFlaeche: string;
  /** Nur für Platz 1 */
  gold: string;
  goldFlaeche: string;
}

export const dunkel: Farbschema = {
  bg: marke.nacht,
  flaeche: marke.nacht2,
  flaeche2: marke.nacht3,
  linie: marke.linie,
  linieStark: "#64768A",
  text: marke.weiss,
  textWeich: "#C9D2DB",
  textGedaempft: "#9AA8B6",
  akzent: marke.gruen,
  akzentHover: marke.gruenHell,
  aufAkzent: marke.nacht,
  akzentText: marke.gruenHell,
  fokus: marke.gruenHell,
  fokusInnen: marke.nacht,
  akzentFlaeche: "rgba(108, 187, 36, 0.16)",
  warn: "#F0B54A",
  warnFlaeche: "rgba(240, 181, 74, 0.14)",
  warnLinie: "rgba(240, 181, 74, 0.5)",
  krit: "#F2A093",
  kritFlaeche: "rgba(229, 96, 75, 0.16)",
  kritLinie: "rgba(229, 96, 75, 0.55)",
  info: "#6FB6E8",
  infoFlaeche: "rgba(111, 182, 232, 0.16)",
  gold: marke.goldHell,
  goldFlaeche: "rgba(212, 169, 60, 0.16)",
};

export const hell: Farbschema = {
  bg: "#F2F4F7",
  flaeche: "#FFFFFF",
  flaeche2: "#E8ECF1",
  linie: "#CBD3DC",
  linieStark: "#76838F",
  text: marke.nacht,
  textWeich: "#2B3948",
  textGedaempft: "#56636F",
  akzent: marke.gruen,
  akzentHover: "#7CC62B",
  aufAkzent: marke.nacht,
  akzentText: marke.gruenText,
  // Grün erreicht auf Hell gegen Weiß und Schuss-Grün zugleich keine 3 : 1; deshalb Nachtblau.
  fokus: marke.nacht,
  fokusInnen: "#FFFFFF",
  akzentFlaeche: "rgba(108, 187, 36, 0.14)",
  warn: "#7A4F00",
  warnFlaeche: "rgba(240, 181, 74, 0.22)",
  warnLinie: "rgba(184, 121, 0, 0.55)",
  krit: "#A82A18",
  kritFlaeche: "rgba(229, 96, 75, 0.14)",
  kritLinie: "rgba(176, 46, 27, 0.5)",
  info: "#1B5F95",
  infoFlaeche: "rgba(111, 182, 232, 0.2)",
  gold: "#6E520B",
  goldFlaeche: "rgba(212, 169, 60, 0.2)",
};

export const farbschemata = { light: hell, dark: dunkel } as const;
