import { describe, expect, it } from "vitest";
import { beschreibeWertung, type WertungOffen } from "./wertung";

describe("beschreibeWertung", () => {
  it("beschreibt Fallscheibe ohne Gleichstandsregel", () => {
    const klartext = beschreibeWertung({
      modell: "zeit_plus_zuschlaege",
      rangfolge: "aufsteigend",
      geprueft: true,
    });
    expect(klartext.name).toBe("Zeit plus Zuschläge");
    expect(klartext.saetze).toEqual([
      "Gewertet wird die Summe der Zeiten plus Zeitzuschläge für stehende Scheiben.",
      "Das niedrigere Ergebnis gewinnt.",
    ]);
    expect(klartext.gleichstand).toBeNull();
    expect(klartext.gleichheit).toBe("treffer");
  });

  it("nennt Abzug, Untergrenze und Gleichstandskriterien bei Mehrdistanz", () => {
    const klartext = beschreibeWertung({
      modell: "ringe_mit_zeitabzug",
      rangfolge: "absteigend",
      geprueft: true,
      abzug_je_voller_sekunde_ueber_sollzeit: 1,
      min_teilergebnis: 0,
      gleichstand: ["zehner", "parcours_zeit"],
    });
    expect(klartext.saetze).toContain("Abzug: 1 Ring je voller Sekunde über der Sollzeit.");
    expect(klartext.saetze).toContain("Ein Teilergebnis kann nicht unter 0 fallen.");
    expect(klartext.gleichstand).toEqual([
      "die höhere Zahl der Zehner",
      "die niedrigere Durchgangszeit",
    ]);
  });

  it("zeigt unbekannte Modelle und Kriterien mit ihrem Schlüssel", () => {
    const klartext = beschreibeWertung({
      modell: "punkte_nach_tabelle",
      rangfolge: "absteigend",
      geprueft: false,
      gleichstand: ["los_entscheid"],
    });
    expect(klartext.name).toBe("Modell „punkte_nach_tabelle“");
    expect(klartext.gleichstand).toEqual(["los entscheid"]);
  });

  it("beschreibt Zehntelwertung, Stechen und die DSB-Kriterien", () => {
    const klartext = beschreibeWertung(
      {
        modell: "ringe",
        rangfolge: "absteigend",
        geprueft: false,
        gleichstand: ["stechen", "letzte_serie_rueckwaerts", "zehntel_gesamt"],
        zehntelwertung: true,
        stechen_bis_platz: 3,
        hoechstergebnis_gleicher_rang: true,
      } as WertungOffen,
      "de",
    );

    expect(klartext.saetze).toContain("Gewertet wird in Zehnteln (0 und 1,0 bis 10,9).");
    expect(klartext.saetze).toContain(
      "Wer das erzielbare Höchstergebnis erreicht, wird ohne Finale nicht unterschieden und erhält den gleichen Rang.",
    );
    expect(klartext.saetze).toContain("Bei Ringgleichheit auf den Plätzen 1 bis 3 wird gestochen.");
    expect(klartext.gleichstand).toEqual([
      "ein Stechen",
      "das bessere Ergebnis der letzten Zehnerserie, dann der vorletzten und so weiter",
      "das höhere Ergebnis in Zehnteln",
    ]);
  });

  it("nennt Stechen beim Höchstergebnis und die Kette je Platz (Auflage)", () => {
    const klartext = beschreibeWertung(
      {
        modell: "ringe",
        rangfolge: "absteigend",
        geprueft: true,
        gleichstand: ["letzte_serie_rueckwaerts", "zehner"],
        stechen_bei_hoechstergebnis: true,
        gleichstand_bis_platz: 6,
        gleichstand_danach: [],
      } as WertungOffen,
      "de",
    );
    expect(klartext.saetze).toContain(
      "Erreichen mehrere das erzielbare Höchstergebnis, entscheidet zwischen ihnen ein Stechen.",
    );
    expect(klartext.saetze).toContain(
      "Die Reihenfolge unten gilt für Gleichstände auf den Plätzen 1 bis 6.",
    );
    expect(klartext.saetze).toContain("Ab Platz 7 erhalten Gleiche denselben Platz.");
  });

  it("vergleicht bei Treffern die Serien wie geschossen, sonst Zehnerserien", () => {
    const wertung = {
      modell: "ringe",
      rangfolge: "absteigend",
      geprueft: true,
      gleichstand: ["letzte_serie_rueckwaerts"],
    } as WertungOffen;
    const treffer = { varianten: [{ abschnitte: [{ ringwerte: [1, 0] }] }] };

    expect(beschreibeWertung(wertung, "de", treffer).gleichstand).toEqual([
      "das bessere Ergebnis der letzten Serie, dann der vorletzten und so weiter",
    ]);
    expect(
      beschreibeWertung(
        { ...wertung, gleichstand_serie: "zehn_schuss" } as WertungOffen,
        "de",
        treffer,
      ).gleichstand,
    ).toEqual(["das bessere Ergebnis der letzten Zehnerserie, dann der vorletzten und so weiter"]);
  });

  it("spricht bei reinen Treffern von Treffergleichheit, sonst von Ringgleichheit", () => {
    const wertung: WertungOffen = { modell: "ringe", rangfolge: "absteigend", geprueft: true };
    const ablauf = (ringwerte: number[] | null) => ({
      varianten: [{ abschnitte: [{ ringwerte }, { ringwerte: null }] }],
    });

    expect(beschreibeWertung(wertung, "de", ablauf([1, 0])).gleichheit).toBe("treffer");
    expect(beschreibeWertung(wertung, "de", ablauf([10, 9, 8])).gleichheit).toBe("ringe");
    expect(beschreibeWertung(wertung, "de", ablauf(null)).gleichheit).toBe("ringe");
    expect(beschreibeWertung(wertung, "de").gleichheit).toBe("ringe");
    expect(beschreibeWertung(wertung, "de", ablauf([1, 0]), "dsb").gleichheit).toBe("ergebnis");
  });
});
