import { describe, expect, it } from "vitest";
import { abschnittPfad, erweiterteFelder } from "../wettbewerbFormular";

describe("Aufteilung des Wettbewerb-Formulars", () => {
  it("lässt Stand, Startgeld, Mehrfachstart und Klassen oben", () => {
    const imErweitert = erweiterteFelder(true);
    for (const feld of ["range_id", "fee_first_cents", "fee_repeat_cents", "multi_start"]) {
      expect(imErweitert(feld)).toBe(false);
    }
    expect(imErweitert("max_starts")).toBe(false);
    expect(imErweitert("class_ids")).toBe(false);
    expect(imErweitert("")).toBe(false);
  });

  it("legt Ablauf, Wertung, Erfassung und Planung unter „Erweitert“", () => {
    const imErweitert = erweiterteFelder(true);
    for (const feld of [
      "definition",
      "capture_mode",
      "multi_start_rule",
      "combined_ranking",
      "planning",
      "heat_minutes",
      "changeover_minutes",
      abschnittPfad(0, "serien"),
    ]) {
      expect(imErweitert(feld)).toBe(true);
    }
  });

  it("zeigt den Namen nur bei abgewandelten Wettbewerben oben", () => {
    expect(erweiterteFelder(true)("name")).toBe(true);
    expect(erweiterteFelder(false)("name")).toBe(false);
  });
});
