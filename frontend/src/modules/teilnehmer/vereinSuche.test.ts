import { describe, expect, it } from "vitest";
import { vereinTreffer } from "./vereinSuche";

const vereine = [
  { id: "1", name: "SSV Hubertus Altdorf", short: "SSV Altdorf" },
  { id: "2", name: "SV Tell Musterstadt", short: "SV Tell" },
  { id: "3", name: "Schützengilde Neustadt", short: null },
];

describe("vereinTreffer", () => {
  it("ohne Suchtext alle Vereine", () => {
    expect(vereinTreffer(vereine, " ").treffer).toHaveLength(3);
  });

  it("bietet ähnliche Vereine wortweise an, wenn nichts direkt passt", () => {
    const ergebnis = vereinTreffer(vereine, "SV Hubertus Neuhausen");
    expect(ergebnis.treffer).toEqual([]);
    expect(ergebnis.aehnlich.map((v) => v.id)).toEqual(["1"]);
    expect(ergebnis.exakt).toBe(false);
  });

  it("zählt ein genau passendes Kürzel als vorhanden", () => {
    const ergebnis = vereinTreffer(vereine, "sv tell");
    expect(ergebnis.exakt).toBe(true);
    expect(ergebnis.treffer.map((v) => v.id)).toEqual(["2"]);
  });

  it("ignoriert Umlaute und kurze Wörter beim Ähnlichkeitsvergleich", () => {
    expect(vereinTreffer(vereine, "Schuetzengilde").treffer.map((v) => v.id)).toEqual(["3"]);
    expect(vereinTreffer(vereine, "SV e.V. Irgendwo").aehnlich).toEqual([]);
  });
});
