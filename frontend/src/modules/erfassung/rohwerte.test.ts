import { describe, expect, it } from "vitest";
import {
  aenderungen,
  aenderungsOrt,
  entwurfAus,
  erreichbar,
  erstesOffenes,
  fehlstellen,
  gleicheRohwerte,
  meldungenFuer,
  naechstes,
  normalerPfad,
  reihenfolge,
  rohwerteAus,
  setzeWert,
  uebrigeMeldungen,
  zeitenUeberGrenze,
} from "./rohwerte";
import { FALLSCHEIBE, PRAEZISION } from "./testdaten";

const leer = entwurfAus({});

describe("Rohwerte aus dem Entwurf", () => {
  it("baut Serien nach dem Format des Servers, leere Serien als null", () => {
    let e = setzeWert(leer, { abschnitt: "fallscheibe", serie: 1, key: "time_cs" }, 1284);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 1, key: "standing" }, 1);
    expect(rohwerteAus(FALLSCHEIBE, e)).toEqual({
      sections: { fallscheibe: { series: [null, { time_cs: 1284, standing: 1 }] } },
    });
  });

  it("lässt Felder weg, die der gewählte Status nicht braucht, und behält sie im Entwurf", () => {
    let e = setzeWert(leer, { abschnitt: "fallscheibe", serie: 0, key: "time_cs" }, 1500);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 0, key: "standing" }, 2);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 0, key: "status" }, "time_limit");
    expect(rohwerteAus(FALLSCHEIBE, e)).toEqual({
      sections: { fallscheibe: { series: [{ status: "time_limit", standing: 2 }] } },
    });
    // Zurück auf „regulär“: Die Zeit ist wieder da, „status“ entfällt (Standard).
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 0, key: "status" }, "normal");
    expect(rohwerteAus(FALLSCHEIBE, e)).toEqual({
      sections: { fallscheibe: { series: [{ time_cs: 1500, standing: 2 }] } },
    });
  });

  it("ein leerer Entwurf ergibt leere Rohwerte", () => {
    expect(rohwerteAus(FALLSCHEIBE, leer)).toEqual({});
    expect(gleicheRohwerte({}, { sections: {} })).toBe(true);
  });

  it("Schüsse ersetzen eine erfasste Seriensumme und umgekehrt", () => {
    const vorher = entwurfAus({ sections: { praezision: { series: [{ sum: 90, tens: 2 }] } } });
    const mitSchuss = setzeWert(
      vorher,
      { abschnitt: "praezision", serie: 0, key: "shots", schuss: 0 },
      "X",
    );
    expect(rohwerteAus(PRAEZISION, mitSchuss)).toEqual({
      sections: { praezision: { series: [{ shots: ["X"] }] } },
    });
    const mitSumme = setzeWert(mitSchuss, { abschnitt: "praezision", serie: 0, key: "sum" }, 88);
    expect(rohwerteAus(PRAEZISION, mitSumme)).toEqual({
      sections: { praezision: { series: [{ sum: 88 }] } },
    });
  });

  it("Löschen eines Schusses kürzt die Liste ab dort", () => {
    let e = leer;
    for (const [i, w] of [10, 9, 8].entries()) {
      e = setzeWert(e, { abschnitt: "praezision", serie: 0, key: "shots", schuss: i }, w);
    }
    e = setzeWert(e, { abschnitt: "praezision", serie: 0, key: "shots", schuss: 2 }, undefined);
    expect(rohwerteAus(PRAEZISION, e)).toEqual({
      sections: { praezision: { series: [{ shots: [10, 9] }] } },
    });
  });

  it("vergleicht Rohwerte unabhängig von der Reihenfolge der Schlüssel", () => {
    expect(
      gleicheRohwerte(
        { sections: { a: { series: [{ time_cs: 1, standing: 0 }] } } },
        { sections: { a: { series: [{ standing: 0, time_cs: 1 }] } } },
      ),
    ).toBe(true);
  });
});

describe("Reihenfolge der Eingabeplätze", () => {
  it("überspringt die Status-Auswahl und gestrichene Serien", () => {
    const ids = reihenfolge(FALLSCHEIBE, leer).map((r) => r.id);
    expect(ids).toEqual([
      "sections.fallscheibe.series.0.time_cs",
      "sections.fallscheibe.series.0.standing",
      "sections.fallscheibe.series.1.time_cs",
      "sections.fallscheibe.series.1.standing",
    ]);
  });

  it("nimmt aufgeklappte gestrichene Serien auf", () => {
    const ids = reihenfolge(FALLSCHEIBE, leer, {
      aufgeklappt: new Set(["sections.fallscheibe.series.2"]),
    }).map((r) => r.id);
    expect(ids).toContain("sections.fallscheibe.series.2.standing");
  });

  it("lässt Felder aus, die der Status nicht braucht", () => {
    const e = setzeWert(leer, { abschnitt: "fallscheibe", serie: 0, key: "status" }, "time_limit");
    const ids = reihenfolge(FALLSCHEIBE, e).map((r) => r.id);
    expect(ids[0]).toBe("sections.fallscheibe.series.0.standing");
    const stoerung = setzeWert(
      leer,
      { abschnitt: "fallscheibe", serie: 0, key: "status" },
      "malfunction_before_first_shot",
    );
    expect(reihenfolge(FALLSCHEIBE, stoerung)[0]?.id).toBe("sections.fallscheibe.series.1.time_cs");
  });

  it("Schüsse sind einzelne Plätze; ein Tipp hinter die Lücke springt zur Lücke", () => {
    const refs = reihenfolge(PRAEZISION, leer);
    expect(refs).toHaveLength(6);
    const dritter = refs[2];
    expect(dritter && erreichbar(leer, dritter).schuss).toBe(0);
    expect(naechstes(refs, refs[2]?.id ?? null)?.id).toBe("sections.praezision.series.1.shots.0");
  });

  it("das erste offene Pflichtfeld zuerst", () => {
    const e = setzeWert(leer, { abschnitt: "fallscheibe", serie: 0, key: "time_cs" }, 1200);
    expect(erstesOffenes(reihenfolge(FALLSCHEIBE, e), e)?.id).toBe(
      "sections.fallscheibe.series.0.standing",
    );
  });
});

describe("Meldungen am Feld", () => {
  it("ordnet Pfade des Servers den Feldern zu", () => {
    const pfad = normalerPfad("raw.sections.fallscheibe.series[1].standing");
    expect(pfad).toBe("sections.fallscheibe.series.1.standing");
    const meldungen = [
      { pfad, meldung: "höchstens 5" },
      { pfad: "", meldung: "allgemein" },
    ];
    expect(meldungenFuer(meldungen, "sections.fallscheibe.series.1")).toHaveLength(1);
    expect(uebrigeMeldungen(FALLSCHEIBE, meldungen)).toEqual([{ pfad: "", meldung: "allgemein" }]);
  });

  it("findet Zeiten über der Grenze der Formularbeschreibung (max in Hundertstel)", () => {
    let e = setzeWert(leer, { abschnitt: "fallscheibe", serie: 0, key: "time_cs" }, 18000);
    expect(zeitenUeberGrenze(FALLSCHEIBE, e)).toEqual([]);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 1, key: "time_cs" }, 18001);
    const ueber = zeitenUeberGrenze(FALLSCHEIBE, e);
    expect(ueber.map((u) => [u.ref.id, u.grenze])).toEqual([
      ["sections.fallscheibe.series.1.time_cs", 18000],
    ]);
  });

  it("beschreibt Änderungen im Verlauf mit den Namen der Maske", () => {
    const schuss = (nr: number) => `Schuss ${nr}`;
    expect(aenderungsOrt(FALLSCHEIBE, "sections.fallscheibe.series[1].time_cs", schuss).text).toBe(
      "Serie 2 · Zeit",
    );
    expect(aenderungsOrt(PRAEZISION, "sections.praezision.series[0].shots[2]", schuss).text).toBe(
      "Serie 1 · Schuss 3",
    );
    expect(aenderungsOrt(PRAEZISION, "irgendwas", schuss).text).toBe("irgendwas");
  });
});

describe("Vollständigkeit und Änderungen", () => {
  it("nennt je Serie die fehlenden Pflichtfelder", () => {
    const e = entwurfAus({
      sections: { fallscheibe: { series: [{ time_cs: 1100, standing: 0 }, { time_cs: 900 }] } },
    });
    const fehlt = fehlstellen(FALLSCHEIBE, e);
    expect(fehlt.map((f) => [f.pfad, f.felder])).toEqual([
      ["sections.fallscheibe.series.1", ["Stehende Scheiben"]],
    ]);
    expect(fehlt[0]?.ziel.id).toBe("sections.fallscheibe.series.1.standing");
    expect(fehlstellen(FALLSCHEIBE, leer).map((f) => f.felder)).toEqual([
      ["Zeit", "Stehende Scheiben"],
      ["Zeit", "Stehende Scheiben"],
    ]);
  });

  it("Waffenstörung braucht keine Werte: keine Lücke", () => {
    const e = entwurfAus({
      sections: {
        fallscheibe: {
          series: [{ status: "malfunction_before_first_shot" }, { time_cs: 900, standing: 1 }],
        },
      },
    });
    expect(fehlstellen(FALLSCHEIBE, e)).toEqual([]);
  });

  it("stellt geänderte Felder alt und neu gegenüber", () => {
    const alt = { sections: { fallscheibe: { series: [{ time_cs: 1100, standing: 1 }] } } };
    const neu = { sections: { fallscheibe: { series: [{ time_cs: 1100, standing: 0 }] } } };
    expect(aenderungen(FALLSCHEIBE, alt, neu)).toEqual([
      {
        ort: "Serie 1 · Stehende Scheiben",
        feld: expect.objectContaining({ key: "standing" }),
        vorher: 1,
        nachher: 0,
      },
    ]);
    expect(aenderungen(FALLSCHEIBE, alt, alt)).toEqual([]);
  });
});
