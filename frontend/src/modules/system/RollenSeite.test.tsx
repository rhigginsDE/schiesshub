import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { meldungenLeeren } from "../../components/Meldungen";
import { apiAttrappe, renderApp } from "../../test/app";

afterEach(() => meldungenLeeren());

const status = {
  setup_required: false,
  auth_enforced: true,
  device: { id: "g1", name: "Leitstand", default_role_id: null },
  device_revoked: false,
  user: { id: "p1", name: "Test-Admin" },
  role: { id: "admin", name: "Administrator" },
  permissions: ["*"],
  pin_min_length: 4,
  max_failed_logins: 5,
  lockout_minutes: 5,
};

const rolle = (
  id: string,
  name: string,
  permissions: string[],
  extra: { is_system?: boolean; starter_key?: string | null; customized?: boolean } = {},
) => ({
  id,
  name,
  is_system: false,
  starter_key: null,
  customized: true,
  permissions,
  effective_permissions: permissions,
  user_count: 2,
  ...extra,
});

const recht = (
  permission: string,
  module: string,
  module_title: string,
  requires: string[] = [],
) => ({
  permission,
  module,
  module_title,
  requires,
});

const BERECHTIGUNGEN = [
  recht("start.read", "starts", "Anmeldung und Starts", ["tournament.read"]),
  recht("start.call", "starts", "Anmeldung und Starts", ["start.read", "tournament.read"]),
  recht("tournament.read", "turnier", "Turnier"),
  recht("display.read", "anzeige", "Anzeige"),
];

const ROLLEN = [
  rolle("admin", "Administrator", ["*"], { is_system: true, starter_key: "Administrator" }),
  rolle("kasse", "Kasse", ["start.read", "tournament.read"], {
    starter_key: "Kasse",
    customized: false,
  }),
  rolle("eigen", "Helfer Halle", ["start.call"]),
];

describe("Rollen: Karten mit Klartext, Matrix unter „Erweitert“", () => {
  it("zeigt je Rolle einen Satz und klappt die Matrix erst auf Wunsch auf", async () => {
    apiAttrappe({
      "/auth/status": status,
      "/users": [],
      "/roles": ROLLEN,
      "/auth/permissions": BERECHTIGUNGEN,
    });
    const nutzer = userEvent.setup();
    renderApp("/system/personen");

    const karten = await screen.findByRole("list", { name: "Rollen" });
    expect(within(karten).getByText(/Darf alles, auch Benutzer/)).toBeInTheDocument();
    expect(within(karten).getByText(/Meldet Schützen an/)).toBeInTheDocument();
    // Eigene Rolle: Zusammenfassung aus den Rechten, mit Hinweis auf die fehlende Voraussetzung.
    expect(within(karten).getByText("Darf: Starts aufrufen.")).toBeInTheDocument();
    expect(within(karten).getByText(/fehlt eine Voraussetzung/)).toBeInTheDocument();
    expect(within(karten).getAllByText("2 Benutzer")).toHaveLength(3);

    // Die Matrix liegt zugeklappt hinter „Erweitert“.
    const kaestchen = screen.getByRole("checkbox", {
      name: "Helfer Halle: Starts aufrufen erlaubt",
      hidden: true,
    });
    expect(kaestchen).not.toBeVisible();
    await nutzer.click(screen.getByText("Erweitert: Rechte im Einzelnen"));
    expect(kaestchen).toBeVisible();
    expect(screen.getByRole("button", { name: "Rolle anlegen" })).toBeVisible();
  });

  it("heißt unter System „Benutzer“, nicht „Personen“", async () => {
    apiAttrappe({
      "/auth/status": status,
      "/users": [],
      "/roles": ROLLEN,
      "/auth/permissions": BERECHTIGUNGEN,
    });
    renderApp("/system/personen");
    expect(await screen.findByRole("heading", { name: "Benutzer" })).toBeInTheDocument();
    expect(await screen.findByText("Noch keine Benutzer")).toBeInTheDocument();
    expect(screen.getAllByText("Benutzer & Rollen").length).toBeGreaterThan(0);
  });
});
