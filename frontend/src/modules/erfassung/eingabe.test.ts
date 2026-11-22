import { describe, expect, it } from "vitest";
import type { FeldBeschreibung } from "./api";
import {
  FRISCH,
  schussPufferAbschliessen,
  schussTaste,
  type Taste,
  tasteAusTastatur,
  type ZahlEingabe,
  zahlTaste,
  zeitAusText,
  zeitText,
} from "./eingabe";

const ZEIT: FeldBeschreibung = { key: "time_cs", label: "Zeit", kind: "time", required: true };
const STEHEND: FeldBeschreibung = {
  key: "standing",
  label: "Stehende Scheiben",
  kind: "integer",
  required: true,
  min: 0,
  max: 5,
};
const SUMME: FeldBeschreibung = {
  key: "sum",
  label: "Seriensumme",
  kind: "integer",
  required: true,
  min: 0,
  max: 100,
};

function tippen(feld: FeldBeschreibung, tasten: string, aktuell?: number) {
  let eingabe: ZahlEingabe = FRISCH;
  let wert = aktuell;
  let weiter = false;
  for (const zeichen of tasten) {
    const taste: Taste =
      zeichen === ","
        ? { art: "komma" }
        : zeichen === "<"
          ? { art: "loeschen" }
          : { art: "ziffer", ziffer: zeichen };
    const ergebnis = zahlTaste(feld, eingabe, wert, taste);
    if (ergebnis.abgelehnt) continue;
    if (ergebnis.geaendert) wert = ergebnis.wert;
    eingabe = ergebnis.eingabe;
    weiter = ergebnis.weiter;
  }
  return { wert, eingabe, weiter };
}

describe("Zeiten", () => {
  it("„12,84“ ergibt 1284 Hundertstel", () => {
    expect(tippen(ZEIT, "12,84").wert).toBe(1284);
    expect(zeitAusText("12.8")).toBe(1280);
    expect(zeitAusText("12")).toBe(1200);
    expect(zeitAusText("")).toBeUndefined();
    expect(zeitText(1284)).toBe("12,84");
  });

  it("nimmt höchstens zwei Nachkommastellen und ein Komma", () => {
    expect(tippen(ZEIT, "12,845").wert).toBe(1284);
    expect(tippen(ZEIT, "1,,2").wert).toBe(120);
  });

  it("„0,“ ist noch keine Zeit", () => {
    expect(tippen(ZEIT, ",").wert).toBeUndefined();
  });

  it("Löschen bearbeitet den vorhandenen Wert", () => {
    expect(tippen(ZEIT, "<", 1284).wert).toBe(1280);
    const leer = zahlTaste(ZEIT, FRISCH, undefined, { art: "loeschen" });
    expect(leer.zurueck).toBe(true);
  });

  it("die erste Ziffer ersetzt den alten Wert", () => {
    expect(tippen(ZEIT, "9", 1284).wert).toBe(900);
  });
});

describe("Zahlen", () => {
  it("schaltet weiter, sobald keine Ziffer mehr passt", () => {
    expect(tippen(STEHEND, "3")).toMatchObject({ wert: 3, weiter: true });
    expect(tippen(SUMME, "9")).toMatchObject({ wert: 9, weiter: false });
    expect(tippen(SUMME, "95")).toMatchObject({ wert: 95, weiter: true });
    expect(tippen(SUMME, "10")).toMatchObject({ wert: 10, weiter: false });
    expect(tippen(SUMME, "100")).toMatchObject({ wert: 100, weiter: true });
  });

  it("lehnt Werte über dem Höchstwert ab", () => {
    expect(zahlTaste(STEHEND, FRISCH, undefined, { art: "ziffer", ziffer: "7" }).abgelehnt).toBe(
      true,
    );
  });
});

describe("Schüsse auf der Tastatur", () => {
  const alle = ["X", 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0];

  it("„1“ wartet auf die „0“, dann 10", () => {
    const erst = schussTaste(alle, "", "1");
    expect(erst).toEqual({ puffer: "1", werte: [] });
    expect(schussTaste(alle, erst.puffer, "0")).toEqual({ puffer: "", werte: [10] });
  });

  it("eine andere Taste trägt die wartende 1 ein", () => {
    expect(schussTaste(alle, "1", "9")).toEqual({ puffer: "", werte: [1, 9] });
    expect(schussPufferAbschliessen(alle, "1")).toBe(1);
  });

  it("„x“ ist der Innenzehner, einstellige Werte gehen sofort", () => {
    expect(schussTaste(alle, "", "x")).toEqual({ puffer: "", werte: ["X"] });
    expect(schussTaste(alle, "", "7")).toEqual({ puffer: "", werte: [7] });
  });

  it("nur erlaubte Werte (z. B. 10, 7, 0)", () => {
    const wenige = [10, 7, 0];
    expect(schussTaste(wenige, "", "9").werte).toEqual([]);
    expect(schussTaste(wenige, "", "1")).toEqual({ puffer: "1", werte: [] });
    expect(schussPufferAbschliessen(wenige, "1")).toBeUndefined();
    expect(schussTaste(wenige, "", "x").werte).toEqual([]);
  });

  it("übersetzt die Tastatur", () => {
    expect(tasteAusTastatur("Enter")).toEqual({ art: "weiter" });
    expect(tasteAusTastatur("Backspace")).toEqual({ art: "loeschen" });
    expect(tasteAusTastatur(",")).toEqual({ art: "komma" });
    expect(tasteAusTastatur("x")).toEqual({ art: "zeichen", zeichen: "x" });
    expect(tasteAusTastatur("Shift")).toBeNull();
  });
});
