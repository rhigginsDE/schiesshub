import { describe, expect, it } from "vitest";
import { type AbschnittOffen, abschnittAlsText, beschreibeAbschnitt, schussGesamt } from "./ablauf";

function abschnitt(felder: Partial<AbschnittOffen>): AbschnittOffen {
  return { id: "a", name: "Abschnitt", serien: 1, ...felder };
}

describe("abschnittAlsText", () => {
  it("beschreibt Fallscheibe mit Obergrenzen und Zuschlag", () => {
    const text = abschnittAlsText(
      abschnitt({
        serien: 4,
        ziele_je_serie: 5,
        max_schuss_je_serie: 6,
        max_zeit_je_serie_s: 60,
        zuschlag_je_stehender_scheibe_s: 10,
      }),
    );
    expect(text).toBe(
      "4 Serien · 5 Ziele · max. 6 Schuss · max. 1 Min. · +10 s je stehender Scheibe",
    );
  });

  it("hängt an, wenn die Zeit in die Wertung eingeht", () => {
    const text = abschnittAlsText(
      abschnitt({
        serien: 4,
        ziele_je_serie: 5,
        max_schuss_je_serie: 16,
        max_zeit_je_serie_s: 60,
        zeit_wird_gemessen: true,
        zuschlag_je_stehender_scheibe_s: 10,
      }),
    );
    expect(text).toBe(
      "4 Serien · 5 Ziele · max. 16 Schuss · max. 1 Min. · +10 s je stehender Scheibe · Zeit wird gemessen",
    );
  });

  it("beschreibt Präzision mit fester Schusszahl und Zeit", () => {
    expect(
      abschnittAlsText(abschnitt({ serien: 2, schuss_je_serie: 10, zeit_je_serie_s: 300 })),
    ).toBe("2 Serien · 10 Schuss · 5 Min.");
  });

  it("nutzt die Einzahl bei einer Serie und einem Ziel", () => {
    expect(abschnittAlsText(abschnitt({ serien: 1, schuss_je_serie: 5, ziele_je_serie: 1 }))).toBe(
      "1 Serie · 5 Schuss · 1 Ziel",
    );
  });

  it("listet wechselnde Zeiten je Serie", () => {
    expect(
      abschnittAlsText(
        abschnitt({ serien: 6, schuss_je_serie: 5, zeiten_s: [40, 40, 30, 30, 20, 20] }),
      ),
    ).toBe("6 Serien · 5 Schuss · Zeiten 40 / 40 / 30 / 30 / 20 / 20 s");
  });

  it("beschreibt Mehrdistanz mit Sollzeit und Abbruchzeit", () => {
    expect(
      abschnittAlsText(
        abschnitt({
          serien: 4,
          schuss_je_serie: 5,
          distanzen_m: [20, 15, 10, 5],
          zeit_wird_gemessen: true,
          sollzeit_s: 80,
          max_gesamtzeit_s: 160,
        }),
      ),
    ).toBe(
      "4 Serien · 5 Schuss · Distanzen 20 / 15 / 10 / 5 m · Sollzeit 80 s · Abbruch nach 160 s · Zeit wird gemessen",
    );
  });

  it("beschreibt Intervall mit Sichtzeit und Pause", () => {
    expect(
      abschnittAlsText(
        abschnitt({
          serien: 6,
          schuss_je_serie: 5,
          zeit_je_schuss_s: 8,
          pause_zwischen_schuessen_s: 12,
        }),
      ),
    ).toBe("6 Serien · 5 Schuss · 8 s je Schuss · 12 s Pause zwischen den Schüssen");
  });

  it("schreibt Dezimalwerte mit Komma", () => {
    expect(abschnittAlsText(abschnitt({ serien: 2, zuschlag_je_stehender_scheibe_s: 2.5 }))).toBe(
      "2 Serien · +2,5 s je stehender Scheibe",
    );
  });
});

describe("beschreibeAbschnitt", () => {
  it("lässt leere und falsche Angaben weg", () => {
    expect(
      beschreibeAbschnitt(
        abschnitt({ serien: 3, schuss_je_serie: null, zeit_wird_gemessen: false, zeiten_s: null }),
      ),
    ).toEqual(["3 Serien"]);
  });

  it("zeigt unbekannte Felder, statt sie zu verschlucken", () => {
    expect(beschreibeAbschnitt(abschnitt({ serien: 2, probeschuesse_je_serie: 3 }))).toEqual([
      "2 Serien",
      "probeschuesse je serie: 3",
    ]);
  });
});

describe("schussGesamt", () => {
  it("summiert feste Schusszahlen über alle Abschnitte", () => {
    expect(
      schussGesamt({
        id: "v",
        name: "Standard",
        abschnitte: [
          abschnitt({ serien: 4, schuss_je_serie: 5 }),
          abschnitt({ serien: 4, schuss_je_serie: 5 }),
        ],
      }),
    ).toBe(40);
  });

  it("gibt null zurück, wenn die Schusszahl nicht feststeht", () => {
    expect(
      schussGesamt({
        id: "v",
        name: "Standard",
        abschnitte: [abschnitt({ serien: 4, max_schuss_je_serie: 16 })],
      }),
    ).toBeNull();
  });
});
