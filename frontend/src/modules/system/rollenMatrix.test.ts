import { describe, expect, it } from "vitest";
import { codeGruppiert, formatRestzeit, initialen, pinGueltig } from "../auth/eingaben";
import { kopplungsAdresse } from "./Geraete";
import { detailsText } from "./Protokoll";
import {
  gleicheEintraege,
  gruppieren,
  textSchluessel,
  ueberMuster,
  umschalten,
} from "./rollenMatrix";

const bekannte = ["person.delete", "person.edit", "person.read", "club.edit", "backup.read"];

describe("umschalten", () => {
  it("fügt eine Berechtigung hinzu, wenn sie noch fehlt", () => {
    expect(umschalten(["club.edit"], bekannte, "person.read", true)).toEqual([
      "club.edit",
      "person.read",
    ]);
    expect(umschalten(["person.*"], bekannte, "person.read", true)).toEqual(["person.*"]);
  });

  it("entfernt einen Namen", () => {
    expect(umschalten(["club.edit", "person.read"], bekannte, "person.read", false)).toEqual([
      "club.edit",
    ]);
  });

  it("löst ein Muster auf und behält die übrigen", () => {
    expect(umschalten(["person.*", "club.edit"], bekannte, "person.edit", false)).toEqual([
      "person.delete",
      "person.read",
      "club.edit",
    ]);
  });

  it("löst auch den Stern auf", () => {
    const neu = umschalten(["*"], bekannte, "backup.read", false);
    expect(neu).not.toContain("backup.read");
    expect(neu).not.toContain("*");
    expect(neu).toHaveLength(bekannte.length - 1);
  });

  it("unbekannte Einträge bleiben stehen", () => {
    expect(umschalten(["result.*", "club.edit"], bekannte, "club.edit", false)).toEqual([
      "result.*",
    ]);
  });
});

describe("Matrix-Hilfen", () => {
  it("gruppiert nach Modul und sortiert", () => {
    const gruppen = gruppieren([
      { permission: "person.read", module: "teilnehmer", module_title: "Teilnehmer" },
      { permission: "backup.read", module: "backup", module_title: "Sicherung" },
      { permission: "club.edit", module: "teilnehmer", module_title: "Teilnehmer" },
    ]);
    expect(gruppen.map((g) => g.titel)).toEqual(["Sicherung", "Teilnehmer"]);
    expect(gruppen[1]?.berechtigungen).toEqual(["club.edit", "person.read"]);
  });

  it("nennt das Muster, über das ein Recht gilt", () => {
    expect(ueberMuster(["person.*"], "person.read")).toBe("person.*");
    expect(ueberMuster(["person.read"], "person.read")).toBeNull();
  });

  it("vergleicht ohne Reihenfolge", () => {
    expect(gleicheEintraege(["a", "b"], ["b", "a"])).toBe(true);
    expect(gleicheEintraege(["a"], ["a", "b"])).toBe(false);
  });

  it("macht Sprachschlüssel aus Namen", () => {
    expect(textSchluessel("backup.read")).toBe("backup_read");
    expect(textSchluessel("auth.login_failed")).toBe("auth_login_failed");
  });

  it("Details des Protokolls kurz", () => {
    expect(detailsText({ name: "Kasse 1", blocked: true, leer: null })).toBe(
      "name: Kasse 1 · blocked: true",
    );
  });

  it("Details des Protokolls in Klartext, ohne IDs, Geld in Euro", () => {
    const rolle = "2c22e880-61bb-488a-b3f4-954ad6a5cb91";
    const hilfen = {
      feld: (k: string) => ({ fee_cents: "Startgeld", role_id: "Rolle", from: "vorher" })[k] ?? k,
      wert: (w: string) => ({ called: "aufgerufen" })[w] ?? w,
      name: (id: string) => (id === rolle ? "Kasse" : undefined),
      geld: (cent: number) => `${(cent / 100).toFixed(2).replace(".", ",")} €`,
      jaNein: (w: boolean) => (w ? "ja" : "nein"),
    };
    expect(
      detailsText(
        {
          tournament_id: "78a0a62a-fd80-4ef3-876a-3e7ad7a332b6",
          start_ids: ["2e523d48-a9a5-495d-bae9-d7380f445b30"],
          fee_cents: [800, 500],
          from: "called",
        },
        hilfen,
      ),
    ).toBe("Startgeld: 8,00 € + 5,00 € · vorher: aufgerufen");
    expect(
      detailsText(
        { role_id: { before: rolle, after: "11111111-2222-4333-8444-555555555555" } },
        hilfen,
      ),
    ).toBe("Rolle: Kasse → –");
    expect(detailsText({ role_id: rolle, active: false }, hilfen)).toBe(
      "Rolle: Kasse · active: nein",
    );
  });

  it("Kopplungsadresse aus Herkunft und Pfad", () => {
    expect(kopplungsAdresse("/pair?code=ABC", "http://192.168.50.1")).toBe(
      "http://192.168.50.1/pair?code=ABC",
    );
  });
});

describe("Eingaben der Anmeldung", () => {
  it("gruppiert den Kopplungscode", () => {
    expect(codeGruppiert("abcdefghjk")).toBe("ABCDE-FGHJK");
    expect(codeGruppiert(" ABCDE-FGHJK ")).toBe("ABCDE-FGHJK");
  });

  it("prüft die PIN", () => {
    expect(pinGueltig("1234")).toBe(true);
    expect(pinGueltig("123")).toBe(false);
    expect(pinGueltig("12a4")).toBe(false);
  });

  it("formatiert die Restzeit", () => {
    expect(formatRestzeit(272)).toBe("4:32");
    expect(formatRestzeit(5)).toBe("0:05");
    expect(formatRestzeit(-3)).toBe("0:00");
  });

  it("bildet Initialen", () => {
    expect(initialen("Maria Brandt")).toBe("MB");
    expect(initialen("M. Brandt")).toBe("MB");
    expect(initialen("Kasse")).toBe("K");
    expect(initialen("Test-Admin")).toBe("TA");
  });
});
