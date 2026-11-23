import { describe, expect, it } from "vitest";
import {
  formatDatum,
  formatDauer,
  formatDezimal,
  formatDezimalText,
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

describe("formatDezimalText", () => {
  it("schreibt Ringe mit Nachkommastelle aus dem Server-Text mit Dezimalkomma", () => {
    expect(formatDezimalText("20.1")).toBe("20,1");
    expect(formatDezimalText("218.0")).toBe("218,0");
    expect(formatDezimalText("1090.9")).toBe("1.090,9");
  });

  it("lässt ganze Ringe ohne Nachkommastelle und rechnet nicht um", () => {
    expect(formatDezimalText(187)).toBe("187");
    expect(formatDezimalText("187")).toBe("187");
    // Kein Gleitkommafehler beim Schreiben: 0,1 + 0,2 kommt als Text „0.3“.
    expect(formatDezimalText("0.3")).toBe("0,3");
    expect(formatDezimalText("104.7", "en")).toBe("104.7");
  });

  it("gibt bei leer oder unlesbar null zurück", () => {
    expect(formatDezimalText(null)).toBeNull();
    expect(formatDezimalText("")).toBeNull();
    expect(formatDezimalText("zehn")).toBeNull();
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
