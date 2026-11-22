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

  it("Löschen bearbeitet den vorhandenen Wert, im leeren Feld passiert nichts", () => {
    expect(tippen(ZEIT, "<", 1284).wert).toBe(1280);
    const leer = zahlTaste(ZEIT, FRISCH, undefined, { art: "loeschen" });
    expect(leer).toMatchObject({ zurueck: false, weiter: false, abgelehnt: true, grund: "leer" });
  });

  it("die erste Ziffer ersetzt den alten Wert", () => {
    expect(tippen(ZEIT, "9", 1284).wert).toBe(900);
  });
});

describe("Zahlen", () => {
  it("schaltet weiter, sobald keine Ziffer den Wert mehr ändern kann", () => {
    for (const ziffer of ["0", "1", "2", "3", "4", "5"]) {
      expect(tippen(STEHEND, ziffer)).toMatchObject({ wert: Number(ziffer), weiter: true });
    }
    expect(tippen(SUMME, "0")).toMatchObject({ wert: 0, weiter: true });
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

/**
 * Folge von Feldern wie im Terminal (Fallscheibe: je Serie Zeit, dann stehende Scheiben). Bewegt
 * das aktive Feld genau so, wie `Terminal.tsx` es mit dem Ergebnis von `zahlTaste` tut.
 * Tasten: Ziffern, „,“ Komma, „>“ Weiter/Enter, „<“ Rück, „^“ zurück.
 */
function folge(serien: number, tasten: string, start: (number | undefined)[] = []) {
  const felder = Array.from({ length: serien }, () => [ZEIT, STEHEND]).flat();
  const werte = felder.map((_, i) => start[i]);
  let index: number | null = 0;
  let eingabe: ZahlEingabe = FRISCH;
  const besucht: (number | null)[] = [0];
  for (const zeichen of tasten) {
    if (index === null) break;
    const feld = felder[index] as FeldBeschreibung;
    const taste: Taste =
      zeichen === ","
        ? { art: "komma" }
        : zeichen === ">"
          ? { art: "weiter" }
          : zeichen === "<"
            ? { art: "loeschen" }
            : zeichen === "^"
              ? { art: "zurueck" }
              : { art: "ziffer", ziffer: zeichen };
    const belegt = index + 1 < felder.length && werte[index + 1] !== undefined;
    const ergebnis = zahlTaste(feld, eingabe, werte[index], taste, belegt);
    if (ergebnis.abgelehnt) continue;
    if (ergebnis.geaendert) werte[index] = ergebnis.wert;
    eingabe = ergebnis.eingabe;
    if (ergebnis.weiter) index = index + 1 < felder.length ? index + 1 : null;
    else if (ergebnis.zurueck) index = Math.max(0, index - 1);
    if (ergebnis.weiter || ergebnis.zurueck) besucht.push(index);
  }
  /** Werte je Serie: [Zeit, stehend] */
  const jeSerie = Array.from({ length: serien }, (_, i) => [werte[2 * i], werte[2 * i + 1]]);
  return { jeSerie, index, besucht };
}

describe("Feldfolge stehende Scheiben (Befund Probelauf 2)", () => {
  it("viermal „11,00“ Enter „0“ ergibt viermal 11,00 s / 0", () => {
    const { jeSerie } = folge(4, "11,00>011,00>011,00>011,00>0");
    expect(jeSerie).toEqual([
      [1100, 0],
      [1100, 0],
      [1100, 0],
      [1100, 0],
    ]);
  });

  it("aus Gewohnheit Enter nach der „0“ überspringt nichts", () => {
    const { jeSerie } = folge(4, "11,00>0>11,00>0>11,00>0>11,00>0>");
    expect(jeSerie).toEqual([
      [1100, 0],
      [1100, 0],
      [1100, 0],
      [1100, 0],
    ]);
  });

  it("„0“ verhält sich wie jede andere Ziffer 1–5", () => {
    for (const ziffer of ["0", "1", "2", "3", "4", "5"]) {
      const { jeSerie } = folge(2, `9,5>${ziffer}10,25>${ziffer}`);
      expect(jeSerie).toEqual([
        [950, Number(ziffer)],
        [1025, Number(ziffer)],
      ]);
    }
  });

  it("Ziffernfeld: Zeit, Weiter, 1–5, Weiter überspringt die nächste Zeit nicht", () => {
    for (const ziffer of ["0", "1", "2", "3", "4", "5"]) {
      // Nach der Ziffer steht das Terminal auf „Serie 2 · Zeit“ und bleibt dort beim „Weiter“.
      const { jeSerie, besucht } = folge(2, `12,3>${ziffer}>`);
      expect(besucht).toEqual([0, 1, 2]);
      const weiter = folge(2, `12,3>${ziffer}>8,7`);
      expect(weiter.jeSerie).toEqual([
        [1230, Number(ziffer)],
        [870, undefined],
      ]);
      expect(jeSerie[1]).toEqual([undefined, undefined]);
    }
  });

  it("Tastenfolge aus dem QA-Durchlauf (B1): 20,00 ⏎ 0 ⏎ 30,00 ⏎ 1 ⏎ 39,00 ⏎ 0 ⏎ 40,00 ⏎ 0 ⏎", () => {
    const { jeSerie, index } = folge(4, "20,00>0>30,00>1>39,00>0>40,00>0>");
    expect(jeSerie).toEqual([
      [2000, 0],
      [3000, 1],
      [3900, 0],
      [4000, 0],
    ]);
    // Nach dem letzten Feld ist keins mehr aktiv; nichts springt an den Anfang zurück.
    expect(index).toBeNull();
  });

  it("dieselbe Folge mit jeder Ziffer 0–5 als stehende Scheiben", () => {
    for (const ziffer of ["0", "1", "2", "3", "4", "5"]) {
      const z = ziffer;
      const { jeSerie } = folge(4, `20,00>${z}>30,00>${z}>39,00>${z}>40,00>${z}>`);
      expect(jeSerie).toEqual([
        [2000, Number(z)],
        [3000, Number(z)],
        [3900, Number(z)],
        [4000, Number(z)],
      ]);
    }
  });

  it("selbsttätig weiter nur in ein leeres Feld: vorhandene Werte bleiben", () => {
    // Serie 1 · stehend korrigieren (Feld angetippt), Serie 2 ist schon erfasst.
    const start = [1234, 2, 1520, 1];
    const ohneEnter = folge(2, ">0", start);
    expect(ohneEnter.index).toBe(1);
    // Weitere Ziffern (gedacht für Serie 2) ändern weder den eben getippten Wert noch Serie 2.
    const getippt = folge(2, ">09,5", start);
    expect(getippt.index).toBe(1);
    expect(getippt.jeSerie).toEqual([
      [1234, 0],
      [1520, 1],
    ]);
    // Rück bearbeitet das Feld wieder ausdrücklich.
    expect(folge(2, ">0<3", start).jeSerie[0]).toEqual([1234, 3]);
    // Enter führt ausdrücklich ins nächste Feld; erst dort ersetzt die Eingabe den Wert.
    const mitEnter = folge(2, ">0>9,5", start);
    expect(mitEnter.index).toBe(2);
    expect(mitEnter.jeSerie).toEqual([
      [1234, 0],
      [950, 1],
    ]);
    const hinweis = zahlTaste(STEHEND, FRISCH, 2, { art: "ziffer", ziffer: "0" }, true);
    expect(hinweis).toMatchObject({ weiter: false, abgelehnt: false, grund: "naechstes_belegt" });
  });

  it("zweimal Weiter nach dem Weiterschalten geht bewusst ein Feld weiter", () => {
    expect(folge(2, "12,3>1>>").index).toBe(3);
  });

  it("Rück löscht nur im aktiven Feld und springt nie ins vorige", () => {
    // Serie 1 · stehend: 8× Rück leert nur dieses Feld, die Zeit davor bleibt.
    const { jeSerie, index } = folge(2, "><<<<<<<<", [950, 2, 1050, 0]);
    expect(index).toBe(1);
    expect(jeSerie).toEqual([
      [950, undefined],
      [1050, 0],
    ]);
    // Serie 2 · Zeit 10,50 wird mit 8× Rück geleert; Serie 1 bleibt unberührt.
    const zeit = folge(2, ">><<<<<<<<", [950, 2, 1050, 0]);
    expect(zeit.index).toBe(2);
    expect(zeit.jeSerie).toEqual([
      [950, 2],
      [undefined, 0],
    ]);
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
