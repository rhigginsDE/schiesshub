import { describe, expect, it } from "vitest";
import { beispielCsv, csvLesen, trennzeichen, vorschauZeilen } from "./csv";

describe("csvLesen", () => {
  it("erkennt das Trennzeichen aus der Kopfzeile", () => {
    expect(trennzeichen("name;club\nA,B;C")).toBe(";");
    expect(trennzeichen("\nname,club\n")).toBe(",");
  });

  it("liest Anführungszeichen, Umbrüche im Feld und zählt Zeilen wie Python", () => {
    const text = 'name;club\r\n"Brandt; Markus";"SV ""Tell"""\r\n"Zwei\nZeilen";X\r\n\r\nLetzte;Y';
    const daten = csvLesen(text);
    expect(daten.map((d) => d.zeile)).toEqual([1, 2, 4, 5, 6]);
    expect(daten[1]?.zellen).toEqual(["Brandt; Markus", 'SV "Tell"']);
    expect(daten[2]?.zellen).toEqual(["Zwei\nZeilen", "X"]);
    expect(daten[3]?.zellen).toEqual([""]);
    expect(daten[4]?.zellen).toEqual(["Letzte", "Y"]);
  });
});

describe("vorschauZeilen", () => {
  it("ordnet Name und Verein den Zeilennummern zu, auch mit deutschen Spaltennamen", () => {
    const zeilen = vorschauZeilen("﻿Verein;Name\nSV Tell;Markus Brandt\n\n;'=Formel\n");
    expect(zeilen.get(2)).toEqual({ name: "Markus Brandt", verein: "SV Tell" });
    expect(zeilen.get(4)).toEqual({ name: "=Formel", verein: "" });
  });

  it("die Beispieldatei hat eine Kopfzeile und erfundene Personen", () => {
    const zeilen = vorschauZeilen(beispielCsv());
    expect(zeilen.size).toBe(4);
    expect(zeilen.get(2)?.name).toBe("Erika Beispiel");
  });
});
