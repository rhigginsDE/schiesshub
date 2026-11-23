import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { meldungenLeeren } from "../../components/Meldungen";
import { apiAttrappe, renderApp } from "../../test/app";
import type { WiederherstellungsStatus } from "./wiederherstellenAblauf";
import { lauf, QUELLE_SERVER, QUELLE_STICK, vorschau } from "./wiederherstellenTestdaten";

afterEach(() => meldungenLeeren());

const HEALTH = { status: "ok", version: "0.1.0", db: "ok", katalog: null };
const KEINE_WARTUNG = { active: false, exclusive: false, message_de: null, since: null };

const anmeldung = (permissions: string[], rolle = "Administrator") => ({
  setup_required: false,
  auth_enforced: true,
  device: { id: "g1", name: "Leitstand", default_role_id: null },
  device_revoked: false,
  user: { id: "p1", name: "Test-Admin" },
  role: { id: "r1", name: rolle },
  permissions,
  pin_min_length: 4,
  max_failed_logins: 5,
  lockout_minutes: 5,
});

const json = (inhalt: unknown, code = 200, kopf: Record<string, string> = {}) =>
  new Response(JSON.stringify(inhalt), {
    status: code,
    headers: { "Content-Type": "application/json", ...kopf },
  });

const WARTUNG_503 = () =>
  json({ detail: "Die Datenbank wird gerade getauscht.", code: "maintenance" }, 503, {
    "Retry-After": "10",
  });

/** Inhalt der Anfrage an einen Pfad (letzter Aufruf). */
function gesendet(attrappe: ReturnType<typeof apiAttrappe>, pfad: string): unknown {
  // `fetch` bekommt die Optionen als zweites Argument; die Attrappe nennt nur das erste.
  const aufrufe = attrappe.mock.calls as unknown as [RequestInfo | URL, RequestInit?][];
  const aufruf = aufrufe.filter(([adresse]) => String(adresse).endsWith(pfad)).at(-1);
  const init = aufruf?.[1];
  return init?.body ? JSON.parse(String(init.body)) : undefined;
}

function fertig(): WiederherstellungsStatus {
  return lauf({
    state: "succeeded",
    step: "finish",
    progress: 1,
    maintenance: false,
    finished_at: "2026-11-23T21:12:00Z",
    steps: lauf().steps.map((schritt) => ({ ...schritt, state: "done" })),
    result: {
      database: "schiesshub_restore_1",
      previous_database: "schiesshub_pre_restore_1",
      pre_restore_backup: "pre-restore-20261123T211000Z.dump",
      schema_upgraded: false,
      journal: {
        applied: 7,
        present: 0,
        missing_events: 2,
        conflicts: 0,
        status_changes: 0,
        recomputed_competitions: 1,
        lines: ["7 Ereignisse nachgetragen, 2 übersprungen: Startnummer 31, 32"],
      },
      keys_installed: [],
      keys_set_aside: [],
      after_backup_ok: true,
      notes: [],
    },
  });
}

describe("Sicherung wiederherstellen (geführt)", () => {
  it("führt von der Auswahl über Passwort, Vorschau und Bestätigung bis zum Ergebnis", {
    timeout: 20000,
  }, async () => {
    // Fortschritt: erst nichts, nach dem Start läuft es, beim Tausch kurz 503, dann fertig.
    let gestartet = false;
    let abfragen = 0;
    const status = () => {
      if (!gestartet) return json(lauf({ state: "idle", step: null, source: null }));
      abfragen += 1;
      if (abfragen === 1) return json(lauf({ step: "swap" }));
      if (abfragen === 2) return WARTUNG_503();
      return json(fertig());
    };
    const attrappe = apiAttrappe({
      "/health": HEALTH,
      "/auth/status": anmeldung(["*"]),
      "/backup/maintenance": KEINE_WARTUNG,
      "/backup/restore/status": status,
      "/backup/restore/sources": {
        usb_present: true,
        restore_running: false,
        sources: [QUELLE_STICK, QUELLE_SERVER],
      },
      "/backup/restore/preview": () =>
        json(vorschau({ access: { ...vorschau().access, lockout_risk: true } })),
      "/backup/restore/execute": () => {
        gestartet = true;
        return json(lauf({ step: "check" }), 202);
      },
    });
    const nutzer = userEvent.setup();
    renderApp("/system/sicherung/wiederherstellen");

    // a) Sicherung wählen
    expect(
      await screen.findByRole("heading", { name: "Welche Sicherung soll zurückkommen?" }),
    ).toBeInTheDocument();
    await nutzer.click(await screen.findByRole("button", { name: "Weiter mit dieser Sicherung" }));
    expect(await screen.findByText("Bitte wähle eine Sicherung.")).toBeInTheDocument();
    const [stick] = screen.getAllByRole("radio");
    expect(stick).toHaveTextContent(/Stick/);
    expect(stick).toHaveTextContent(/Passwort nötig/);
    await nutzer.click(stick as HTMLElement);
    await nutzer.click(screen.getByRole("button", { name: "Weiter mit dieser Sicherung" }));

    // b) Passwort
    expect(
      await screen.findByRole("heading", { name: "Passwort der Sicherung eingeben" }),
    ).toBeInTheDocument();
    await nutzer.click(screen.getByRole("button", { name: "Sicherung prüfen" }));
    expect(screen.getByText("Bitte das Sicherungspasswort eingeben.")).toBeInTheDocument();
    await nutzer.type(screen.getByLabelText("Sicherungspasswort"), "Rote Scheibe 1972");
    await nutzer.click(screen.getByRole("button", { name: "Sicherung prüfen" }));

    // c) Vorschau
    expect(await screen.findByRole("heading", { name: "Das kommt zurück" })).toBeInTheDocument();
    expect(gesendet(attrappe, "/backup/restore/preview")).toEqual({
      source_id: QUELLE_STICK.id,
      passphrase: "Rote Scheibe 1972",
    });
    expect(screen.getByText("Vereinsmeisterschaft")).toBeInTheDocument();
    expect(screen.getByText(/2 Eingaben gehen verloren/)).toBeInTheDocument();
    expect(screen.getByText(/Davon trägt Schiesshub 7 automatisch nach/)).toBeInTheDocument();
    expect(screen.getByText(/Vorher sichert Schiesshub automatisch/)).toBeInTheDocument();
    expect(
      screen.getByText(/Sind Koppeln und PIN jetzt Pflicht, bleibt das so/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Danach kommst du an diesem Gerät nicht mehr in die Verwaltung"),
    ).toBeInTheDocument();
    await nutzer.click(screen.getByRole("button", { name: "Weiter zur Bestätigung" }));
    expect(screen.getByText("Bitte bestätige, dass du das verstanden hast.")).toBeInTheDocument();
    await nutzer.click(screen.getByRole("checkbox", { name: /nicht mehr als Administrator/ }));
    await nutzer.click(screen.getByRole("button", { name: "Weiter zur Bestätigung" }));

    // d) Bestätigen: gefährliche Aktion, nicht grün
    expect(
      await screen.findByRole("heading", { name: "Jetzt wiederherstellen?" }),
    ).toBeInTheDocument();
    const los = screen.getByRole("button", { name: "Sicherung jetzt wiederherstellen" });
    await nutzer.click(los);
    expect(
      screen.getByText("Bitte bestätige, dass der jetzige Stand ersetzt wird."),
    ).toBeInTheDocument();
    expect(gestartet).toBe(false);
    await nutzer.click(screen.getByRole("checkbox", { name: /jetzige Stand ersetzt wird/ }));
    await nutzer.click(los);

    // e) Fortschritt bis zum Ergebnis, 503 beim Tausch ohne Fehlermeldung
    expect(
      await screen.findByRole("heading", { name: "Die Sicherung wird wiederhergestellt" }),
    ).toBeInTheDocument();
    expect(gesendet(attrappe, "/backup/restore/execute")).toEqual({
      source_id: QUELLE_STICK.id,
      passphrase: "Rote Scheibe 1972",
      confirm: QUELLE_STICK.id,
      apply_journal: true,
      accept_lockout: true,
    });
    expect(screen.getByText("Sicherung einspielen")).toBeInTheDocument();
    expect(
      await screen.findByText(
        /schaltet gerade auf die wiederhergestellten Daten um/,
        {},
        {
          timeout: 5000,
        },
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole(
        "heading",
        { name: "Die Sicherung ist wiederhergestellt" },
        { timeout: 8000 },
      ),
    ).toBeInTheDocument();
    expect(abfragen).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText("Keine Verbindung zum Server")).not.toBeInTheDocument();
    expect(
      screen.getByText(/7 Eingaben bei den Ergebnissen wurden nachgetragen/),
    ).toBeInTheDocument();
    expect(screen.getByText(/2 Eingaben ließen sich nicht nachtragen/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fertig" })).toBeInTheDocument();
  });

  it("zeigt Probleme der Vorschau und bietet nur eine andere Sicherung an", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": anmeldung(["*"]),
      "/backup/maintenance": KEINE_WARTUNG,
      "/backup/restore/status": lauf({ state: "idle", step: null }),
      "/backup/restore/sources": {
        usb_present: false,
        restore_running: false,
        sources: [QUELLE_SERVER],
      },
      "/backup/restore/preview": () =>
        json(
          vorschau({
            source: QUELLE_SERVER,
            restorable: false,
            problems: ["Die Sicherung stammt von einer neueren Version der App."],
          }),
        ),
    });
    const nutzer = userEvent.setup();
    renderApp("/system/sicherung/wiederherstellen");

    expect(await screen.findByText(/Sicherungs-Stick steckt nicht im Server/)).toBeInTheDocument();
    const [server] = await screen.findAllByRole("radio");
    await nutzer.click(server as HTMLElement);
    await nutzer.click(screen.getByRole("button", { name: "Weiter mit dieser Sicherung" }));
    // Ohne Passwort direkt zur Vorschau
    expect(
      await screen.findByText("Diese Sicherung lässt sich so nicht wiederherstellen"),
    ).toBeInTheDocument();
    expect(screen.getByText(/neueren Version der App/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Weiter zur Bestätigung" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Andere Sicherung wählen" })).toBeInTheDocument();
  });

  it("erklärt den Leerzustand ohne Stick", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": anmeldung(["*"]),
      "/backup/maintenance": KEINE_WARTUNG,
      "/backup/restore/status": lauf({ state: "idle", step: null }),
      "/backup/restore/sources": { usb_present: false, restore_running: false, sources: [] },
    });
    renderApp("/system/sicherung/wiederherstellen");
    expect(await screen.findByText("Keine Sicherung gefunden")).toBeInTheDocument();
    expect(screen.getByText(/Steck den Sicherungs-Stick/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Erneut suchen" })).toBeInTheDocument();
  });

  it("öffnet direkt den Fortschritt, wenn schon eine Wiederherstellung läuft", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": anmeldung(["*"]),
      "/backup/maintenance": { ...KEINE_WARTUNG, active: true },
      "/backup/restore/status": lauf(),
    });
    renderApp("/system/sicherung/wiederherstellen");
    expect(
      await screen.findByRole("heading", { name: "Die Sicherung wird wiederhergestellt" }),
    ).toBeInTheDocument();
    // Hinweis für alle Geräte in der Kopfzeile
    expect(screen.getByText("Die Daten werden gerade wiederhergestellt.")).toBeInTheDocument();
  });
});

describe("Rechte der Sicherung", () => {
  const SICHERUNG = {
    "/health": HEALTH,
    "/backup/maintenance": KEINE_WARTUNG,
    "/backup/status": {
      usb: {
        present: true,
        writable: true,
        free_bytes: 1e9,
        last_seen_at: "2026-11-22T00:00:00Z",
      },
      last_snapshot: null,
      last_usb_copy: null,
      journal: { pending: 0 },
      warning: null,
      passphrase_set: false,
    },
    "/backup/settings": {
      enabled: true,
      usb_enabled: true,
      snapshot_interval_minutes: 5,
      keep_local: 12,
      keep_usb: 48,
      warn_all_stations: true,
      warn_on_display: false,
      encrypt: true,
    },
    "/backup/runs?limit=50": [],
    "/backup/warning": { warning: null, warn_all_stations: true, warn_on_display: false },
  };

  it("Turnierleitung: „Jetzt sichern“ ja, Einrichten und Wiederherstellen nein", async () => {
    apiAttrappe({
      ...SICHERUNG,
      "/auth/status": anmeldung(["backup.read", "backup.run", "tournament.*"], "Turnierleitung"),
    });
    renderApp("/system/sicherung");
    expect(await screen.findByRole("button", { name: "Jetzt sichern" })).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByText("Stick und Passwort richtet ein Administrator ein."),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: "Passwort festlegen" })).not.toBeInTheDocument();
    expect(screen.queryByText("Sicherung wiederherstellen")).not.toBeInTheDocument();
  });

  it("ohne backup.restore ist die Seite gesperrt", async () => {
    apiAttrappe({
      ...SICHERUNG,
      "/auth/status": anmeldung(["backup.read", "backup.run"], "Turnierleitung"),
    });
    renderApp("/system/sicherung/wiederherstellen");
    expect(await screen.findByText("Nur für Administratoren")).toBeInTheDocument();
  });

  it("Administrator: Einstieg in die Wiederherstellung sichtbar", async () => {
    apiAttrappe({ ...SICHERUNG, "/auth/status": anmeldung(["*"]) });
    renderApp("/system/sicherung");
    expect(await screen.findByRole("link", { name: "Wiederherstellen …" })).toHaveAttribute(
      "href",
      "/system/sicherung/wiederherstellen",
    );
  });
});
