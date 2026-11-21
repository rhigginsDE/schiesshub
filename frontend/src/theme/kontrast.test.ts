import { describe, expect, it } from "vitest";
import { kontrast, mischen } from "./kontrast";
import { type Farbschema, farbschemata } from "./tokens";

const AA_TEXT = 4.5;
const AA_BEDIENELEMENT = 3;

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

describe("helles Farbschema", () => {
  it("Rahmen von Eingabefeldern hebt sich von der Fläche ab", () => {
    const { linieStark, flaeche } = farbschemata.light;
    expect(kontrast(linieStark, flaeche)).toBeGreaterThanOrEqual(AA_BEDIENELEMENT);
  });
});
