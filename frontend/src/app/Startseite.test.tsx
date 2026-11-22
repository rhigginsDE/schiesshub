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
