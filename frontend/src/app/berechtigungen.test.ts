import { describe, expect, it } from "vitest";
import { abweisGrund, bestimmeLage, rechteAus } from "./anmeldeLage";
import { darfMit, passt, type Rechte } from "./berechtigungen";
import { sichtbareWarnung } from "./sicherungsLage";

const status = (teil: Record<string, unknown> = {}) => ({
  setup_required: false,
  auth_enforced: false,
  device: { id: "g1", name: "Kasse 1", default_role_id: null },
  device_revoked: false,
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

  it("eine Berechtigung, die die Rolle nicht hat, sperrt – auch eine unbekannte", () => {
    expect(darfMit(rechte, "anmeldung.nutzen")).toBe(false);
    expect(darfMit({ offen: false, erlaubt: ["entry.edit"] }, ["entry.read", "entry.edit"])).toBe(
      true,
    );
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

describe("abweisGrund", () => {
  const ohneGeraet = status({ auth_enforced: true, device: null, user: null, role: null });

  it("gesperrtes Gerät aus dem Status oder aus dem Code der 401", () => {
    expect(abweisGrund({ ...ohneGeraet, device_revoked: true }, null)).toBe("gesperrt");
    expect(abweisGrund(ohneGeraet, "device_revoked")).toBe("gesperrt");
    expect(abweisGrund(ohneGeraet, "device_unknown")).toBeNull();
  });

  it("abgelaufene Anmeldung", () => {
    const ohnePerson = status({ auth_enforced: true, user: null, role: null });
    expect(abweisGrund(ohnePerson, "session_expired")).toBe("abgelaufen");
    expect(abweisGrund(status(), "session_expired")).toBeNull();
  });
});

describe("sichtbareWarnung", () => {
  const warnung = {
    code: "usb_missing" as const,
    message_de: "Der Sicherungs-Stick fehlt.",
    since: "2026-11-21T10:38:00Z",
  };
  const lage = { warning: warnung, warn_all_stations: true, warn_on_display: false };

  it("zeigt die Warnung auf allen Stationen", () => {
    expect(
      sichtbareWarnung({
        lage,
        istAnzeige: false,
        stumm: null,
        jetzt: 0,
      }),
    ).toBe(warnung);
  });

  it("die Anzeige hat eine eigene Einstellung", () => {
    expect(
      sichtbareWarnung({
        lage,
        istAnzeige: true,
        stumm: null,
        jetzt: 0,
      }),
    ).toBeNull();
  });

  it("ohne Warnung oder mit ausgeschalteter Einstellung kein Banner", () => {
    const eingaben = { istAnzeige: false, stumm: null, jetzt: 0 };
    expect(sichtbareWarnung({ ...eingaben, lage: undefined })).toBeNull();
    expect(sichtbareWarnung({ ...eingaben, lage: { ...lage, warning: null } })).toBeNull();
    expect(
      sichtbareWarnung({ ...eingaben, lage: { ...lage, warn_all_stations: false } }),
    ).toBeNull();
  });

  it("ausgeblendet bis zum Ablauf, eine andere Warnung erscheint sofort", () => {
    const stumm = { bis: 1000, code: "usb_missing" };
    const eingaben = { lage, istAnzeige: false, stumm };
    expect(sichtbareWarnung({ ...eingaben, jetzt: 999 })).toBeNull();
    expect(sichtbareWarnung({ ...eingaben, jetzt: 1001 })).toBe(warnung);
    expect(
      sichtbareWarnung({ ...eingaben, stumm: { bis: 1000, code: "usb_full" }, jetzt: 999 }),
    ).toBe(warnung);
  });
});
