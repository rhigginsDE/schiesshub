import { describe, expect, it } from "vitest";
import type { FeldBeschreibung } from "./api";
import {
  einheitenAus,
  einheitenRoh,
  einheitenText,
  FRISCH,
  istJeZiel,
  istKommaFeld,
  kommaBereich,
  kommaGrenzen,
  schussPufferAbschliessen,
  schussTaste,
  summeEinheiten,
  type Taste,
  tasteAusTastatur,
  wertText,
  type ZahlEingabe,
  zahlTaste,
  zeitAusText,
  zeitText,
  zifferErlaubt,
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

function tippen(feld: FeldBeschreibung, tasten: string, aktuell?: number | string) {
  let eingabe: ZahlEingabe = FRISCH;
  let wert: number | string | undefined = aktuell;
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
function folge(
  serien: number,
  tasten: string,
  start: (number | string | undefined)[] = [],
  jeSerieFelder: FeldBeschreibung[] = [ZEIT, STEHEND],
) {
  const felder = Array.from({ length: serien }, () => jeSerieFelder).flat();
  const werte: (number | string | undefined)[] = felder.map((_, i) => start[i]);
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
  /** Werte je Serie: [Zeit, stehend] (bzw. die Felder aus `jeSerieFelder`) */
  const breite = jeSerieFelder.length;
  const jeSerie = Array.from({ length: serien }, (_, i) =>
    werte.slice(breite * i, breite * i + breite),
  );
  return { jeSerie, werte, index, besucht };
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

// --- Zehntelwertung (DSB) -------------------------------------------------------------------------

/** Wie `GET …/form` es für Luftgewehr mit Zehntelwertung liefert (Einzelschuss). */
const SCHUSS_ZEHNTEL: FeldBeschreibung = {
  key: "shots",
  label: "Schüsse",
  kind: "shots",
  required: true,
  count: 10,
  allowed_values: null,
  decimals: 1,
  step: "0.1",
  value_min: "1.0",
  value_max: "10.9",
  zero_allowed: true,
};
/** Seriensumme bei Zehntelwertung (10 Schuss). */
const SUMME_ZEHNTEL: FeldBeschreibung = {
  key: "sum",
  label: "Seriensumme",
  kind: "decimal",
  required: true,
  decimals: 1,
  step: "0.1",
  value_min: "0.0",
  value_max: "109.0",
};
/** Treffer je Ziel (Trap): ein Wert je Ziel, 1 oder 0. */
const ZIELE: FeldBeschreibung = {
  key: "shots",
  label: "Treffer je Ziel",
  kind: "shots",
  required: true,
  count: 25,
  allowed_values: [1, 0],
  per_target: true,
};
const BDS_SCHUSS: FeldBeschreibung = {
  key: "shots",
  label: "Schüsse",
  kind: "shots",
  required: true,
  count: 5,
  allowed_values: ["X", 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
};

describe("Zehntel: Kommazahlen lesen und schreiben", () => {
  it("erkennt Kommafelder nur bei Nachkommastellen ohne feste Ringwerte", () => {
    expect(istKommaFeld(SCHUSS_ZEHNTEL)).toBe(true);
    expect(istKommaFeld(SUMME_ZEHNTEL)).toBe(true);
    expect(istKommaFeld(BDS_SCHUSS)).toBe(false);
    expect(istKommaFeld(SUMME)).toBe(false);
    expect(istKommaFeld(ZIELE)).toBe(false);
    expect(istJeZiel(ZIELE)).toBe(true);
    expect(istJeZiel(BDS_SCHUSS)).toBe(false);
  });

  it("liest Komma, Punkt und Zahlen als ganze Zehntel", () => {
    expect(einheitenAus("10,4", 1)).toBe(104);
    expect(einheitenAus("10.4", 1)).toBe(104);
    expect(einheitenAus("10.40", 1)).toBe(104);
    expect(einheitenAus(10.4, 1)).toBe(104);
    expect(einheitenAus("10", 1)).toBe(100);
    expect(einheitenAus("0", 1)).toBe(0);
    expect(einheitenAus("10.45", 1)).toBeUndefined();
    expect(einheitenAus("-1", 1)).toBeUndefined();
    expect(einheitenAus("zehn", 1)).toBeUndefined();
    expect(einheitenAus(null, 1)).toBeUndefined();
  });

  it("schreibt für den Server Text mit Punkt, für die Anzeige mit Komma", () => {
    expect(einheitenRoh(104, 1)).toBe("10.4");
    expect(einheitenRoh(0, 1)).toBe("0.0");
    expect(einheitenRoh(1090, 1)).toBe("109.0");
    expect(einheitenText(104, 1)).toBe("10,4");
    expect(einheitenText(10909, 1)).toBe("1.090,9");
    expect(wertText(SCHUSS_ZEHNTEL, "9.8")).toBe("9,8");
    expect(wertText(SCHUSS_ZEHNTEL, 10)).toBe("10,0");
    expect(wertText(SUMME_ZEHNTEL, "104.3")).toBe("104,3");
    // Ganze Ringe bleiben, wie sie sind.
    expect(wertText(BDS_SCHUSS, "X")).toBe("X");
    expect(wertText(BDS_SCHUSS, 9)).toBe("9");
  });

  it("summiert in ganzen Zehnteln ohne Gleitkommafehler", () => {
    // 0,1 + 0,2 ergäbe als Gleitkommazahl 0,30000000000000004.
    expect(summeEinheiten([0.1, 0.2], 1)).toBe(3);
    expect(einheitenRoh(summeEinheiten([0.1, 0.2], 1), 1)).toBe("0.3");
    const serie = ["10.4", "9.8", 10.1, "10,9", "0.0", "9.9", "10.0", "8.7", "10.3", "9.6"];
    expect(summeEinheiten(serie, 1)).toBe(897);
    expect(einheitenText(summeEinheiten(serie, 1), 1)).toBe("89,7");
    // Zehnmal 10,9 ist genau die Höchstsumme 109,0.
    expect(einheitenRoh(summeEinheiten(Array(10).fill("10.9"), 1), 1)).toBe("109.0");
  });

  it("nennt die Grenzen aus der Formularbeschreibung", () => {
    expect(kommaGrenzen(SCHUSS_ZEHNTEL)).toEqual({ stellen: 1, min: 10, max: 109, null: true });
    expect(kommaBereich(SCHUSS_ZEHNTEL)).toEqual({ min: "1,0", max: "10,9", null: true });
    expect(kommaBereich(SUMME_ZEHNTEL)).toEqual({ min: "0,0", max: "109,0", null: false });
  });
});

describe("Zehntel: Eingabe am Feld", () => {
  it("„10,4“ mit Komma oder Punkt ergibt „10.4“ und schaltet weiter", () => {
    expect(tippen(SCHUSS_ZEHNTEL, "10,4")).toMatchObject({ wert: "10.4", weiter: true });
    // Punkt und Komma des Ziffernblocks kommen als Taste „komma“ an.
    expect(tasteAusTastatur(".")).toEqual({ art: "komma" });
    expect(tasteAusTastatur("Decimal")).toEqual({ art: "komma" });
  });

  it("springt nicht nach der ersten Ziffer, solange ein Komma folgen kann", () => {
    expect(tippen(SCHUSS_ZEHNTEL, "1")).toMatchObject({ wert: "1.0", weiter: false });
    expect(tippen(SCHUSS_ZEHNTEL, "9")).toMatchObject({ wert: "9.0", weiter: false });
    expect(tippen(SCHUSS_ZEHNTEL, "10")).toMatchObject({ wert: "10.0", weiter: false });
    expect(tippen(SCHUSS_ZEHNTEL, "9,")).toMatchObject({ wert: "9.0", weiter: false });
  });

  it("setzt das Komma selbst, wenn die Ziffer nur dahinter passt", () => {
    expect(tippen(SCHUSS_ZEHNTEL, "98")).toMatchObject({ wert: "9.8", weiter: true });
    expect(tippen(SCHUSS_ZEHNTEL, "104")).toMatchObject({ wert: "10.4", weiter: true });
    expect(tippen(SCHUSS_ZEHNTEL, "100")).toMatchObject({ wert: "10.0", weiter: true });
  });

  it("„0“ ist ein Fehlschuss und schaltet sofort weiter", () => {
    expect(tippen(SCHUSS_ZEHNTEL, "0")).toMatchObject({ wert: "0.0", weiter: true });
  });

  it("lehnt Werte zwischen 0 und 1,0 mit Hinweis ab", () => {
    const komma = zahlTaste(SCHUSS_ZEHNTEL, FRISCH, undefined, { art: "komma" });
    const fuenf = zahlTaste(SCHUSS_ZEHNTEL, komma.eingabe, undefined, {
      art: "ziffer",
      ziffer: "5",
    });
    expect(fuenf).toMatchObject({ abgelehnt: true, grund: "zu_klein" });
  });

  it("lehnt Werte über dem Höchstwert mit Hinweis ab (Seriensumme)", () => {
    // 109 ist die Höchstsumme: fertig, weiter.
    expect(tippen(SUMME_ZEHNTEL, "109")).toMatchObject({ wert: "109.0", weiter: true });
    const zuViel = zahlTaste(SUMME_ZEHNTEL, { text: "109,", frisch: false }, "109.0", {
      art: "ziffer",
      ziffer: "5",
    });
    expect(zuViel).toMatchObject({ abgelehnt: true, grund: "zu_gross" });
    expect(tippen(SUMME_ZEHNTEL, "104,3")).toMatchObject({ wert: "104.3", weiter: true });
    // Bei der Summe kann „0“ noch „0,5“ werden: kein selbsttätiges Weiter.
    expect(tippen(SUMME_ZEHNTEL, "0")).toMatchObject({ wert: "0.0", weiter: false });
  });

  it("Ziffernfeld sperrt nur, was nicht passt", () => {
    const zehnKomma = tippen(SCHUSS_ZEHNTEL, "10,").eingabe;
    expect(zifferErlaubt(SCHUSS_ZEHNTEL, zehnKomma, "9")).toBe(true);
    const nullKomma = tippen(SCHUSS_ZEHNTEL, ",").eingabe;
    expect(zifferErlaubt(SCHUSS_ZEHNTEL, nullKomma, "0")).toBe(true);
    expect(zifferErlaubt(SCHUSS_ZEHNTEL, nullKomma, "5")).toBe(false);
  });

  it("Rück bearbeitet den gespeicherten Wert", () => {
    expect(tippen(SCHUSS_ZEHNTEL, "<", "10.4")).toMatchObject({ wert: "10.0" });
    expect(tippen(SCHUSS_ZEHNTEL, "<<<<", "10.4").wert).toBeUndefined();
  });

  it("ausgeschriebener Höchstwert „109,0“: „,0“ landet nicht als Zehner 0 im nächsten Feld", () => {
    const ZEHNER: FeldBeschreibung = {
      key: "tens",
      label: "Zehner",
      kind: "integer",
      required: false,
      min: 0,
      max: 10,
    };
    // Gefunden beim DSB-Probelauf: „1090“ bzw. „109,0“ ergab 109,0 und Zehner 0 (Server: 422).
    const ausgeschrieben = folge(2, "109,0>6", [], [SUMME_ZEHNTEL, ZEHNER]);
    expect(ausgeschrieben.jeSerie[0]).toEqual(["109.0", 6]);
    expect(folge(2, "109,06", [], [SUMME_ZEHNTEL, ZEHNER]).jeSerie[0]).toEqual(["109.0", 6]);
    // Ohne Komma bleibt die „0“ eine Eingabe im nächsten Feld (Zehner 0 ist erlaubt).
    expect(folge(2, "1090", [], [SUMME_ZEHNTEL, ZEHNER]).jeSerie[0]).toEqual(["109.0", 0]);
    // Fehlschuss „0,0“: ein Schuss, nicht zwei.
    const schuesse = Array.from({ length: 3 }, () => SCHUSS_ZEHNTEL);
    expect(folge(1, "0,098", [], schuesse).werte).toEqual(["0.0", "9.8", undefined]);
    // „10,9“ wie bisher; eine andere Ziffer nach dem Komma beginnt frisch.
    expect(folge(1, "109,98", [], schuesse).werte).toEqual(["10.9", "9.8", undefined]);
  });

  it("eine Serie Zehntel in einem Zug: jede Zahl schaltet selbst weiter", () => {
    const felder = Array.from({ length: 5 }, () => SCHUSS_ZEHNTEL);
    const { werte, index } = folge(1, "10,498010>9,9", [], felder);
    expect(werte).toEqual(["10.4", "9.8", "0.0", "10.0", "9.9"]);
    // Nach dem letzten Schuss ist kein Feld mehr aktiv.
    expect(index).toBeNull();
  });
});

describe("Treffer je Ziel", () => {
  it("1 und 0 gehen ohne Warten", () => {
    const erlaubt = ZIELE.allowed_values ?? [];
    expect(schussTaste(erlaubt, "", "1")).toEqual({ puffer: "", werte: [1] });
    expect(schussTaste(erlaubt, "", "0")).toEqual({ puffer: "", werte: [0] });
    expect(schussTaste(erlaubt, "", "5")).toEqual({ puffer: "", werte: [] });
  });
});
