import { describe, expect, it } from "vitest";
import { abkuerzen, anzeigename, vergleichsform } from "./anzeigename";

describe("abkuerzen (gleiche Regel wie das Backend)", () => {
  it.each([
    ["Markus Brandt", "M. Brandt"],
    ["Hans Peter Müller", "H. P. Müller"],
    ["Hans-Peter Müller", "H.-P. Müller"],
    ["Anna Müller-Lüdenscheidt", "A. Müller-Lüdenscheidt"],
    ["Ludwig van Beethoven", "L. van Beethoven"],
    ["Anna von der Leyen", "A. von der Leyen"],
    ["J. Maier", "J. Maier"],
    ["Deniz Yılmaz", "D. Yılmaz"],
    ["  Katrin   Vogel ", "K. Vogel"],
    ["Cher", "Cher"],
    ["von Bülow", "von Bülow"],
    ["", ""],
  ])("%s → %s", (name, erwartet) => {
    expect(abkuerzen(name)).toBe(erwartet);
  });
});

describe("anzeigename", () => {
  it("liefert voll, abgekürzt oder nichts", () => {
    expect(anzeigename(" Sabine  Köhler", "full")).toBe("Sabine Köhler");
    expect(anzeigename("Sabine Köhler", "short")).toBe("S. Köhler");
    expect(anzeigename("Sabine Köhler", "hidden")).toBeNull();
  });
});

describe("vergleichsform", () => {
  it("behandelt Umlaute, Akzente und Großschreibung gleich", () => {
    expect(vergleichsform("Köhler")).toBe(vergleichsform("koehler"));
    expect(vergleichsform("KOHLER")).toBe(vergleichsform("Köhler"));
    expect(vergleichsform("Straße")).toBe("strasse");
    expect(vergleichsform("  SGi   Neustadt ")).toBe("sgi neustadt");
  });
});
