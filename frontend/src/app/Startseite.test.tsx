import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { beispielTurnier, TURNIER_ID } from "../modules/turnier/testdaten";
import { apiAttrappe, renderApp } from "../test/app";

const HEALTH = { status: "ok", version: "0.1.0", db: "ok", katalog: null };
const STATUS = {
  setup_required: false,
  auth_enforced: false,
  device: null,
  user: null,
  role: null,
  permissions: [],
};

function start(nr: number, status: string) {
  return { start_id: `s${nr}`, entry_id: `e${nr}`, start_number: nr, status };
}

describe("Startseite: Ablauf", () => {
  it("ohne Turnier ist „Turnier anlegen“ die eine Hauptaktion, die Anmeldung wartet", async () => {
    apiAttrappe({ "/health": HEALTH, "/auth/status": STATUS, "/tournaments": [] });
    renderApp("/");
    expect(await screen.findByText("Noch kein Turnier angelegt.", { exact: false })).toBeVisible();
    expect(screen.getByRole("button", { name: "Turnier anlegen" })).toBeInTheDocument();
    const schritte = screen.getAllByRole("listitem").filter((li) => li.closest("ol"));
    expect(schritte).toHaveLength(5);
    expect(schritte[0]).toHaveAttribute("aria-current", "step");
    expect(
      within(schritte[1] as HTMLElement).getByText("Geht, sobald das Turnier gestartet ist."),
    ).toBeVisible();
    // Weitere Bereiche bleiben erreichbar.
    expect(screen.getByRole("heading", { name: "Weitere Bereiche" })).toBeInTheDocument();
  });

  it("am Wettkampftag mit offenen Starts: „Ergebnisse erfassen“ mit Zahlen vom Server", async () => {
    const turnier = { ...beispielTurnier("active"), ranges: [], classes: [], competitions: [] };
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": STATUS,
      "/tournaments": [turnier],
      [`/tournaments/${TURNIER_ID}/overview`]: turnier,
      [`/tournaments/${TURNIER_ID}/startlist`]: [start(1, "final"), start(2, "registered")],
    });
    renderApp("/");
    const knopf = await screen.findByRole("link", { name: "Ergebnisse erfassen" });
    expect(knopf).toHaveAttribute("href", "/erfassung");
    expect(screen.getByText("2 angemeldet, 2 Starts gebucht.")).toBeInTheDocument();
    expect(screen.getByText(/1 Start offen, 1 abgeschlossen\./)).toBeInTheDocument();
    expect(screen.queryByText("Noch nicht möglich")).not.toBeInTheDocument();
  });
});

describe("Startseite: nur was die Rolle darf", () => {
  const turnier = { ...beispielTurnier("active"), ranges: [], classes: [], competitions: [] };
  const mitRolle = (permissions: string[], teil: Record<string, unknown> = {}) => ({
    ...STATUS,
    auth_enforced: true,
    device: { id: "g1", name: "Tablet Stand", default_role_id: null },
    user: { id: "p1", name: "S. Krämer" },
    role: { id: "r1", name: "Standaufsicht" },
    permissions,
    pin_min_length: 4,
    max_failed_logins: 5,
    lockout_minutes: 5,
    ...teil,
  });

  it("Standaufsicht: nur der Stand, mit „Zum Stand“ als Hauptaktion und eigenem Menüpunkt", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": mitRolle(["start.call", "start.read", "tournament.read"]),
      "/tournaments": [turnier],
      [`/tournaments/${TURNIER_ID}/overview`]: turnier,
      [`/tournaments/${TURNIER_ID}/startlist`]: [start(1, "final"), start(2, "registered")],
    });
    renderApp("/");
    const knopf = await screen.findByRole("link", { name: "Zum Stand" });
    expect(knopf).toHaveAttribute("href", "/erfassung/stand");
    expect(screen.getByRole("heading", { name: "Am Stand aufrufen" })).toBeInTheDocument();
    expect(screen.queryByText("Schützen anmelden")).not.toBeInTheDocument();
    expect(screen.queryByText("Turnier einrichten")).not.toBeInTheDocument();
    const navigation = screen.getByRole("navigation", { name: "Stationen" });
    expect(within(navigation).getByRole("link", { name: "Stand" })).toHaveAttribute(
      "href",
      "/erfassung/stand",
    );
  });

  it("ohne jede Station: ein Satz statt einer leeren Seite", async () => {
    apiAttrappe({ "/health": HEALTH, "/auth/status": mitRolle([]) });
    renderApp("/");
    expect(await screen.findByText("Dir ist noch keine Aufgabe zugeteilt")).toBeVisible();
  });

  it("Anzeige-Gerät ohne zugeordnete Anzeige: ruhige Seite statt Turnier und Verwaltung", async () => {
    apiAttrappe({
      "/health": HEALTH,
      "/auth/status": mitRolle(["display.read"], {
        user: null,
        role: { id: "r5", name: "Anzeige" },
      }),
    });
    renderApp("/");
    expect(
      await screen.findByRole("heading", {
        name: "Diesem Gerät ist noch keine Anzeige zugeordnet",
      }),
    ).toBeVisible();
  });
});
