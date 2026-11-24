import { describe, expect, it } from "vitest";
import type { AbschnittWertung, Formular, SerienWertung } from "./api";
import {
  aenderungen,
  aenderungsOrt,
  entwurfAus,
  erreichbar,
  erstesOffenes,
  fehlstellen,
  fertigeSerien,
  gleicheRohwerte,
  meldungenFuer,
  naechstes,
  normalerPfad,
  reihenfolge,
  rohwerteAus,
  setzeWert,
  uebrigeMeldungen,
  voriges,
  zeitenUeberGrenze,
  zielNachStatus,
} from "./rohwerte";
import { FALLSCHEIBE, PRAEZISION, wertung } from "./testdaten";

const leer = entwurfAus({});

/** Fallscheibe, deren Status keine `unscored_fields` kennt (älterer Server): Die Zeit entfällt. */
const OHNE_UNGEWERTETE: Formular = {
  ...FALLSCHEIBE,
  sections: FALLSCHEIBE.sections.map((abschnitt) => ({
    ...abschnitt,
    series: abschnitt.series.map((serie) => ({
      ...serie,
      fields: serie.fields.map((feld) =>
        feld.options
          ? { ...feld, options: feld.options.map((o) => ({ ...o, unscored_fields: [] })) }
          : feld,
      ),
    })),
  })),
};

describe("Rohwerte aus dem Entwurf", () => {
  it("baut Serien nach dem Format des Servers, leere Serien als null", () => {
    let e = setzeWert(leer, { abschnitt: "fallscheibe", serie: 1, key: "time_cs" }, 1284);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 1, key: "standing" }, 1);
    expect(rohwerteAus(FALLSCHEIBE, e)).toEqual({
      sections: { fallscheibe: { series: [null, { time_cs: 1284, standing: 1 }] } },
    });
  });

  it("schickt erfasste Werte auch dann mit, wenn der gewählte Status sie in keiner Liste führt", () => {
    let e = setzeWert(leer, { abschnitt: "fallscheibe", serie: 0, key: "time_cs" }, 1500);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 0, key: "standing" }, 2);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 0, key: "status" }, "time_limit");
    expect(rohwerteAus(OHNE_UNGEWERTETE, e)).toEqual({
      sections: { fallscheibe: { series: [{ time_cs: 1500, standing: 2, status: "time_limit" }] } },
    });
    // Zurück auf „regulär“: Die Zeit bleibt, „status“ entfällt (Standard).
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 0, key: "status" }, "normal");
    expect(rohwerteAus(OHNE_UNGEWERTETE, e)).toEqual({
      sections: { fallscheibe: { series: [{ time_cs: 1500, standing: 2 }] } },
    });
  });

  it("Abbruch durch den Schützen: die erfasste Zeit geht mit (nicht gewertet, nie verworfen)", () => {
    let e = setzeWert(leer, { abschnitt: "fallscheibe", serie: 1, key: "time_cs" }, 2500);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 1, key: "status" }, "aborted_by_shooter");
    expect(rohwerteAus(FALLSCHEIBE, e)).toEqual({
      sections: {
        fallscheibe: { series: [null, { time_cs: 2500, status: "aborted_by_shooter" }] },
      },
    });
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 1, key: "standing" }, 1);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 1, key: "status" }, "time_limit");
    expect(rohwerteAus(FALLSCHEIBE, e)).toEqual({
      sections: {
        fallscheibe: { series: [null, { time_cs: 2500, status: "time_limit", standing: 1 }] },
      },
    });
    // Waffenstörung: Zeit und stehende Scheiben bleiben beide erhalten.
    e = setzeWert(
      e,
      { abschnitt: "fallscheibe", serie: 1, key: "status" },
      "malfunction_before_first_shot",
    );
    expect(rohwerteAus(FALLSCHEIBE, e)).toEqual({
      sections: {
        fallscheibe: {
          series: [null, { time_cs: 2500, status: "malfunction_before_first_shot", standing: 1 }],
        },
      },
    });
  });

  it("die Gesamtzeit eines Abschnitts hängt an keinem Serienstatus", () => {
    let e = setzeWert(leer, { abschnitt: "fallscheibe", serie: null, key: "time_cs" }, 9000);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 0, key: "status" }, "aborted_by_shooter");
    expect(rohwerteAus(FALLSCHEIBE, e)).toEqual({
      sections: { fallscheibe: { series: [{ status: "aborted_by_shooter" }], time_cs: 9000 } },
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

  it("lässt Felder aus, die der Status weder braucht noch erlaubt", () => {
    const e = setzeWert(leer, { abschnitt: "fallscheibe", serie: 0, key: "status" }, "time_limit");
    const ids = reihenfolge(OHNE_UNGEWERTETE, e).map((r) => r.id);
    expect(ids[0]).toBe("sections.fallscheibe.series.0.standing");
  });

  it("nicht gewertete Felder: antippbar, aber keine Lücke und nie von selbst angesteuert", () => {
    let e = setzeWert(leer, { abschnitt: "fallscheibe", serie: 0, key: "time_cs" }, 1200);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 0, key: "standing" }, 0);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 1, key: "status" }, "aborted_by_shooter");
    const refs = reihenfolge(FALLSCHEIBE, e);
    const zeit = refs.find((r) => r.id === "sections.fallscheibe.series.1.time_cs");
    expect(zeit?.ungewertet).toBe(true);
    expect(refs.find((r) => r.id === "sections.fallscheibe.series.1.standing")?.ungewertet).toBe(
      undefined,
    );
    // Erstes offenes Feld: die stehenden Scheiben, nicht die leere, nicht gewertete Zeit.
    expect(erstesOffenes(refs, e)?.id).toBe("sections.fallscheibe.series.1.standing");
    // Weiter von Serie 1 springt über die Zeit hinweg, zurück ebenso.
    expect(naechstes(refs, "sections.fallscheibe.series.0.standing")?.id).toBe(
      "sections.fallscheibe.series.1.standing",
    );
    expect(voriges(refs, "sections.fallscheibe.series.1.standing")?.id).toBe(
      "sections.fallscheibe.series.0.standing",
    );
    // Von der angetippten Zeit geht es mit „weiter“ in die stehenden Scheiben.
    expect(naechstes(refs, "sections.fallscheibe.series.1.time_cs")?.id).toBe(
      "sections.fallscheibe.series.1.standing",
    );
    // Lücken: nur die stehenden Scheiben, keine Zeit.
    expect(fehlstellen(FALLSCHEIBE, e).map((f) => f.felder)).toEqual([["Stehende Scheiben"]]);
    // Eine nicht gewertete Zeit über der Grenze ist kein Fehler am Feld.
    const lang = setzeWert(e, { abschnitt: "fallscheibe", serie: 1, key: "time_cs" }, 20000);
    expect(zeitenUeberGrenze(FALLSCHEIBE, lang)).toEqual([]);
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

  it("QA G-5: nach der Statuswahl ins erste leere Feld der Serie, nie in ein Feld mit Wert", () => {
    let e = setzeWert(leer, { abschnitt: "fallscheibe", serie: 1, key: "time_cs" }, 1500);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 1, key: "status" }, "time_limit");
    // Serie 2 · Zeit entfällt mit „Zeitlimit“; leer ist dort nur noch „Stehende Scheiben“.
    expect(zielNachStatus(reihenfolge(FALLSCHEIBE, e), e, "fallscheibe", 1)?.id).toBe(
      "sections.fallscheibe.series.1.standing",
    );
    // Serie voll: das erste leere Feld überhaupt (hier Serie 1).
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 1, key: "standing" }, 2);
    expect(zielNachStatus(reihenfolge(FALLSCHEIBE, e), e, "fallscheibe", 1)?.id).toBe(
      "sections.fallscheibe.series.0.time_cs",
    );
    // Alles gefüllt: kein Feld (ein Wert wird nur nach ausdrücklicher Auswahl geändert).
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 0, key: "time_cs" }, 1000);
    e = setzeWert(e, { abschnitt: "fallscheibe", serie: 0, key: "standing" }, 0);
    expect(zielNachStatus(reihenfolge(FALLSCHEIBE, e), e, "fallscheibe", 1)).toBeNull();
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

  it("eine Serie, die der Server vollständig nennt, hat keine Lücke (Serie nicht beendet)", () => {
    const e = entwurfAus({
      sections: { praezision: { series: [{ status: "unfinished", shots: [10] }] } },
    });
    const serie = { complete: true } as SerienWertung;
    const offen = { complete: false } as SerienWertung;
    const w = wertung({
      sections: [{ id: "praezision", series: [serie, offen] } as AbschnittWertung],
    });
    const fertig = fertigeSerien(w);
    expect([...fertig]).toEqual(["sections.praezision.series.0"]);
    expect(fehlstellen(PRAEZISION, e).map((f) => f.pfad)).toEqual([
      "sections.praezision.series.0",
      "sections.praezision.series.1",
    ]);
    expect(fehlstellen(PRAEZISION, e, fertig).map((f) => f.pfad)).toEqual([
      "sections.praezision.series.1",
    ]);
    expect(fertigeSerien(null).size).toBe(0);
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
