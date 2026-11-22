import { describe, expect, it, vi } from "vitest";
import { ApiFehler } from "../../api/client";
import { vereinSichern, vereinTreffer } from "./vereinSuche";

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

  it("stellt Vereine, deren Name oder Kürzel mit dem Suchtext beginnt, nach vorn", () => {
    const liste = [
      { id: "a", name: "Freie Schützen Tellingen", short: null },
      { id: "b", name: "SV Tell Musterstadt", short: "SV Tell" },
      { id: "c", name: "Tell-Schützen Bergheim", short: null },
    ];
    expect(vereinTreffer(liste, "tell").treffer.map((v) => v.id)).toEqual(["c", "a", "b"]);
    expect(vereinTreffer(liste, "sv").treffer.map((v) => v.id)).toEqual(["b"]);
  });

  it("ignoriert Umlaute und kurze Wörter beim Ähnlichkeitsvergleich", () => {
    expect(vereinTreffer(vereine, "Schuetzengilde").treffer.map((v) => v.id)).toEqual(["3"]);
    expect(vereinTreffer(vereine, "SV e.V. Irgendwo").aehnlich).toEqual([]);
  });
});

describe("vereinSichern", () => {
  const neu = { id: "9", name: "SG Probe 1920", short: null };

  it("nimmt einen vorhandenen Verein gleichen Namens, statt einen zweiten anzulegen", async () => {
    const anlegen = vi.fn();
    const verein = await vereinSichern("sv tell musterstadt", {
      vorhandene: vereine,
      anlegen,
      neuLaden: async () => vereine,
    });
    expect(verein.id).toBe("2");
    expect(anlegen).not.toHaveBeenCalled();
  });

  it("legt einen unbekannten Namen an", async () => {
    const anlegen = vi.fn(async () => neu);
    expect(
      await vereinSichern("SG Probe 1920", {
        vorhandene: vereine,
        anlegen,
        neuLaden: async () => [],
      }),
    ).toBe(neu);
    expect(anlegen).toHaveBeenCalledWith("SG Probe 1920");
  });

  it("nimmt bei „gibt es schon“ den inzwischen angelegten Verein", async () => {
    const konflikt = new ApiFehler("konflikt", "/clubs", 409, "Gibt es schon.");
    const verein = await vereinSichern("SG Probe 1920", {
      vorhandene: vereine,
      anlegen: async () => {
        throw konflikt;
      },
      neuLaden: async () => [...vereine, neu],
    });
    expect(verein).toBe(neu);
  });

  it("gibt andere Fehler weiter", async () => {
    const fehler = new ApiFehler("server", "/clubs", 500);
    await expect(
      vereinSichern("SG Probe 1920", {
        vorhandene: vereine,
        anlegen: async () => {
          throw fehler;
        },
        neuLaden: async () => [...vereine, neu],
      }),
    ).rejects.toBe(fehler);
  });
});
