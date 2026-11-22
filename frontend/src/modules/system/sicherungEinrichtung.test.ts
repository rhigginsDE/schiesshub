import { describe, expect, it } from "vitest";
import type {
  SicherungsEinstellungen,
  SicherungsLauf,
  SicherungsStatus,
} from "../../api/typenSystem";
import { einrichtungsAufgaben, hauptaktion, naechsteAufgabe } from "./sicherungEinrichtung";

const einstellungen: SicherungsEinstellungen = {
  enabled: true,
  usb_enabled: true,
  snapshot_interval_minutes: 5,
  keep_local: 12,
  keep_usb: 48,
  warn_all_stations: true,
  warn_on_display: false,
  encrypt: true,
};

function status(teil: Partial<SicherungsStatus> = {}): SicherungsStatus {
  return {
    usb: { present: true, writable: true, free_bytes: 1e9, last_seen_at: "2026-11-22T00:00:00Z" },
    last_snapshot: null,
    last_usb_copy: null,
    journal: { pending: 0 },
    warning: null,
    passphrase_set: false,
    ...teil,
  };
}

const kopie: SicherungsLauf = {
  id: "1",
  started_at: "2026-11-22T00:00:00Z",
  finished_at: "2026-11-22T00:00:01Z",
  kind: "snapshot",
  target: "usb",
  file_name: "a.shbak",
  size_bytes: 10,
  sha256: "x",
  ok: true,
  error: null,
};

describe("Ersteinrichtung der Sicherung", () => {
  it("Stick erkannt, Passwort fehlt: Passwort festlegen ist die Hauptaktion", () => {
    const aufgaben = einrichtungsAufgaben(status(), einstellungen, []);
    expect(aufgaben).toEqual([
      { id: "stick", erledigt: true },
      { id: "passwort", erledigt: false },
      { id: "erste", erledigt: false },
    ]);
    expect(naechsteAufgabe(aufgaben)).toBe("passwort");
    expect(hauptaktion(status(), einstellungen, aufgaben)).toBe("passwort");
  });

  it("noch nie ein Stick gesehen: einrichten, sonst erneut prüfen", () => {
    const ohne = status({
      usb: { present: false, writable: false, free_bytes: null, last_seen_at: null },
    });
    const aufgaben = einrichtungsAufgaben(ohne, einstellungen, []);
    expect(naechsteAufgabe(aufgaben)).toBe("stick");
    expect(hauptaktion(ohne, einstellungen, aufgaben)).toBe("stick_einrichten");
    const bekannt = status({
      usb: {
        present: false,
        writable: false,
        free_bytes: null,
        last_seen_at: "2026-11-21T10:00:00Z",
      },
    });
    expect(
      hauptaktion(bekannt, einstellungen, einrichtungsAufgaben(bekannt, einstellungen, [])),
    ).toBe("stick_pruefen");
  });

  it("Stick und Passwort da: jetzt sichern", () => {
    const fertig = status({ passphrase_set: true });
    const aufgaben = einrichtungsAufgaben(fertig, einstellungen, []);
    expect(naechsteAufgabe(aufgaben)).toBe("erste");
    expect(hauptaktion(fertig, einstellungen, aufgaben)).toBe("sichern");
  });

  it("nach der ersten Kopie auf den Stick keine Liste mehr", () => {
    expect(
      einrichtungsAufgaben(status({ passphrase_set: true }), einstellungen, [kopie]),
    ).toBeNull();
    expect(einrichtungsAufgaben(status({ last_usb_copy: kopie }), einstellungen, [])).toBeNull();
  });

  it("ohne Verschlüsselung keine Passwort-Aufgabe, ohne Stick-Kopie gar keine Liste", () => {
    const aufgaben = einrichtungsAufgaben(status(), { ...einstellungen, encrypt: false }, []);
    expect(aufgaben?.map((a) => a.id)).toEqual(["stick", "erste"]);
    expect(einrichtungsAufgaben(status(), { ...einstellungen, usb_enabled: false }, [])).toBeNull();
  });

  it("später fehlt der Stick: erneut prüfen statt jetzt sichern", () => {
    const weg = status({
      passphrase_set: true,
      last_usb_copy: kopie,
      usb: {
        present: false,
        writable: false,
        free_bytes: null,
        last_seen_at: "2026-11-22T00:00:00Z",
      },
    });
    expect(hauptaktion(weg, einstellungen, einrichtungsAufgaben(weg, einstellungen, []))).toBe(
      "stick_pruefen",
    );
  });
});
