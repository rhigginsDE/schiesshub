import { describe, expect, it } from "vitest";
import { ApiFehler } from "../../api/client";
import { ablehnungsgrund } from "./importFehler";

const abgelehnt = (detail: string) => new ApiFehler("anfrage", "/persons/import", 400, detail);

describe("ablehnungsgrund", () => {
  it("erkennt die häufigen Gründe einer abgelehnten Datei", () => {
    expect(
      ablehnungsgrund(
        abgelehnt("Die Datei ist nicht in UTF-8 kodiert. Bitte als „CSV UTF-8“ speichern."),
      ),
    ).toEqual({ art: "kodierung" });
    expect(
      ablehnungsgrund(abgelehnt("Die Spalte „Vorname“ ist unbekannt. Erlaubt sind: …")),
    ).toEqual({
      art: "spalte_unbekannt",
      spalte: "Vorname",
    });
    expect(ablehnungsgrund(abgelehnt("Die Spalte „Name“ kommt doppelt vor."))).toEqual({
      art: "spalte_doppelt",
      spalte: "Name",
    });
    expect(ablehnungsgrund(abgelehnt("Die Datei ist leer."))?.art).toBe("leer");
    expect(
      ablehnungsgrund(abgelehnt("Die Datei enthält Zeichen, die sich nicht lesen lassen. …"))?.art,
    ).toBe("kodierung");
    expect(
      ablehnungsgrund(abgelehnt("Die Kopfzeile braucht eine Spalte „Name“ (oder …)."))?.art,
    ).toBe("name_fehlt");
  });

  it("gibt unbekannte Meldungen des Servers weiter", () => {
    expect(ablehnungsgrund(abgelehnt("Etwas anderes."))).toEqual({
      art: "sonstig",
      meldung: "Etwas anderes.",
    });
  });

  it("ist kein Dateifehler bei Netz- oder Serverproblemen", () => {
    expect(ablehnungsgrund(new ApiFehler("netzwerk", "/persons/import"))).toBeNull();
    expect(ablehnungsgrund(new ApiFehler("server", "/persons/import", 500))).toBeNull();
    expect(ablehnungsgrund(new Error("x"))).toBeNull();
  });
});
