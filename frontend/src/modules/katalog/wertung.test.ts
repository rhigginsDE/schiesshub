import { describe, expect, it } from "vitest";
import { beschreibeWertung } from "./wertung";

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
      "die niedrigere Parcourszeit",
    ]);
  });

  it("zeigt unbekannte Modelle und Kriterien mit ihrem Schlüssel", () => {
    const klartext = beschreibeWertung({
      modell: "punkte_nach_tabelle",
      rangfolge: "absteigend",
      geprueft: false,
      gleichstand: ["stechen"],
    });
    expect(klartext.name).toBe("Modell „punkte_nach_tabelle“");
    expect(klartext.gleichstand).toEqual(["stechen"]);
  });
});
