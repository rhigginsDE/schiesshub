import { describe, expect, it } from "vitest";
import type { Disziplin, Gruppe } from "../../../api/typen";
import { gruppenNachWaffenart, normalisiere, sucheImKatalog, suchWoerter } from "./katalogSuche";

function gruppe(id: string, name: string, waffenart: string, art: string, distanz: number | null) {
  return {
    verband: "bds",
    id,
    name,
    waffenart,
    distanz_m: distanz,
    art,
    anzahl: 1,
    wertung_modell: "ringe",
    geprueft: true,
  } satisfies Gruppe;
}

function disziplin(kennziffer: string, name: string, g: Gruppe, waffe: string): Disziplin {
  return {
    verband: "bds",
    kennziffer,
    name,
    gruppe_id: g.id,
    gruppe_name: g.name,
    waffe,
    munition: "",
    visierung: "offen",
    anschlag: "stehend",
    scheibe: "",
    optional: false,
    hinweis: null,
  };
}

const FALL = gruppe(
  "flinte-15m-fallscheibe",
  "Flinte 15 m Fallscheibe",
  "flinte",
  "fallscheibe",
  15,
);
const PRAEZ = gruppe("kw-25m-praezision", "KW 25 m Präzision", "kurzwaffe", "praezision", 25);
const GRUPPEN = [FALL, PRAEZ];
const KATALOG = [
  disziplin("1001", "Pistole bis 9 mm", PRAEZ, "Pistole"),
  disziplin("1006", "Revolver bis .38", PRAEZ, "Revolver"),
  disziplin("4401", "Selbstladeflinte, offene Visierung", FALL, "Selbstladeflinte"),
  disziplin("4410", "Repetierflinte", FALL, "Repetierflinte"),
];
const kennziffern = (eingabe: string) =>
  sucheImKatalog(KATALOG, GRUPPEN, eingabe).map((d) => d.kennziffer);

describe("Katalogsuche", () => {
  it("findet über den Gruppennamen, auch wenn der Name ihn nicht enthält", () => {
    expect(kennziffern("Fallscheibe")).toEqual(["4401", "4410"]);
    expect(kennziffern("fallscheibe")).toEqual(["4401", "4410"]);
  });

  it("verlangt bei mehreren Wörtern jedes Wort", () => {
    expect(kennziffern("Fallscheibe repetier")).toEqual(["4410"]);
    expect(kennziffern("flinte 15 m")).toEqual(["4401", "4410"]);
    expect(kennziffern("15m")).toEqual(["4401", "4410"]);
  });

  it("ist bei Umlauten tolerant", () => {
    expect(kennziffern("Präzision")).toEqual(["1001", "1006"]);
    expect(kennziffern("praezision")).toEqual(["1001", "1006"]);
    expect(kennziffern("prazision")).toEqual(["1001", "1006"]);
  });

  it("durchsucht Waffe und Waffenart", () => {
    expect(kennziffern("revolver")).toEqual(["1006"]);
    expect(kennziffern("kurzwaffe")).toEqual(["1001", "1006"]);
  });

  it("stellt passende Kennziffern nach vorn", () => {
    expect(kennziffern("44")).toEqual(["4401", "4410"]);
    expect(kennziffern("4401")).toEqual(["4401"]);
  });

  it("gibt ohne Eingabe alles zurück und bei Unsinn nichts", () => {
    expect(kennziffern("  ")).toHaveLength(4);
    expect(kennziffern("Luftpistole")).toEqual([]);
  });

  it("normalisiert Eingaben", () => {
    expect(normalisiere("Größe Übung")).toBe("groesse uebung");
    expect(suchWoerter("  KW, 25 m ")).toEqual(["kw", "25", "m"]);
  });

  it("gliedert Gruppen nach Waffenart", () => {
    expect(gruppenNachWaffenart(GRUPPEN).map(([art, liste]) => [art, liste.length])).toEqual([
      ["flinte", 1],
      ["kurzwaffe", 1],
    ]);
  });
});
