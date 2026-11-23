import { describe, expect, it } from "vitest";
import { ApiFehler, istWartungsFehler } from "../api/client";
import { KEINE_WARTUNG, wartungAus } from "./wartung";

describe("Wartung während einer Wiederherstellung", () => {
  it("liest den Zustand vom Server", () => {
    expect(
      wartungAus({
        active: true,
        exclusive: false,
        message_de: "Die Sicherung wird gerade wiederhergestellt.",
        since: "2026-11-23T21:10:00Z",
      }),
    ).toEqual({
      active: true,
      exclusive: false,
      message_de: "Die Sicherung wird gerade wiederhergestellt.",
      since: "2026-11-23T21:10:00Z",
    });
    expect(wartungAus({ active: false, exclusive: false, message_de: null, since: null })).toEqual(
      KEINE_WARTUNG,
    );
  });

  it("versteht 503 mit code maintenance als Tausch der Datenbank", () => {
    expect(
      wartungAus({ detail: "Die Datenbank wird gerade getauscht.", code: "maintenance" }),
    ).toEqual({
      active: true,
      exclusive: true,
      message_de: "Die Datenbank wird gerade getauscht.",
      since: null,
    });
  });

  it("unbekannte Antworten heißen: keine Wartung", () => {
    expect(wartungAus(null)).toEqual(KEINE_WARTUNG);
    expect(wartungAus({ detail: "Nicht gefunden" })).toEqual(KEINE_WARTUNG);
  });

  it("erkennt Wartungsfehler an Status und code", () => {
    const wartung = new ApiFehler("netzwerk", "/x", 503, "…", 10, [], {}, "maintenance");
    expect(istWartungsFehler(wartung)).toBe(true);
    expect(istWartungsFehler(new ApiFehler("netzwerk", "/x", 503))).toBe(false);
    expect(istWartungsFehler(new Error("x"))).toBe(false);
  });
});
