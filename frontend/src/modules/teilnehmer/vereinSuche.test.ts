import { describe, expect, it } from "vitest";
import { ApiFehler } from "../../api/client";
import { vereinFehlerAus } from "./PersonFormular";
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

describe("vereinFehlerAus", () => {
  const OHNE_RECHT = "Du darfst keine neuen Vereine anlegen.";

  it("meldet 403 beim Speichern mit neuem Verein am Feld", () => {
    const fehler = new ApiFehler("verboten", "/persons", 403, "Zum Anlegen fehlt club.edit.");
    expect(vereinFehlerAus(fehler, true, OHNE_RECHT)).toBe(OHNE_RECHT);
  });

  it("lässt 403 ohne neuen Verein nicht am Vereinsfeld erscheinen", () => {
    const fehler = new ApiFehler("verboten", "/persons", 403, "Berechtigung fehlt.");
    expect(vereinFehlerAus(fehler, false, OHNE_RECHT)).toBeUndefined();
  });

  it("nimmt die Meldung des Servers am Feld club_name", () => {
    const fehler = new ApiFehler("anfrage", "/persons", 422, "Bitte prüfen.", undefined, [
      { feld: "name", meldung: "Name fehlt." },
      { feld: "club_name", meldung: "Bitte entweder club_id oder club_name angeben." },
    ]);
    expect(vereinFehlerAus(fehler, true, OHNE_RECHT)).toBe(
      "Bitte entweder club_id oder club_name angeben.",
    );
  });

  it("gibt für andere Fehler nichts zurück", () => {
    expect(
      vereinFehlerAus(new ApiFehler("server", "/persons", 500), true, OHNE_RECHT),
    ).toBeUndefined();
    expect(vereinFehlerAus(new Error("x"), true, OHNE_RECHT)).toBeUndefined();
  });
});
