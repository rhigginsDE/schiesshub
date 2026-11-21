import { describe, expect, it } from "vitest";
import type { Abschnitt, Variante } from "../../api/typen";
import { nurZeitVarianten, sollzeitTabelle, verwendeteHaende, zeitTabelle } from "./aushangDaten";

const fertigkeit: Abschnitt = {
  id: "fertigkeit",
  name: "Fertigkeit",
  serien: 4,
  schuss_je_serie: 5,
};

function parcours(sollzeit: number, abbruch: number): Abschnitt {
  return {
    id: "parcours",
    name: "Parcours",
    serien: 4,
    schuss_je_serie: 5,
    sollzeit_s: sollzeit,
    max_gesamtzeit_s: abbruch,
    positionen: [
      { nr: 5, distanz_m: 20, anschlaege: [{ haltung: "stehend", hand: "beidhaendig" }] },
      { nr: 8, distanz_m: 5, anschlaege: [{ haltung: "stehend", hand: "einhaendig" }] },
    ],
  };
}

const mehrdistanz: Variante[] = [
  { id: "variante-1", name: "Parcours-Variante 1", abschnitte: [fertigkeit, parcours(80, 160)] },
  { id: "variante-2", name: "Parcours-Variante 2", abschnitte: [fertigkeit, parcours(60, 120)] },
];

describe("nurZeitVarianten", () => {
  it("erkennt Varianten, die sich nur in Soll- und Abbruchzeit unterscheiden", () => {
    expect(nurZeitVarianten(mehrdistanz)).toBe(true);
  });

  it("verneint bei unterschiedlicher Serienzahl und bei nur einer Variante", () => {
    const meisterschaft: Variante[] = [
      { id: "bm", name: "BM/LM", abschnitte: [{ ...fertigkeit, serien: 4 }] },
      { id: "dm", name: "DM", abschnitte: [{ ...fertigkeit, serien: 6 }] },
    ];
    expect(nurZeitVarianten(meisterschaft)).toBe(false);
    expect(nurZeitVarianten(mehrdistanz.slice(0, 1))).toBe(false);
  });
});

describe("sollzeitTabelle", () => {
  it("listet Sollzeit und Abbruch je Variante für den Abschnitt", () => {
    expect(sollzeitTabelle(mehrdistanz, 1, "de")).toEqual([
      { variante: "Parcours-Variante 1", sollzeit: "80 s", abbruch: "160 s" },
      { variante: "Parcours-Variante 2", sollzeit: "60 s", abbruch: "120 s" },
    ]);
    expect(sollzeitTabelle(mehrdistanz, 0, "de")).toEqual([]);
  });
});

describe("zeitTabelle", () => {
  it("leitet die Fallscheiben-Fälle aus den Katalogfeldern ab", () => {
    const zeilen = zeitTabelle(
      {
        id: "fallscheibe",
        name: "Fallscheibe",
        serien: 4,
        ziele_je_serie: 5,
        max_schuss_je_serie: 6,
        max_zeit_je_serie_s: 60,
        zuschlag_je_stehender_scheibe_s: 10,
        zeit_bei_abbruch_s: 60,
        zuschlag_stoerung_vor_erstem_schuss_s: 50,
      },
      "de",
    );
    expect(zeilen).toEqual([
      { fall: "Alle Scheiben gefallen", zeit: "gemessene Zeit" },
      {
        fall: "Alle 6 Schuss abgegeben, Scheiben stehen noch",
        zeit: "gemessene Zeit + 10 s je stehende Scheibe",
      },
      {
        fall: "Zeitlimit 60 s erreicht – Abbruch durch den Schießleiter",
        zeit: "60 s + 10 s je stehende Scheibe",
      },
      { fall: "Schütze bricht selbst ab", zeit: "60 s + 10 s je stehende Scheibe" },
      { fall: "Waffenstörung vor dem ersten Wertungsschuss", zeit: "60 s + 50 s" },
    ]);
  });

  it("bleibt leer ohne Zuschlag (keine Fallscheibe)", () => {
    expect(zeitTabelle(fertigkeit, "de")).toEqual([]);
  });
});

describe("verwendeteHaende", () => {
  it("nennt die vorkommenden Hand-Abzeichen in fester Reihenfolge", () => {
    expect(verwendeteHaende(mehrdistanz[0] as Variante)).toEqual(["beidhaendig", "einhaendig"]);
  });
});
