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
    device_revoked: false,
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
  it("im offenen Betrieb ohne Kopplung: kein Personenabruf, klare Seite mit Ausweg", async () => {
    const attrappe = apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status({ device: null }),
    });
    renderApp("/anmelden");
    expect(
      await screen.findByRole("heading", { name: "Erst dieses Gerät koppeln" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Wer bist du?" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Gerät koppeln" })).toHaveAttribute("href", "/pair");
    expect(screen.getByRole("link", { name: "Zur Startseite" })).toHaveAttribute("href", "/");
    const pfade = attrappe.mock.calls.map(([eingabe]) => String(eingabe));
    expect(pfade.some((pfad) => pfad.includes("/auth/users"))).toBe(false);
  });

  it("Koppeln im offenen Betrieb bietet den Weg zur Startseite", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status({ device: null }),
    });
    renderApp("/pair");
    expect(await screen.findByRole("heading", { name: "Gerät koppeln" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zur Startseite" })).toBeInTheDocument();
  });

  it("ohne Durchsetzung bleibt die App benutzbar und zeigt den Hinweis zur Ersteinrichtung", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status({ setup_required: true, device: null }),
      "/tournaments": [],
    });
    renderApp("/");
    expect(
      await screen.findByRole("heading", { name: "So läuft dein Turnier" }),
    ).toBeInTheDocument();
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
    await nutzer.click(screen.getByRole("button", { name: "Einloggen" }));
    expect(await screen.findByText("PIN stimmt nicht. Bitte erneut eingeben.")).toBeInTheDocument();

    for (const ziffer of ["9", "9", "9", "9"]) {
      await nutzer.click(screen.getByRole("button", { name: ziffer }));
    }
    await nutzer.click(screen.getByRole("button", { name: "Einloggen" }));
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
    const knopf = await screen.findByRole("button", { name: /Eingeloggt: H\. Berger/ });
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
      "/backup/warning": {
        warning: {
          code: "usb_missing",
          message_de: "Der Sicherungs-Stick fehlt.",
          since: "2026-11-21T10:38:00Z",
        },
        warn_all_stations: true,
        warn_on_display: false,
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
      "/tournaments": [],
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

  it("Stick fehlt: sagt, was zu tun ist, und bietet „Erneut prüfen“", async () => {
    apiAttrappe(sicherungsAttrappe("usb_missing", "Der Sicherungs-Stick fehlt."));
    renderApp("/");
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Steck den Sicherungs-Stick in den Server");
    expect(within(banner).getByRole("button", { name: "Erneut prüfen" })).toBeInTheDocument();
    expect(within(banner).queryByRole("link", { name: "Passwort festlegen" })).toBeNull();
  });

  it("Passwort fehlt: Link „Passwort festlegen“, kein „Erneut prüfen“", async () => {
    apiAttrappe(sicherungsAttrappe("passphrase_missing", "Das Sicherungspasswort fehlt."));
    renderApp("/");
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Leg ein Sicherungspasswort fest.");
    expect(within(banner).getByRole("link", { name: "Passwort festlegen" })).toHaveAttribute(
      "href",
      "/system/sicherung",
    );
    expect(within(banner).queryByRole("button", { name: "Erneut prüfen" })).toBeNull();
  });

  it("ohne Verwaltungsrecht: Bescheid geben statt Link", async () => {
    apiAttrappe({
      ...sicherungsAttrappe("passphrase_missing", "Das Sicherungspasswort fehlt."),
      "/auth/status": status({
        user: { id: "p1", name: "H. Berger" },
        role: { id: "r2", name: "Kasse" },
        permissions: ["backup.read"],
      }),
    });
    renderApp("/");
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Sag der Turnierleitung Bescheid.");
    expect(within(banner).queryByRole("link", { name: "Passwort festlegen" })).toBeNull();
  });

  it("QA G-6: ohne „Sicherung ansehen“ erscheint die Warnung trotzdem, ohne Kopfzeilen-Chip", async () => {
    const verboten = () => json({ detail: "Dafür fehlt die Berechtigung „backup.read“." }, 403);
    let warnung: unknown = {
      code: "usb_missing",
      message_de: "Der Sicherungs-Stick fehlt.",
      since: "2026-11-21T10:38:00Z",
    };
    const attrappe = apiAttrappe({
      "/health": HEALTH,
      "/tournaments": [],
      "/auth/status": status({
        auth_enforced: true,
        user: { id: "p1", name: "L. Behrens" },
        role: { id: "r3", name: "Auswertung" },
        permissions: ["result.read", "result.edit"],
      }),
      "/backup/warning": () =>
        json({ warning: warnung, warn_all_stations: true, warn_on_display: false }),
      "/backup/status": verboten,
      "/backup/settings": verboten,
    });
    const nutzer = userEvent.setup();
    renderApp("/");
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Der Sicherungs-Stick fehlt.");
    expect(banner).toHaveTextContent("Steck den Sicherungs-Stick in den Server");
    expect(screen.queryByText("Kein Sicherungs-Stick")).not.toBeInTheDocument();
    const pfade = attrappe.mock.calls.map(([eingabe]) => String(eingabe));
    expect(pfade.some((pfad) => pfad.includes("/backup/status"))).toBe(false);

    // Stick wieder da: „Erneut prüfen“ fragt die Warnung neu ab, das Banner verschwindet.
    warnung = null;
    await nutzer.click(within(banner).getByRole("button", { name: "Erneut prüfen" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("ein Server ohne Warnung zeigt kein Banner", async () => {
    apiAttrappe({
      ...sicherungsAttrappe("usb_missing", "Der Sicherungs-Stick fehlt."),
      "/backup/warning": { warning: null, warn_all_stations: true, warn_on_display: false },
    });
    renderApp("/");
    expect(await screen.findByText("Kein Sicherungs-Stick")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("Abgewiesene Geräte (QA KLEIN 3)", () => {
  it("ein gesperrtes Gerät liest auf der Kopplungsseite, was los ist", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": status({ auth_enforced: true, device: null, device_revoked: true }),
    });
    renderApp("/");
    expect(
      await screen.findByRole("heading", { name: "Dieses Gerät wurde gesperrt" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Ein Benutzer mit Verwaltungsrecht kann es unter System → Geräte wieder freigeben oder neu koppeln.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Kopplungscode")).toBeInTheDocument();
  });

  it("abgelaufene Sitzung: kurzer Hinweis auf der Anmeldeseite", async () => {
    // Erst angemeldet; die nächste Anfrage kommt mit 401 `session_expired` zurück, danach meldet
    // der Status niemanden mehr.
    let abfragen = 0;
    const abgelaufen = () =>
      json({ detail: "Die Sitzung ist abgelaufen.", code: "session_expired" }, 401);
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": () => {
        abfragen += 1;
        return json(
          abfragen === 1
            ? status({
                auth_enforced: true,
                user: { id: "p1", name: "H. Berger" },
                role: { id: "r2", name: "Turnierleitung" },
                permissions: ["backup.read"],
              })
            : status({ auth_enforced: true }),
        );
      },
      "/auth/users": [{ id: "p1", name: "H. Berger" }],
      "/backup/warning": { warning: null, warn_all_stations: true, warn_on_display: false },
      "/backup/status": abgelaufen,
      "/backup/settings": abgelaufen,
      "/backup/runs?limit=50": abgelaufen,
    });
    renderApp("/system/sicherung");
    expect(await screen.findByRole("heading", { name: "Wer bist du?" })).toBeInTheDocument();
    expect(
      await screen.findByText("Die Sitzung ist abgelaufen, bitte neu anmelden."),
    ).toBeInTheDocument();
  });
});

function sicherungsAttrappe(code: string, text: string) {
  return {
    "/health": HEALTH,
    "/auth/status": status(),
    "/tournaments": [],
    "/backup/status": {
      usb: {
        present: code !== "usb_missing",
        writable: true,
        free_bytes: null,
        last_seen_at: null,
      },
      last_snapshot: null,
      last_usb_copy: null,
      journal: { pending: 0 },
      warning: { code, message_de: text, since: "2026-11-21T10:38:00Z" },
      passphrase_set: code !== "passphrase_missing",
    },
    "/backup/warning": {
      warning: { code, message_de: text, since: "2026-11-21T10:38:00Z" },
      warn_all_stations: true,
      warn_on_display: false,
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
  };
}
