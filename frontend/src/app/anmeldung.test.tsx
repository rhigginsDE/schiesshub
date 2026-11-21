import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { meldungenLeeren } from "../components/Meldungen";
import { apiAttrappe, renderApp } from "../test/app";

afterEach(() => meldungenLeeren());

const HEALTH = { status: "ok", version: "0.1.0", db: "ok", katalog: null };

function status(teil: Record<string, unknown> = {}) {
  return {
    setup_required: false,
    auth_enforced: false,
    device: { id: "g1", name: "Kasse 1", default_role_id: null },
    user: null,
    role: null,
    permissions: [],
    ...teil,
  };
}

const json = (inhalt: unknown, status = 200, kopf: Record<string, string> = {}) =>
  new Response(JSON.stringify(inhalt), {
    status,
    headers: { "Content-Type": "application/json", ...kopf },
  });

describe("Anmelde-Zustand", () => {
  it("ohne Durchsetzung bleibt die App benutzbar und zeigt den Hinweis zur Ersteinrichtung", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status({ setup_required: true, device: null }),
    });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Station wählen" })).toBeInTheDocument();
    expect(await screen.findByText("Ersteinrichtung ausstehend")).toBeInTheDocument();
  });

  it("mit Durchsetzung und ohne Kopplung erscheint „Gerät koppeln“, der Code kommt aus der Adresse", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status({ auth_enforced: true, device: null }),
    });
    renderApp("/pair?code=abcdefghjk");
    expect(await screen.findByRole("heading", { name: "Gerät koppeln" })).toBeInTheDocument();
    expect(screen.getByLabelText("Kopplungscode")).toHaveValue("ABCDE-FGHJK");
    expect(screen.queryByRole("navigation", { name: "Stationen" })).not.toBeInTheDocument();
  });

  it("Anmeldung: falsche PIN, dann Sperre mit Restzeit", async () => {
    let versuche = 0;
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status({ auth_enforced: true }),
      "/auth/users": [{ id: "p1", name: "H. Berger" }],
      "/auth/login": () => {
        versuche += 1;
        return versuche === 1
          ? json({ detail: "Die Anmeldung ist fehlgeschlagen." }, 401)
          : json({ detail: "Zu viele Fehlversuche." }, 429, { "Retry-After": "272" });
      },
    });
    const nutzer = userEvent.setup();
    renderApp("/turnier");

    await nutzer.click(await screen.findByRole("button", { name: /H\. Berger/ }));
    for (const ziffer of ["1", "2", "3", "4"]) {
      await nutzer.click(screen.getByRole("button", { name: ziffer }));
    }
    await nutzer.click(screen.getByRole("button", { name: "Anmelden" }));
    expect(await screen.findByText("PIN stimmt nicht. Bitte erneut eingeben.")).toBeInTheDocument();

    for (const ziffer of ["9", "9", "9", "9"]) {
      await nutzer.click(screen.getByRole("button", { name: ziffer }));
    }
    await nutzer.click(screen.getByRole("button", { name: "Anmelden" }));
    expect(await screen.findByText(/noch 4:3\d Min\. gesperrt/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "5" })).toBeDisabled();
  });

  it("eine 401 von einem Endpunkt führt zurück zur Anmeldung", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status(),
      "/auth/users": [{ id: "p1", name: "H. Berger" }],
      "/backup/status": () => json({ detail: "Bitte zuerst mit der PIN anmelden." }, 401),
      "/backup/settings": () => json({ detail: "Bitte zuerst mit der PIN anmelden." }, 401),
      "/backup/runs?limit=50": () => json({ detail: "Bitte zuerst mit der PIN anmelden." }, 401),
    });
    renderApp("/system/sicherung");
    expect(await screen.findByRole("heading", { name: "Wer bist du?" })).toBeInTheDocument();
  });

  it("eine 403 zeigt „Dafür fehlt die Berechtigung“", async () => {
    const verboten = () => json({ detail: "Dafür fehlt die Berechtigung „device.manage“." }, 403);
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status(),
      "/devices": verboten,
      "/roles": verboten,
    });
    renderApp("/system/geraete");
    expect(await screen.findByText("Dafür fehlt die Berechtigung")).toBeInTheDocument();
    expect(
      (await screen.findAllByText("Dafür fehlt die Berechtigung „device.manage“.")).length,
    ).toBeGreaterThan(0);
  });

  it("angemeldet: Name und Rolle in der Kopfzeile, Navigation nach Rechten", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status({
        auth_enforced: true,
        user: { id: "p1", name: "H. Berger" },
        role: { id: "r2", name: "Kasse" },
        permissions: ["person.read"],
      }),
    });
    renderApp("/");
    const knopf = await screen.findByRole("button", { name: /Angemeldet: H\. Berger/ });
    expect(knopf).toHaveTextContent("H. Berger · Kasse");
    const navigation = screen.getByRole("navigation", { name: "Stationen" });
    expect(within(navigation).queryByText("System")).not.toBeInTheDocument();
  });
});

describe("Sicherungswarnung", () => {
  it("Banner auf jeder Station, ausblendbar für 15 Minuten", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status(),
      "/backup/status": {
        usb: { present: false, writable: false, free_bytes: null, last_seen_at: null },
        last_snapshot: null,
        last_usb_copy: null,
        journal: { pending: 0 },
        warning: {
          code: "usb_missing",
          message_de: "Der Sicherungs-Stick fehlt.",
          since: "2026-11-21T10:38:00Z",
        },
        passphrase_set: true,
      },
      "/backup/settings": {
        enabled: true,
        usb_enabled: true,
        snapshot_interval_minutes: 5,
        keep_local: 20,
        keep_usb: 20,
        warn_all_stations: true,
        warn_on_display: false,
        encrypt: true,
      },
    });
    const nutzer = userEvent.setup();
    renderApp("/");
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Der Sicherungs-Stick fehlt.");
    expect(screen.getByText("Kein Sicherungs-Stick")).toBeInTheDocument();

    await nutzer.click(within(banner).getByRole("button", { name: "Für 15 Min. ausblenden" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(window.localStorage.getItem("schiesshub.sicherung.stumm")).toContain("usb_missing");
  });
});
