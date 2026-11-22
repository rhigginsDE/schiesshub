import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { meldungenLeeren } from "../../components/Meldungen";
import { apiAttrappe, renderApp } from "../../test/app";

afterEach(() => meldungenLeeren());

// jsdom kennt scrollIntoView nicht; die Mantine-Auswahl ruft es auf.
Element.prototype.scrollIntoView = () => undefined;

/** Optionen genau der Auswahl, die zu diesem Eingabefeld gehört (die Liste liegt im Portal). */
function optionenVon(feld: HTMLElement) {
  const liste = document.getElementById(feld.getAttribute("aria-controls") ?? "");
  if (!liste) throw new Error("Auswahlliste nicht gefunden");
  return within(liste);
}

const HEALTH = { status: "ok", version: "0.1.0", db: "ok", katalog: null };

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

const rolle = (id: string, name: string, permissions: string[], is_system = false) => ({
  id,
  name,
  is_system,
  starter_key: null,
  customized: false,
  permissions,
  effective_permissions: permissions,
  user_count: 0,
});

const ROLLEN = [
  rolle("admin", "Administrator", ["*"], true),
  rolle("anzeige", "Anzeige", ["display.read"]),
  rolle("technik", "Technik", ["backup.*", "display.read"]),
];

const GERAET = {
  id: "g2",
  name: "Bildschirm Halle",
  paired_at: "2026-11-22T08:00:00Z",
  last_seen_at: null,
  default_role_id: null,
  blocked: false,
  is_current: false,
};

const FELDFEHLER = {
  detail: "Bitte die Eingaben prüfen.",
  errors: [
    {
      field: "default_role_id",
      message:
        "Die Rolle „Technik“ enthält Verwaltungsrechte und kann deshalb nicht ohne Anmeldung gelten.",
    },
  ],
};

const json = (inhalt: unknown, code = 200) =>
  new Response(JSON.stringify(inhalt), {
    status: code,
    headers: { "Content-Type": "application/json" },
  });

describe("Geräte: Standardrolle ohne Verwaltungsrechte (QA G-10)", () => {
  it("bietet Rollen mit Verwaltungsrechten beim Koppeln nicht an, mit Begründung", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status,
      "/devices": [GERAET],
      "/roles": ROLLEN,
    });
    const nutzer = userEvent.setup();
    renderApp("/system/geraete");

    await nutzer.click(await screen.findByRole("button", { name: "Neues Gerät hinzufügen" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/gelten nur nach dem Einloggen mit PIN/)).toBeInTheDocument();
    const feld = within(dialog).getByRole("combobox", { name: /Ohne Anmeldung nutzbar als/ });
    await nutzer.click(feld);
    await waitFor(() => expect(feld).toHaveAttribute("aria-controls"));
    const optionen = optionenVon(feld);
    const admin = await optionen.findByRole("option", { name: /Administrator/, hidden: true });
    expect(admin).toHaveTextContent("nur mit PIN: Verwaltungsrechte");
    expect(admin).toHaveAttribute("data-combobox-disabled", "true");
    expect(optionen.getByRole("option", { name: /^Technik/, hidden: true })).toHaveAttribute(
      "data-combobox-disabled",
      "true",
    );
    expect(optionen.getByRole("option", { name: "Anzeige", hidden: true })).not.toHaveAttribute(
      "data-combobox-disabled",
    );
  });

  it("zeigt den Feldfehler des Servers am Auswahlfeld des Geräts", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status,
      "/devices": [GERAET],
      "/roles": [...ROLLEN, rolle("alt", "Alte Technik", ["display.read"])],
      "/devices/g2": () => json(FELDFEHLER, 422),
    });
    const nutzer = userEvent.setup();
    renderApp("/system/geraete");

    const feld = await screen.findByRole("combobox", { name: /Ohne Anmeldung nutzbar als/ });
    await waitFor(() => expect(feld).toBeEnabled());
    await nutzer.click(feld);
    await nutzer.click(await screen.findByRole("option", { name: "Alte Technik", hidden: true }));
    expect(await screen.findByText(/enthält Verwaltungsrechte/)).toBeInTheDocument();
    // Nur am Feld, nicht zusätzlich als Meldung.
    expect(screen.getAllByText(/enthält Verwaltungsrechte/)).toHaveLength(1);
  });
});
