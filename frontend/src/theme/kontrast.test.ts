import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { cssVariablesResolver } from "./cssVariables";
import { kontrast, mischen } from "./kontrast";
import { theme } from "./theme";
import { type Farbschema, farbschemata } from "./tokens";

const AA_TEXT = 4.5;
const AA_BEDIENELEMENT = 3;
const VERZEICHNIS = import.meta.dirname;

describe("kontrast", () => {
  it("rechnet die bekannten Grenzwerte", () => {
    expect(kontrast("#000000", "#FFFFFF")).toBeCloseTo(21, 1);
    expect(kontrast("#FFFFFF", "#FFFFFF")).toBe(1);
  });
});

describe.each(Object.entries(farbschemata))("Farbschema %s", (_name, schema: Farbschema) => {
  const flaechen = [schema.bg, schema.flaeche, schema.flaeche2];

  it.each(["text", "textWeich", "textGedaempft", "akzentText"] as const)(
    "%s ist auf allen Flächen lesbar",
    (rolle) => {
      for (const flaeche of flaechen) {
        expect(kontrast(schema[rolle], flaeche)).toBeGreaterThanOrEqual(AA_TEXT);
      }
    },
  );

  it("Schrift auf dem Primär-Button ist lesbar", () => {
    expect(kontrast(schema.aufAkzent, schema.akzent)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(kontrast(schema.aufAkzent, schema.akzentHover)).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it.each([
    ["akzentText", "akzentFlaeche"],
    ["warn", "warnFlaeche"],
    ["krit", "kritFlaeche"],
    ["info", "infoFlaeche"],
    ["gold", "goldFlaeche"],
  ] as const)("Chip-Schrift %s auf %s ist lesbar", (text, toenung) => {
    for (const untergrund of [schema.bg, schema.flaeche]) {
      const flaeche = mischen(schema[toenung], untergrund);
      expect(kontrast(schema[text], flaeche)).toBeGreaterThanOrEqual(AA_TEXT);
    }
  });
});

describe.each(Object.entries(farbschemata))("Bedienelemente im Schema %s", (_name, schema) => {
  // Eingabefelder stehen auf Fläche (Feldgrund) und auf jeder Seitenfläche.
  const flaechen = { bg: schema.bg, flaeche: schema.flaeche, flaeche2: schema.flaeche2 };

  it.each(Object.entries(flaechen))("Feldrahmen hebt sich von %s ab", (_flaeche, farbe) => {
    expect(kontrast(schema.linieStark, farbe)).toBeGreaterThanOrEqual(AA_BEDIENELEMENT);
  });

  it.each(Object.entries(flaechen))("Fokusrahmen hebt sich von %s ab", (_flaeche, farbe) => {
    expect(kontrast(schema.fokus, farbe)).toBeGreaterThanOrEqual(AA_BEDIENELEMENT);
  });

  it("Fokusrahmen hebt sich von grün getönten Flächen ab", () => {
    for (const untergrund of [schema.bg, schema.flaeche]) {
      const flaeche = mischen(schema.akzentFlaeche, untergrund);
      expect(kontrast(schema.fokus, flaeche)).toBeGreaterThanOrEqual(AA_BEDIENELEMENT);
    }
  });

  it("Fokusrahmen ist auch an grünen Knöpfen sichtbar (zweifarbig)", () => {
    // Entweder hebt sich schon der äußere Rahmen vom Grün ab, oder der innere Ring trennt beide.
    const trennung = Math.max(
      kontrast(schema.fokus, schema.akzent),
      kontrast(schema.fokusInnen, schema.akzent),
    );
    expect(trennung).toBeGreaterThanOrEqual(AA_BEDIENELEMENT);
    expect(kontrast(schema.fokus, schema.fokusInnen)).toBeGreaterThanOrEqual(AA_BEDIENELEMENT);
  });

  it("Feldrahmen beim Fokus hebt sich vom Feld ab", () => {
    expect(kontrast(schema.fokus, schema.flaeche)).toBeGreaterThanOrEqual(AA_BEDIENELEMENT);
  });

  it("Deaktiviertes bleibt lesbar", () => {
    expect(kontrast(schema.textGedaempft, schema.flaeche2)).toBeGreaterThanOrEqual(
      AA_BEDIENELEMENT,
    );
  });
});

/** Die geprüften Farben müssen auch dort ankommen, wo Mantine zeichnet. */
describe("Bindung der Tokens an Mantine", () => {
  const variablen = cssVariablesResolver(theme as never);

  it.each(["light", "dark"] as const)("Schema %s schreibt Fokus- und Linienfarben", (schema) => {
    const werte = variablen[schema];
    expect(werte["--sh-fokus"]).toBe(farbschemata[schema].fokus);
    expect(werte["--sh-fokus-innen"]).toBe(farbschemata[schema].fokusInnen);
    expect(werte["--sh-linie-stark"]).toBe(farbschemata[schema].linieStark);
    expect(werte["--mantine-color-disabled-color"]).toBe(farbschemata[schema].textGedaempft);
    expect(werte["--mantine-color-disabled"]).toBe(farbschemata[schema].flaeche2);
  });

  const css = readFileSync(join(VERZEICHNIS, "global.css"), "utf8").replace(/\s+/g, " ");

  it("Eingabefelder nutzen „Linie stark“ und beim Fokus die Fokusfarbe", () => {
    expect(css).toContain("--input-bd: var(--sh-linie-stark)");
    expect(css).toContain("--input-bd-focus: var(--sh-fokus)");
  });

  it("Mantine-Fokusklassen nutzen den zweifarbigen Fokusrahmen", () => {
    const regel = /\.mantine-focus-auto:focus-visible[^{]*\{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(regel).toContain("outline: 2px solid var(--sh-fokus)");
    expect(regel).toContain("var(--sh-fokus-innen)");
    expect(css).toMatch(/\.mantine-focus-always:focus[^{]*\{[^}]*var\(--sh-fokus\)/);
  });
});
