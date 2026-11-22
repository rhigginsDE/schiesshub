import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RechteProvider } from "../../app/berechtigungen";
import { Meldungen, meldungenLeeren } from "../../components/Meldungen";
import {
  type Aufruf,
  renderAnsicht,
  serverAttrappe,
  type TestAntwort,
} from "../teilnehmer/testhilfe";
import type { TurnierUebersicht } from "../turnier/typen";
import { StandSeite } from "./StandSeite";
import { stationStart } from "./testdaten";

const T = "78a0a62a-fd80-4ef3-876a-3e7ad7a332b6";
const R = "46c19d4d-52f9-4ff1-956e-32630f067fd0";
const W_Q = "b5c26783-fdd4-4dfc-92d4-3fc47a9243d9";
const W_Z = "a579cdfc-a843-4824-8212-2b328bcd0834";

const einstellungen = {
  currency: "EUR",
  default_fee_first_cents: 0,
  default_fee_repeat_cents: 0,
  default_multi_start: true,
  default_max_starts: 3,
  default_multi_start_rule: "best",
  default_changeover_minutes: 5,
  default_capture_mode: "series",
  first_start_number: 1,
  display: {},
} as const;

const turnier = {
  id: T,
  name: "Herbstpokal",
  organizer: null,
  date_from: "2026-12-05",
  date_to: "2026-12-05",
  status: "active",
  template: "open",
  settings: einstellungen,
  created_at: "2026-11-21T10:00:00Z",
  updated_at: "2026-11-21T10:00:00Z",
} as const;

function wettbewerb(id: string, planung: "queue" | "schedule") {
  return {
    id,
    tournament_id: T,
    range_id: R,
    sort: 0,
    catalog_federation: "bds",
    catalog_code: planung === "queue" ? "4401" : "1001",
    name: planung === "queue" ? "Selbstladeflinte" : "Pistole bis 9 mm",
    definition: {},
    capture_mode: "series",
    multi_start: true,
    max_starts: 3,
    multi_start_rule: "best",
    fee_first_cents: 800,
    fee_repeat_cents: 500,
    class_ids: [],
    combined_ranking: false,
    planning: planung,
    heat_minutes: planung === "schedule" ? 15 : null,
    changeover_minutes: 5,
    definition_revision: 1,
  };
}

function uebersicht(planungen: ("queue" | "schedule")[]): TurnierUebersicht {
  return {
    ...turnier,
    ranges: [{ id: R, tournament_id: T, name: "15-m-Stand", lane_count: 2, sort: 0 }],
    classes: [],
    competitions: planungen.map((p) => wettbewerb(p === "queue" ? W_Q : W_Z, p)),
  } as unknown as TurnierUebersicht;
}

const wartend = stationStart({
  start_id: "s-1",
  start_number: 7,
  display_name: "Markus Brandt",
  competition_id: W_Q,
  competition_name: "Selbstladeflinte",
  competition_code: "4401",
  queue_position: 1,
});
const aufgerufen = stationStart({
  start_id: "s-2",
  entry_id: "e-2",
  start_number: 8,
  display_name: null,
  competition_id: W_Q,
  competition_name: "Selbstladeflinte",
  competition_code: "4401",
  status: "called",
  lane: 1,
  // Ortszeit 09:05 – die Kachel zeigt die Aufrufzeit des Servers, nicht die des Browsers.
  called_at: new Date(2026, 10, 22, 9, 5).toISOString(),
});

function routen(
  planungen: ("queue" | "schedule")[],
  extra: Record<string, TestAntwort | ((a: Aufruf) => TestAntwort)> = {},
) {
  return serverAttrappe({
    "GET /tournaments": { inhalt: [turnier] },
    [`GET /tournaments/${T}/overview`]: { inhalt: uebersicht(planungen) },
    [`GET /tournaments/${T}/ranges/${R}/queue?names=full`]: {
      inhalt: {
        range_id: R,
        lane_count: 2,
        waiting: planungen.includes("queue") ? [wartend] : [],
        lanes: [
          { lane: 1, start: planungen.includes("queue") ? aufgerufen : null },
          { lane: 2, start: null },
        ],
      },
    },
    [`GET /tournaments/${T}/ranges/${R}/heats`]: { inhalt: [] },
    [`GET /tournaments/${T}/startlist?range_id=${R}&names=full`]: { inhalt: [] },
    ...extra,
  });
}

/** Stand samt Meldungen am Bildschirmrand (die App-Shell zeigt sie sonst). */
function StandMitMeldungen() {
  return (
    <>
      <StandSeite suche={{}} onSuche={() => {}} />
      <Meldungen />
    </>
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  meldungenLeeren();
});

// Menüs und Dialoge brauchen unter Last (alle Tests parallel) länger als die üblichen 5 s.
describe("Stand", { timeout: 15000 }, () => {
  it("zeigt die Bahnen und ruft mit dem einen Hauptknopf die Nächsten auf", async () => {
    const aufrufe = routen(["queue"], {
      [`POST /tournaments/${T}/ranges/${R}/call-next`]: {
        inhalt: {
          called: [{ id: "s-1" }],
          skipped: [],
          held_lanes: [],
          upcoming_heat: null,
          message: null,
        },
      },
    });
    const benutzer = userEvent.setup();
    renderAnsicht(() => <StandMitMeldungen />);

    const bahn1 = await screen.findByRole("listitem", { name: "Bahn 1" });
    expect(within(bahn1).getByText("Name nicht angezeigt")).toBeInTheDocument();
    expect(within(bahn1).getByText("8")).toBeInTheDocument();
    expect(within(bahn1).getByText("seit 09:05")).toBeInTheDocument();
    expect(screen.getByText("Herbstpokal")).toBeInTheDocument();
    expect(screen.getByText("Markus Brandt")).toBeInTheDocument();

    await benutzer.click(screen.getByRole("button", { name: /Nächste aufrufen/ }));
    const aufruf = aufrufe.find((a) => a.methode === "POST" && a.pfad.endsWith("/call-next"));
    expect(aufruf).toBeDefined();
    expect(aufruf?.inhalt).toBeUndefined();
    expect(await screen.findByText("1 Start aufgerufen")).toBeInTheDocument();
  });

  it("QA G-11: zeigt den Text des Servers zu Übersprungenen und freigehaltenen Bahnen", async () => {
    routen(["queue"], {
      [`POST /tournaments/${T}/ranges/${R}/call-next`]: {
        inhalt: {
          called: [],
          skipped: [
            {
              start_id: "s-1",
              entry_id: "e-s-1",
              start_number: 7,
              competition_id: W_Q,
              queue_position: 1,
              reason: "on_lane",
            },
          ],
          held_lanes: [2],
          upcoming_heat: null,
          message: "Startnummer 7 steht gerade auf einer Bahn. Bahn 2 bleibt für Durchgang 2 frei.",
        },
      },
    });
    const benutzer = userEvent.setup();
    renderAnsicht(() => <StandMitMeldungen />);

    await benutzer.click(await screen.findByRole("button", { name: /Nächste aufrufen/ }));
    expect(await screen.findByText("Niemand aufgerufen")).toBeInTheDocument();
    expect(screen.getByText(/Bahn 2 bleibt für Durchgang 2 frei/)).toBeInTheDocument();
  });

  it("QA G-11: „Nächsten auf Bahn 2“ ruft über call-next mit Bahn auf", async () => {
    const aufrufe = routen(["queue"], {
      [`POST /tournaments/${T}/ranges/${R}/call-next`]: {
        inhalt: { called: [], skipped: [], held_lanes: [], upcoming_heat: null, message: null },
      },
    });
    const benutzer = userEvent.setup();
    renderAnsicht(() => <StandSeite suche={{}} onSuche={() => {}} />);

    const bahn2 = await screen.findByRole("listitem", { name: "Bahn 2" });
    await benutzer.click(within(bahn2).getByRole("button", { name: "Nächsten auf Bahn 2" }));
    const aufruf = aufrufe.find((a) => a.pfad.endsWith("/call-next"));
    expect(aufruf?.inhalt).toEqual({ lane: 2 });
    expect(aufrufe.some((a) => a.pfad.endsWith("/call") && a.methode === "POST")).toBe(false);
  });

  it("QA G-11: fragt bei bald beginnendem Durchgang zurück und wiederholt mit Bestätigung", async () => {
    const aufrufe = routen(["queue"], {
      [`POST /tournaments/${T}/ranges/${R}/call-next`]: (aufruf) =>
        (aufruf.inhalt as { confirm_heat_conflict?: boolean } | undefined)?.confirm_heat_conflict
          ? {
              inhalt: {
                called: [{ id: "s-1" }],
                skipped: [],
                held_lanes: [],
                upcoming_heat: null,
                message: null,
              },
            }
          : {
              status: 409,
              inhalt: {
                detail: "Durchgang 2 beginnt um 05:15 und braucht Bahn 2.",
                code: "heat_imminent",
              },
            },
    });
    const benutzer = userEvent.setup();
    renderAnsicht(() => <StandMitMeldungen />);

    await benutzer.click(await screen.findByRole("button", { name: /Nächste aufrufen/ }));
    const dialog = await screen.findByRole("dialog", {}, { timeout: 5000 });
    expect(
      within(dialog).getByText("Durchgang 2 beginnt um 05:15 und braucht Bahn 2."),
    ).toBeInTheDocument();
    await benutzer.click(within(dialog).getByRole("button", { name: "Trotzdem aufrufen" }));

    const gesendet = aufrufe.filter((a) => a.pfad.endsWith("/call-next")).map((a) => a.inhalt);
    expect(gesendet).toEqual([undefined, { confirm_heat_conflict: true }]);
    expect(await screen.findByText("1 Start aufgerufen")).toBeInTheDocument();
  });

  it("QA G-11: zeigt ruhig, dass ein Durchgang bald Bahnen braucht", async () => {
    routen(["queue"], {
      [`GET /tournaments/${T}/ranges/${R}/queue?names=full`]: {
        inhalt: {
          range_id: R,
          lane_count: 2,
          waiting: [wartend],
          lanes: [
            { lane: 1, start: null },
            { lane: 2, start: null },
          ],
          upcoming_heat: {
            heat_id: "h-2",
            number: 2,
            starts_at: new Date(2026, 10, 22, 5, 15).toISOString(),
            ends_at: new Date(2026, 10, 22, 5, 30).toISOString(),
            lanes: [2],
            reserve_minutes: 10,
            reserved_from: new Date(2026, 10, 22, 5, 5).toISOString(),
            active: false,
          },
        },
      },
    });
    renderAnsicht(() => <StandSeite suche={{}} onSuche={() => {}} />);
    expect(
      await screen.findByText("Durchgang 2 um 05:15 braucht Bahn 2 – wird ab 05:05 freigehalten"),
    ).toBeInTheDocument();
  });

  it("bricht einen Start erst nach Rückfrage ab", async () => {
    const aufrufe = routen(["queue"], {
      [`POST /tournaments/${T}/starts/s-2/abort`]: {
        inhalt: { ...aufgerufen, status: "aborted" },
      },
    });
    const benutzer = userEvent.setup();
    renderAnsicht(() => <StandSeite suche={{}} onSuche={() => {}} />);

    const bahn1 = await screen.findByRole("listitem", { name: "Bahn 1" });
    await benutzer.click(within(bahn1).getByRole("button", { name: /Abbrechen/ }));
    // Unter Last braucht das Menü länger als die übliche Sekunde.
    const geduld = { timeout: 5000 };
    await benutzer.click(await screen.findByRole("menuitem", { name: "Aufgegeben" }, geduld));

    const dialog = await screen.findByRole("dialog", {}, geduld);
    expect(within(dialog).getByText("Startnummer 8: Aufgegeben?")).toBeInTheDocument();
    expect(aufrufe.some((a) => a.pfad.endsWith("/abort"))).toBe(false);

    await benutzer.click(within(dialog).getByRole("button", { name: "Start abbrechen" }));
    const abbruch = aufrufe.find((a) => a.pfad.endsWith("/abort"));
    expect(abbruch?.inhalt).toEqual({ abort_reason: "dnf" });
  });

  it("zeigt intern den vollen Namen, den der Server mit names=full liefert", async () => {
    const aufrufe = routen(["queue"], {
      [`GET /tournaments/${T}/ranges/${R}/queue?names=full`]: {
        inhalt: {
          range_id: R,
          lane_count: 2,
          waiting: [],
          lanes: [
            { lane: 1, start: { ...aufgerufen, full_name: "Paul Winter" } },
            { lane: 2, start: null },
          ],
        },
      },
    });
    renderAnsicht(() => <StandSeite suche={{}} onSuche={() => {}} />);

    const bahn1 = await screen.findByRole("listitem", { name: "Bahn 1" });
    expect(await within(bahn1).findByText("Paul Winter")).toBeInTheDocument();
    expect(within(bahn1).queryByText("Name nicht angezeigt")).toBeNull();
    expect(aufrufe.some((a) => a.pfad.includes("/entries"))).toBe(false);
  });

  it("fragt ohne Recht auf volle Namen ohne names=full (kein 403)", async () => {
    const aufrufe = routen(["queue"], {
      [`GET /tournaments/${T}/ranges/${R}/queue`]: {
        inhalt: {
          range_id: R,
          lane_count: 2,
          waiting: [wartend],
          lanes: [
            { lane: 1, start: aufgerufen },
            { lane: 2, start: null },
          ],
        },
      },
      [`GET /tournaments/${T}/startlist?range_id=${R}`]: { inhalt: [] },
    });
    const rechte = { offen: false, erlaubt: ["result.read", "tournament.read"] } as const;
    renderAnsicht(() => (
      <RechteProvider value={rechte}>
        <StandSeite suche={{}} onSuche={() => {}} />
      </RechteProvider>
    ));

    const bahn1 = await screen.findByRole("listitem", { name: "Bahn 1" });
    expect(within(bahn1).getByText("Name nicht angezeigt")).toBeInTheDocument();
    expect(aufrufe.some((a) => a.pfad.includes("names=full"))).toBe(false);
  });

  it("hält die Bahn bis zum Abschluss, zeigt den Fortschritt und gibt sie nach Rückfrage frei", async () => {
    const inErfassung = { ...aufgerufen, status: "captured" as const };
    const aufrufe = routen(["queue"], {
      [`GET /tournaments/${T}/ranges/${R}/queue?names=full`]: {
        inhalt: {
          range_id: R,
          lane_count: 2,
          waiting: [wartend],
          lanes: [
            {
              lane: 1,
              start: inErfassung,
              progress: {
                section_id: null,
                series_done: 2,
                series_total: 4,
                complete: false,
                section_number: 1,
                section_count: 1,
                series_done_overall: 2,
                series_total_overall: 4,
              },
            },
            { lane: 2, start: null, progress: null },
          ],
        },
      },
      [`POST /tournaments/${T}/starts/s-2/release-lane`]: { inhalt: {} },
    });
    const benutzer = userEvent.setup();
    renderAnsicht(() => <StandSeite suche={{}} onSuche={() => {}} />);

    const bahn1 = await screen.findByRole("listitem", { name: "Bahn 1" });
    expect(within(bahn1).getByText("wird erfasst")).toBeInTheDocument();
    expect(within(bahn1).getByText("2 von 4 Serien erfasst")).toBeInTheDocument();
    expect(within(bahn1).getByRole("link", { name: /Ergebnis erfassen/ })).toHaveAttribute(
      "href",
      "/erfassung?start=s-2",
    );
    expect(within(bahn1).queryByRole("button", { name: /Zurückstellen/ })).toBeNull();

    await benutzer.click(within(bahn1).getByRole("button", { name: /Bahn freigeben/ }));
    const dialog = await screen.findByRole("dialog", {}, { timeout: 5000 });
    expect(within(dialog).getByText("Bahn 1 freigeben?")).toBeInTheDocument();
    expect(aufrufe.some((a) => a.pfad.endsWith("/release-lane"))).toBe(false);
    await benutzer.click(within(dialog).getByRole("button", { name: "Bahn freigeben" }));
    expect(aufrufe.some((a) => a.methode === "POST" && a.pfad.endsWith("/release-lane"))).toBe(
      true,
    );
  });

  it("QA G-3: zeigt die Kennziffer vor dem Wettbewerb und, mit Name, im Abbruch-Dialog", async () => {
    routen(["queue"]);
    const benutzer = userEvent.setup();
    renderAnsicht(() => <StandSeite suche={{}} onSuche={() => {}} />);

    const bahn1 = await screen.findByRole("listitem", { name: "Bahn 1" });
    expect(within(bahn1).getByText("4401")).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Startnummer 7 (4401 Selbstladeflinte, 1. Start) aufrufen",
      }),
    ).toBeInTheDocument();

    await benutzer.click(
      screen.getByRole("button", { name: /Weitere Aktionen für Startnummer 7/ }),
    );
    await benutzer.click(
      await screen.findByRole(
        "menuitem",
        { name: "Disqualifiziert", hidden: true },
        { timeout: 5000 },
      ),
    );
    const dialog = await screen.findByRole("dialog", {}, { timeout: 5000 });
    expect(
      within(dialog).getByText("Startnummer 7 · Markus Brandt: Disqualifiziert?"),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/„4401 Selbstladeflinte“/)).toBeInTheDocument();
  });

  it("QA G-2: Standaufsicht ohne start.edit sieht weder „Durchgänge anlegen“ noch „Umsetzen“", async () => {
    const eingeplant = stationStart({
      start_id: "s-3",
      entry_id: "e-3",
      start_number: 9,
      display_name: "Jana Hoffmann",
      competition_id: W_Z,
      competition_name: "Pistole bis 9 mm",
      heat_id: "h-1",
      heat_number: 1,
      heat_starts_at: "2026-12-05T09:00:00Z",
      lane: 1,
    });
    routen(["queue", "schedule"], {
      [`GET /tournaments/${T}/ranges/${R}/heats`]: {
        inhalt: [
          {
            id: "h-1",
            range_id: R,
            number: 1,
            starts_at: "2099-12-05T09:00:00Z",
            ends_at: "2099-12-05T09:15:00Z",
            capacity: 2,
            booked: 1,
          },
        ],
      },
      [`GET /tournaments/${T}/startlist?range_id=${R}&names=full`]: { inhalt: [eingeplant] },
    });
    const benutzer = userEvent.setup();
    const rechte = {
      offen: false,
      erlaubt: ["start.read", "start.call", "tournament.read"],
    } as const;
    renderAnsicht(() => (
      <RechteProvider value={rechte}>
        <StandSeite suche={{}} onSuche={() => {}} />
      </RechteProvider>
    ));

    expect(await screen.findByText("Durchgang 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Durchgänge anlegen" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Aktionen für Durchgang 1" })).toBeNull();
    // Aufrufen bleibt; Abbrechen braucht start.abort, Umsetzen start.edit.
    await benutzer.click(screen.getByRole("button", { name: "Aktionen für Startnummer 9" }));
    expect(
      await screen.findByRole(
        "menuitem",
        { name: "Einzeln aufrufen", hidden: true },
        { timeout: 5000 },
      ),
    ).toBeInTheDocument();
    // Mantine blendet das Menü ein; während der Einblendung gelten die Einträge als verborgen.
    expect(screen.queryByRole("menuitem", { name: "Nicht angetreten", hidden: true })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Umsetzen", hidden: true })).toBeNull();
    expect(
      screen.queryByRole("menuitem", { name: "Aus dem Durchgang nehmen", hidden: true }),
    ).toBeNull();
  });

  it("QA G-2: nur ansehen (start.read): keine Aktionen, aber ein Hinweis", async () => {
    routen(["queue"], {
      [`GET /tournaments/${T}/ranges/${R}/queue`]: {
        inhalt: {
          range_id: R,
          lane_count: 2,
          waiting: [wartend],
          lanes: [
            { lane: 1, start: aufgerufen },
            { lane: 2, start: null },
          ],
        },
      },
      [`GET /tournaments/${T}/startlist?range_id=${R}`]: { inhalt: [] },
    });
    const rechte = { offen: false, erlaubt: ["start.read", "tournament.read"] } as const;
    renderAnsicht(() => (
      <RechteProvider value={rechte}>
        <StandSeite suche={{}} onSuche={() => {}} />
      </RechteProvider>
    ));

    const bahn1 = await screen.findByRole("listitem", { name: "Bahn 1" });
    expect(screen.getByText(/Aufrufen ist für deine Rolle nicht freigegeben/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Nächste aufrufen/ })).toBeNull();
    expect(within(bahn1).queryByRole("button", { name: /Abbrechen/ })).toBeNull();
    expect(within(bahn1).queryByRole("button", { name: /Zurückstellen/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Startnummer 7 .* aufrufen/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Weitere Aktionen/ })).toBeNull();
  });

  it("QA G-2: mit dem neuen Recht start.abort allein darf man abbrechen, sonst nichts", async () => {
    routen(["queue"], {
      [`GET /tournaments/${T}/ranges/${R}/queue`]: {
        inhalt: {
          range_id: R,
          lane_count: 2,
          waiting: [wartend],
          lanes: [
            { lane: 1, start: aufgerufen },
            { lane: 2, start: null },
          ],
        },
      },
      [`GET /tournaments/${T}/startlist?range_id=${R}`]: { inhalt: [] },
    });
    const rechte = {
      offen: false,
      erlaubt: ["start.read", "start.abort", "tournament.read"],
    } as const;
    renderAnsicht(() => (
      <RechteProvider value={rechte}>
        <StandSeite suche={{}} onSuche={() => {}} />
      </RechteProvider>
    ));

    const bahn1 = await screen.findByRole("listitem", { name: "Bahn 1" });
    expect(within(bahn1).getByRole("button", { name: /Abbrechen/ })).toBeInTheDocument();
    expect(within(bahn1).queryByRole("button", { name: /Zurückstellen/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Nächste aufrufen/ })).toBeNull();
  });

  it("legt Durchgänge als Serie an und zeigt Feldfehler des Servers", async () => {
    let versuch = 0;
    const aufrufe = routen(["schedule"], {
      [`POST /tournaments/${T}/ranges/${R}/heats/series`]: () => {
        versuch += 1;
        return versuch === 1
          ? {
              status: 422,
              inhalt: {
                detail: "Feld ‚count‘: darf höchstens 200 sein.",
                errors: [{ field: "count", message: "darf höchstens 200 sein" }],
              },
            }
          : { status: 201, inhalt: [] };
      },
    });
    const benutzer = userEvent.setup();
    renderAnsicht(() => <StandSeite suche={{}} onSuche={() => {}} />);

    expect(await screen.findByText("Gerade wartet niemand auf diesem Stand.")).toBeInTheDocument();
    await benutzer.click(screen.getByRole("button", { name: "Durchgänge anlegen" }));
    const dialog = await screen.findByRole("dialog", {}, { timeout: 5000 });
    const anzahl = within(dialog).getByRole("textbox", { name: "Anzahl" });
    await benutzer.clear(anzahl);
    await benutzer.type(anzahl, "3");
    await benutzer.click(within(dialog).getByRole("button", { name: "Durchgänge anlegen" }));

    expect(await within(dialog).findByText("darf höchstens 200 sein")).toBeInTheDocument();
    const gesendet = aufrufe.find((a) => a.pfad.endsWith("/heats/series"));
    expect(gesendet?.inhalt).toMatchObject({ competition_id: W_Z, count: 3 });
    expect(gesendet?.inhalt).toHaveProperty("starts_at", expect.any(String));

    await benutzer.click(within(dialog).getByRole("button", { name: "Durchgänge anlegen" }));
    expect(versuch).toBe(2);
  });
});
