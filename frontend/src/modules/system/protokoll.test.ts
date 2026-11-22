import { describe, expect, it } from "vitest";
import { detailsText, vorgangText } from "./Protokoll";

describe("Protokoll: Vorgang", () => {
  const eigene = (action: string) =>
    action === "display.created" ? "Anzeige angelegt" : undefined;

  it("nimmt den Klartext des Servers", () => {
    expect(
      vorgangText(
        { action: "result.corrected", action_text: "Ergebnis korrigiert" },
        eigene,
        "Weiterer Vorgang",
      ),
    ).toBe("Ergebnis korrigiert");
  });

  it("fällt auf die eigene Übersetzung zurück, wenn der Server nur den Schlüssel liefert", () => {
    expect(
      vorgangText(
        { action: "display.created", action_text: "display.created" },
        eigene,
        "Weiterer Vorgang",
      ),
    ).toBe("Anzeige angelegt");
    expect(
      vorgangText({ action: "neu.etwas", action_text: "neu.etwas" }, eigene, "Weiterer Vorgang"),
    ).toBe("Weiterer Vorgang");
  });
});

describe("Protokoll: Details", () => {
  it("fasst Ergebnis vorher und nachher zusammen und blendet die laufende Nummer aus", () => {
    const text = detailsText({
      seq: 10,
      score: "54,00",
      score_before: "44,00",
      competition_code: "4403",
    });
    expect(text).toBe("score: 44,00 → 54,00 · competition_code: 4403");
  });
});

describe("Protokoll: Details mit Zeitpunkt (QA KLEIN 1)", () => {
  it("schreibt Beginn und Ende eines Durchgangs lesbar, wenn eine Zeit-Hilfe da ist", () => {
    const details = { number: 2, starts_at: "2026-11-22T04:15:00+00:00" };
    expect(detailsText(details)).toBe("number: 2 · starts_at: 2026-11-22T04:15:00+00:00");
    expect(
      detailsText(details, {
        feld: (k) => ({ number: "Nummer", starts_at: "Beginn" })[k] ?? k,
        wert: (w) => w,
        name: () => undefined,
        geld: String,
        jaNein: String,
        zeit: () => "22.11.2026, 05:15",
      }),
    ).toBe("Nummer: 2 · Beginn: 22.11.2026, 05:15");
  });
});
