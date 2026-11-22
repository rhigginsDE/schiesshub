import { describe, expect, it } from "vitest";
import { bestimmeLage, rechteAus } from "./anmeldeLage";
import { darfMit, passt, type Rechte } from "./berechtigungen";
import { sichtbareWarnung } from "./sicherungsLage";

const status = (teil: Record<string, unknown> = {}) => ({
  setup_required: false,
  auth_enforced: false,
  device: { id: "g1", name: "Kasse 1", default_role_id: null },
  user: { id: "p1", name: "H. Berger" },
  role: { id: "r1", name: "Kasse" },
  permissions: ["person.read", "entry.edit"],
  pin_min_length: 4,
  max_failed_logins: 5,
  lockout_minutes: 5,
  ...teil,
});

describe("passt", () => {
  it("wertet Stern und Präfix aus", () => {
    expect(passt("*", "tournament.edit")).toBe(true);
    expect(passt("person.*", "person.edit")).toBe(true);
    expect(passt("person.*", "personal.edit")).toBe(false);
    expect(passt("club.edit", "club.edit")).toBe(true);
    expect(passt("club.edit", "club.read")).toBe(false);
  });
});

describe("darfMit", () => {
  const rechte: Rechte = {
    offen: false,
    erlaubt: ["person.*", "backup.read"],
    bekannt: new Set(["person.read", "backup.read", "backup.manage", "system.manage"]),
  };

  it("erlaubt alles im offenen Betrieb", () => {
    expect(darfMit({ offen: true }, "system.manage")).toBe(true);
  });

  it("prüft Namen, Muster und Listen", () => {
    expect(darfMit(rechte, "person.read")).toBe(true);
    expect(darfMit(rechte, "backup.manage")).toBe(false);
    expect(darfMit(rechte, ["system.manage", "backup.read"])).toBe(true);
    expect(darfMit(rechte, null)).toBe(true);
  });

  it("lässt Platzhalter durch, die der Server nicht kennt", () => {
    expect(darfMit(rechte, "anmeldung.nutzen")).toBe(true);
    expect(darfMit({ offen: false, erlaubt: [] }, "anmeldung.nutzen")).toBe(false);
  });
});

describe("bestimmeLage", () => {
  it("sperrt nicht, solange der Server nicht durchsetzt", () => {
    const lage = bestimmeLage({
      status: status({
        setup_required: true,
        device: null,
        user: null,
        role: null,
        permissions: [],
      }),
      statusFehler: false,
      abgewiesen: false,
    });
    expect(lage).toMatchObject({ ausstehend: "einrichtung", pflicht: null, sperren: false });
  });

  it("verlangt Kopplung und Anmeldung bei Durchsetzung", () => {
    const ohneGeraet = status({ auth_enforced: true, device: null, user: null, role: null });
    expect(
      bestimmeLage({ status: ohneGeraet, statusFehler: false, abgewiesen: false }).pflicht,
    ).toBe("koppeln");
    const ohneRolle = status({ auth_enforced: true, user: null, role: null });
    expect(
      bestimmeLage({ status: ohneRolle, statusFehler: false, abgewiesen: false }).pflicht,
    ).toBe("anmelden");
  });

  it("eine 401 reicht als Schalter", () => {
    const ohneRolle = status({ user: null, role: null });
    expect(bestimmeLage({ status: ohneRolle, statusFehler: false, abgewiesen: true }).pflicht).toBe(
      "anmelden",
    );
  });

  it("Gerät mit Standardrolle kommt ohne Person hinein", () => {
    const anzeige = status({
      auth_enforced: true,
      user: null,
      role: { id: "r5", name: "Anzeige" },
    });
    expect(
      bestimmeLage({ status: anzeige, statusFehler: false, abgewiesen: false }).pflicht,
    ).toBeNull();
  });

  it("älterer Server ohne Status: App bleibt benutzbar", () => {
    const lage = bestimmeLage({ status: undefined, statusFehler: true, abgewiesen: false });
    expect(lage).toMatchObject({ pruefe: false, pflicht: null });
    expect(rechteAus(undefined, lage)).toEqual({ offen: true });
  });
});

describe("rechteAus", () => {
  it("nutzt die Berechtigungen der Rolle", () => {
    const s = status();
    const lage = bestimmeLage({ status: s, statusFehler: false, abgewiesen: false });
    expect(rechteAus(s, lage)).toMatchObject({
      offen: false,
      erlaubt: ["person.read", "entry.edit"],
    });
  });

  it("ohne Rolle und ohne Sperre ist alles offen", () => {
    const s = status({ user: null, role: null, permissions: [] });
    const lage = bestimmeLage({ status: s, statusFehler: false, abgewiesen: false });
    expect(rechteAus(s, lage)).toEqual({ offen: true });
  });
});

describe("sichtbareWarnung", () => {
  const warnung = {
    code: "usb_missing" as const,
    message_de: "Der Sicherungs-Stick fehlt.",
    since: "2026-11-21T10:38:00Z",
  };
  const sicherung = { warning: warnung } as never;
  const einstellungen = { warn_all_stations: true, warn_on_display: false } as never;

  it("zeigt die Warnung auf allen Stationen", () => {
    expect(
      sichtbareWarnung({
        status: sicherung,
        einstellungen,
        istAnzeige: false,
        stumm: null,
        jetzt: 0,
      }),
    ).toBe(warnung);
  });

  it("die Anzeige hat eine eigene Einstellung", () => {
    expect(
      sichtbareWarnung({
        status: sicherung,
        einstellungen,
        istAnzeige: true,
        stumm: null,
        jetzt: 0,
      }),
    ).toBeNull();
  });

  it("ausgeblendet bis zum Ablauf, eine andere Warnung erscheint sofort", () => {
    const stumm = { bis: 1000, code: "usb_missing" };
    const eingaben = { status: sicherung, einstellungen, istAnzeige: false, stumm };
    expect(sichtbareWarnung({ ...eingaben, jetzt: 999 })).toBeNull();
    expect(sichtbareWarnung({ ...eingaben, jetzt: 1001 })).toBe(warnung);
    expect(
      sichtbareWarnung({ ...eingaben, stumm: { bis: 1000, code: "usb_full" }, jetzt: 999 }),
    ).toBe(warnung);
  });
});
