import { describe, expect, it } from "vitest";
import {
  formatDatum,
  formatDauer,
  formatDezimal,
  formatHundertstel,
  formatSekunden,
  formatUhrzeit,
  formatZahl,
} from "./format";

describe("formatZahl", () => {
  it("nutzt in Deutsch Dezimalkomma und Tausenderpunkt", () => {
    expect(formatZahl(1234.5)).toBe("1.234,5");
    expect(formatZahl(0.25)).toBe("0,25");
    expect(formatZahl(42)).toBe("42");
  });

  it("richtet sich nach der übergebenen Sprache", () => {
    expect(formatZahl(1234.5, {}, "en")).toBe("1,234.5");
  });

  it("begrenzt die Nachkommastellen", () => {
    expect(formatZahl(1.23456)).toBe("1,235");
    expect(formatZahl(1.23456, { maxNachkommastellen: 1 })).toBe("1,2");
  });
});

describe("formatDezimal", () => {
  it("füllt auf feste Nachkommastellen auf", () => {
    expect(formatDezimal(6, 2)).toBe("6,00");
    expect(formatDezimal(98.7, 1)).toBe("98,7");
    expect(formatDezimal(12.345, 2, "en")).toBe("12.35");
  });
});

describe("formatHundertstel", () => {
  it("wandelt Hundertstelsekunden in Sekunden mit zwei Stellen", () => {
    expect(formatHundertstel(1234)).toBe("12,34");
    expect(formatHundertstel(500)).toBe("5,00");
  });
});

describe("formatSekunden und formatDauer", () => {
  it("hängt die Einheit an", () => {
    expect(formatSekunden(10)).toBe("10 s");
    expect(formatSekunden(2.5)).toBe("2,5 s");
  });

  it("schreibt volle Minuten als Minuten, alles andere in Sekunden", () => {
    expect(formatDauer(60)).toBe("1 Min.");
    expect(formatDauer(300)).toBe("5 Min.");
    expect(formatDauer(90)).toBe("90 s");
    expect(formatDauer(8)).toBe("8 s");
  });
});

describe("formatDatum und formatUhrzeit", () => {
  it("schreibt ein ISO-Datum deutsch", () => {
    expect(formatDatum("2026-06-30")).toBe("30.06.2026");
  });

  it("lässt unlesbare Werte unverändert", () => {
    expect(formatDatum("unbekannt")).toBe("unbekannt");
  });

  it("zeigt die Uhrzeit zweistellig", () => {
    expect(formatUhrzeit(new Date(2026, 10, 21, 9, 5))).toBe("09:05");
  });
});
