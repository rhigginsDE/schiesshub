import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { meldungenLeeren } from "../../components/Meldungen";
import { apiAttrappe, renderApp } from "../../test/app";
import { pruefungsAufgaben, unbekannteHindernisse } from "./pruefungsLage";

afterEach(() => meldungenLeeren());

const HEALTH = { status: "ok", version: "0.1.0", db: "ok", katalog: null };

const status = {
  setup_required: false,
  auth_enforced: false,
  device: { id: "g1", name: "Laptop Turnierleitung", default_role_id: null },
  device_revoked: false,
  user: { id: "p1", name: "Test-Admin" },
  role: { id: "admin", name: "Administrator" },
  permissions: ["*"],
  pin_min_length: 4,
  max_failed_logins: 5,
  lockout_minutes: 5,
};

const blocker = (code: string) => ({ code, message_de: `Text des Servers zu ${code}` });

const AUS_BEREIT = { enforced: false, source: null, can_enable: true, blockers: [] };
const AN_APP = { enforced: true, source: "setting", can_enable: false, blockers: [] };

const json = (inhalt: unknown, code = 200) =>
  new Response(JSON.stringify(inhalt), {
    status: code,
    headers: { "Content-Type": "application/json" },
  });

const aufrufeVon = (attrappe: ReturnType<typeof apiAttrappe>, pfad: string) =>
  attrappe.mock.calls.filter(([url]) => String(url).endsWith(pfad));

describe("Koppeln und PIN verlangen: Voraussetzungen", () => {
  it("ordnet die Hindernisse des Servers den Schritten zu", () => {
    expect(pruefungsAufgaben([blocker("device_not_paired"), blocker("not_logged_in")])).toEqual([
      { id: "admin", erledigt: true },
      { id: "geraet", erledigt: false, code: "device_not_paired" },
      { id: "eingeloggt", erledigt: false, code: "not_logged_in" },
    ]);
    expect(pruefungsAufgaben([blocker("not_admin")])[2]).toEqual({
      id: "eingeloggt",
      erledigt: false,
      code: "not_admin",
    });
    expect(pruefungsAufgaben([]).every((aufgabe) => aufgabe.erledigt)).toBe(true);
  });

  it("reicht unbekannte Hindernisse mit dem Text des Servers durch", () => {
    expect(unbekannteHindernisse([blocker("not_admin"), blocker("neu")])).toEqual([blocker("neu")]);
  });
});

describe("System → Server: Koppeln und PIN verlangen", () => {
  it("zeigt offene Schritte mit Weg zur Lösung und bietet Einschalten noch nicht an", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": { ...status, device: null, user: null, role: null },
      "/auth/enforcement": {
        enforced: false,
        source: null,
        can_enable: false,
        blockers: [blocker("no_admin_with_pin"), blocker("device_not_paired")],
      },
    });
    renderApp("/system/server");

    const abschnitt = await screen.findByRole("region", {
      name: "Geräte koppeln und PIN verlangen",
    });
    expect(await within(abschnitt).findByText("Vorher erledigen")).toBeInTheDocument();
    expect(within(abschnitt).getByText("1 von 3 erledigt")).toBeInTheDocument();
    expect(
      within(abschnitt).getByText(/Es gibt noch keinen Administrator mit PIN/),
    ).toBeInTheDocument();
    expect(within(abschnitt).getByRole("link", { name: "Zu Benutzer & Rollen" })).toHaveAttribute(
      "href",
      "/system/personen",
    );
    expect(within(abschnitt).getByRole("link", { name: "Zu Geräte" })).toHaveAttribute(
      "href",
      "/system/geraete",
    );
    expect(within(abschnitt).queryByRole("button", { name: "Einschalten" })).toBeNull();
  });

  it("fragt vor dem Einschalten nach und sagt, dass Ausschalten nur auf dem Server geht", async () => {
    let an = false;
    const attrappe = apiAttrappe({
      "/health": HEALTH,
      "/auth/status": () => json({ ...status, auth_enforced: an }),
      "/auth/enforcement": () => json(an ? AN_APP : AUS_BEREIT),
      "/auth/enforcement/enable": () => {
        an = true;
        return json(AN_APP);
      },
    });
    const nutzer = userEvent.setup();
    renderApp("/system/server");

    await nutzer.click(await screen.findByRole("button", { name: "Einschalten" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/nur noch direkt auf dem Server/)).toBeInTheDocument();
    expect(
      within(dialog).getByText(/„Laptop Turnierleitung“\) bleibt gekoppelt.*als Test-Admin/),
    ).toBeInTheDocument();
    expect(aufrufeVon(attrappe, "/auth/enforcement/enable")).toHaveLength(0);

    const statusVorher = aufrufeVon(attrappe, "/auth/status").length;
    await nutzer.click(within(dialog).getByRole("button", { name: "Einschalten" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const aufruf = aufrufeVon(attrappe, "/auth/enforcement/enable")[0] as unknown[] | undefined;
    expect((aufruf?.[1] as RequestInit | undefined)?.method).toBe("POST");
    await waitFor(() =>
      expect(aufrufeVon(attrappe, "/auth/status").length).toBeGreaterThan(statusVorher),
    );
    const abschnitt = screen.getByRole("region", { name: "Geräte koppeln und PIN verlangen" });
    expect(await within(abschnitt).findByText(/nur direkt auf dem Server/)).toBeInTheDocument();
    expect(within(abschnitt).queryByRole("button", { name: "Einschalten" })).toBeNull();
  });

  it("zeigt im Dialog, warum der Server das Einschalten ablehnt", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status,
      "/auth/enforcement": AUS_BEREIT,
      "/auth/enforcement/enable": () =>
        json(
          {
            detail: "Die Berechtigungsprüfung kann noch nicht eingeschaltet werden.",
            code: "enforcement_blocked",
          },
          409,
        ),
    });
    const nutzer = userEvent.setup();
    renderApp("/system/server");

    await nutzer.click(await screen.findByRole("button", { name: "Einschalten" }));
    const dialog = await screen.findByRole("dialog");
    await nutzer.click(within(dialog).getByRole("button", { name: "Einschalten" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "kann noch nicht eingeschaltet werden",
    );
  });

  it("zeigt eingeschaltet nur den Zustand, ohne Knopf zum Ausschalten", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": { ...status, auth_enforced: true },
      "/auth/enforcement": { ...AN_APP, source: "env" },
    });
    renderApp("/system/server");

    const abschnitt = await screen.findByRole("region", {
      name: "Geräte koppeln und PIN verlangen",
    });
    expect(await within(abschnitt).findByText("Eingeschaltet")).toBeInTheDocument();
    expect(within(abschnitt).getByText(/auf dem Server fest eingestellt/)).toBeInTheDocument();
    expect(within(abschnitt).queryByRole("button")).toBeNull();
  });
});
