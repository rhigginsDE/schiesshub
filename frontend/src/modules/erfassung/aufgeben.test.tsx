import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Target } from "lucide-react";
import { beforeEach, describe, expect, it } from "vitest";
import { meldungenLeeren } from "../../components/Meldungen";
import { renderAnsicht, serverAttrappe } from "../teilnehmer/testhilfe";
import type { AbschnittWertung, ErgebnisStand, Rohwerte, SerienWertung } from "./api";
import { offeneSerien, orteText } from "./aufgeben";
import { ErfassungSeite } from "./ErfassungSeite";
import { FALLSCHEIBE, maske, PRAEZISION, stand, wertung } from "./testdaten";

// Mantines Textarea mit `autosize` (Bemerkung im Abbruch-Dialog) horcht auf `document.fonts`;
// jsdom kennt das nicht.
if (!("fonts" in document)) {
  Object.defineProperty(document, "fonts", {
    configurable: true,
    value: { addEventListener() {}, removeEventListener() {}, ready: Promise.resolve() },
  });
}

const T = "78a0a62a-fd80-4ef3-876a-3e7ad7a332b6";
const R = "46c19d4d-52f9-4ff1-956e-32630f067fd0";
const S = "s-1";

function serie(teil: Partial<SerienWertung> & { number: number }): SerienWertung {
  return {
    struck: false,
    status: "normal",
    captured: false,
    complete: false,
    shots_entered: 0,
    shots_expected: 0,
    rings: null,
    tens: null,
    inner_tens: null,
    measured_time_cs: null,
    time_cs: null,
    standing: null,
    penalty_cs: null,
    total_cs: null,
    ...teil,
  };
}

function abschnitt(id: string, series: SerienWertung[]): AbschnittWertung {
  return {
    id,
    name: id,
    complete: series.every((x) => x.complete || x.struck),
    rings: null,
    time_cs: null,
    penalty_cs: null,
    overtime_s: null,
    deduction: null,
    subtotal: "0",
    result: "0",
    floored: false,
    series,
  };
}

type SerieRoh = Record<string, unknown> | null;

/**
 * Wie der Server eine Fallscheiben-Serie sieht (`app.scoring`): angefangen, sobald ein Wert da ist;
 * vollständig mit Zeit und stehenden Scheiben, bei „Abbruch durch den Schützen“ oder „Zeitlimit“
 * mit den stehenden Scheiben allein, bei „Waffenstörung“ immer.
 */
function fallscheibeWertung(raw: Rohwerte) {
  const serien = ((raw.sections as Record<string, { series?: SerieRoh[] }> | undefined)?.fallscheibe
    ?.series ?? []) as SerieRoh[];
  const liste = [0, 1, 2].map((index) => {
    const roh = serien[index] ?? {};
    const status = (roh.status as SerienWertung["status"] | undefined) ?? "normal";
    const stehend = roh.standing !== undefined;
    const complete =
      status === "malfunction_before_first_shot" ||
      (status === "normal" ? roh.time_cs !== undefined && stehend : stehend);
    return serie({
      number: index + 1,
      struck: index === 2,
      status,
      captured: Object.keys(roh).length > 0,
      complete,
      time_cs: typeof roh.time_cs === "number" ? roh.time_cs : null,
      standing: typeof roh.standing === "number" ? roh.standing : null,
    });
  });
  const fertig = liste.filter((x) => !x.struck && x.complete).length;
  return wertung({
    model: "zeit_plus_zuschlaege",
    score: "20.00",
    complete: fertig >= 2,
    sections: [abschnitt("fallscheibe", liste)],
    progress: {
      shots_entered: 0,
      shots_expected: 0,
      series_complete: fertig,
      series_expected: 2,
      section_times_entered: 0,
      section_times_expected: 0,
    },
  });
}

function serverStand(raw: Rohwerte, teil: Partial<ErgebnisStand> = {}): ErgebnisStand {
  return stand({ raw, status: "captured", computed: fallscheibeWertung(raw), ...teil });
}

// Serie 1 fertig, Serie 2 angefangen: nur die Zeit ist erfasst.
const ANGEFANGEN: Rohwerte = {
  sections: { fallscheibe: { series: [{ time_cs: 2000, standing: 0 }, { time_cs: 1500 }] } },
};

describe("offeneSerien", () => {
  it("Fallscheibe: angefangene, unvollständige Serie mit Status „Abbruch durch den Schützen“", () => {
    const liste = offeneSerien(FALLSCHEIBE, fallscheibeWertung(ANGEFANGEN));
    expect(liste.map((o) => o.ort)).toEqual(["Serie 2"]);
    expect(liste[0]?.abbruchStatus).toBe("Abbruch durch den Schützen");
  });

  it("nicht geschossene, fertige und gestrichene Serien sind nicht offen", () => {
    const raw = { sections: { fallscheibe: { series: [{ time_cs: 2000, standing: 0 }] } } };
    expect(offeneSerien(FALLSCHEIBE, fallscheibeWertung(raw))).toEqual([]);
    const gestrichen = {
      sections: {
        fallscheibe: { series: [{ time_cs: 2000, standing: 0 }, null, { time_cs: 900 }] },
      },
    };
    expect(offeneSerien(FALLSCHEIBE, fallscheibeWertung(gestrichen))).toEqual([]);
  });

  it("nach „Abbruch durch den Schützen“ mit stehenden Scheiben ist die Serie fertig", () => {
    const raw = {
      sections: {
        fallscheibe: {
          series: [
            { time_cs: 2000, standing: 0 },
            { status: "aborted_by_shooter", standing: 3 },
          ],
        },
      },
    };
    expect(offeneSerien(FALLSCHEIBE, fallscheibeWertung(raw))).toEqual([]);
  });

  it("Ringe: eine halbe Serie zählt (fehlende Schüsse 0 Ringe), also nichts offen", () => {
    const halb = wertung({
      model: "ringe",
      sections: [
        abschnitt("praezision", [
          serie({
            number: 1,
            captured: true,
            complete: false,
            shots_entered: 2,
            shots_expected: 3,
          }),
          serie({ number: 2 }),
        ]),
      ],
    });
    expect(offeneSerien(PRAEZISION, halb)).toEqual([]);
  });

  it("Ringe minus Zeit: halbe Serie zählt nur mit Zeit", () => {
    const mit = (time_cs: number | null) =>
      wertung({
        model: "ringe_minus_zeit",
        sections: [
          abschnitt("praezision", [
            serie({ number: 1, captured: true, complete: false, time_cs }),
            serie({ number: 2 }),
          ]),
        ],
      });
    expect(offeneSerien(PRAEZISION, mit(1500))).toEqual([]);
    const ohneZeit = offeneSerien(PRAEZISION, mit(null));
    expect(ohneZeit.map((o) => o.ort)).toEqual(["Serie 1"]);
    // Die Serie kennt keinen Status „Abbruch durch den Schützen“: dann heißt es „fertig erfassen“.
    expect(ohneZeit[0]?.abbruchStatus).toBeNull();
  });

  it("ohne Wertung nichts; Orte als Aufzählung", () => {
    expect(offeneSerien(FALLSCHEIBE, null)).toEqual([]);
    const o = offeneSerien(FALLSCHEIBE, fallscheibeWertung(ANGEFANGEN));
    expect(orteText([...o, ...o, ...o], "und")).toBe("Serie 2, Serie 2 und Serie 2");
  });
});

// --- Bedienung -------------------------------------------------------------------------------

const turnier = {
  id: T,
  name: "Herbstpokal",
  organizer: null,
  date_from: "2026-12-05",
  date_to: "2026-12-05",
  status: "active",
  template: "open",
  settings: { currency: "EUR", first_start_number: 1, display: {} },
  created_at: "2026-11-21T10:00:00Z",
  updated_at: "2026-11-21T10:00:00Z",
};

const uebersicht = {
  ...turnier,
  ranges: [{ id: R, tournament_id: T, name: "Schießstand Flinte 15 m", lane_count: 2, sort: 0 }],
  classes: [],
  competitions: [{ id: "w", catalog_code: "4401", name: "Selbstladeflinte", range_id: R }],
};

const startZeile = {
  start_id: S,
  entry_id: "e-1",
  start_number: 7,
  display_name: "M. Brandt",
  club: null,
  class_id: "k",
  class_short: "S",
  competition_id: "w",
  competition_name: "Selbstladeflinte",
  range_id: R,
  attempt: 1,
  status: "captured",
  abort_reason: null,
  queue_position: null,
  lane: 1,
  heat_id: null,
  heat_number: null,
  heat_starts_at: null,
  called_at: null,
};

function routen(anfang: ErgebnisStand) {
  let server = anfang;
  const form = () => ({ inhalt: maske(FALLSCHEIBE, server) });
  return serverAttrappe({
    "GET /tournaments": { inhalt: [turnier] },
    [`GET /tournaments/${T}/overview`]: { inhalt: uebersicht },
    [`GET /tournaments/${T}/startlist?names=full`]: { inhalt: [startZeile] },
    [`GET /tournaments/${T}/results/needs-review`]: { inhalt: [] },
    [`GET /tournaments/${T}/starts/${S}/form`]: form,
    [`GET /tournaments/${T}/starts/${S}/form?capture_mode=series`]: form,
    [`GET /tournaments/${T}/starts/${S}/events`]: { inhalt: [] },
    [`PUT /tournaments/${T}/starts/${S}/raw`]: (aufruf) => {
      const inhalt = aufruf.inhalt as { raw: Rohwerte; base_seq: number };
      server = serverStand(inhalt.raw, { seq: inhalt.base_seq + 1 });
      return { inhalt: server };
    },
    [`POST /tournaments/${T}/starts/${S}/result/abort`]: (aufruf) => {
      const inhalt = aufruf.inhalt as { abort_reason: ErgebnisStand["abort_reason"] };
      server = {
        ...server,
        status: "aborted",
        abort_reason: inhalt.abort_reason,
        seq: server.seq + 1,
      };
      return { inhalt: server };
    },
  });
}

function anzeigen() {
  return renderAnsicht(() => (
    <ErfassungSeite station="erfassung" icon={Target} suche={{ start: S }} onSuche={() => {}} />
  ));
}

async function aufgebenWaehlen(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Start abbrechen" }));
  const dialog = await screen.findByRole("dialog");
  await user.click(within(dialog).getByRole("radio", { name: "Aufgegeben" }));
  return dialog;
}

beforeEach(() => {
  Element.prototype.scrollIntoView = () => {};
  localStorage.clear();
  sessionStorage.clear();
  meldungenLeeren();
});

describe("Aufgeben in der Erfassung", () => {
  it("offene Serie: Rückfrage sagt, was passiert, und trägt „Abbruch durch den Schützen“ ein", async () => {
    const aufrufe = routen(serverStand(ANGEFANGEN, { seq: 3 }));
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });

    const dialog = await aufgebenWaehlen(user);
    expect(within(dialog).getByText("Serie 2 ist noch nicht fertig erfasst.")).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "Damit Markus Brandt mit dem bisherigen Ergebnis gewertet wird, trag für diese Serie „Abbruch durch den Schützen“ ein.",
      ),
    ).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Start abbrechen" })).toBeNull();
    await user.click(
      within(dialog).getByRole("button", { name: "„Abbruch durch den Schützen“ eintragen" }),
    );

    // Kein Abbruch, sondern der Status an der Serie (die Zeit entfällt dabei).
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(
      () =>
        expect(aufrufe.filter((a) => a.methode === "PUT").at(-1)?.inhalt).toEqual({
          raw: {
            sections: {
              fallscheibe: {
                series: [{ time_cs: 2000, standing: 0 }, { status: "aborted_by_shooter" }],
              },
            },
          },
          base_seq: 3,
        }),
      { timeout: 3000 },
    );
    expect(aufrufe.some((a) => a.pfad.endsWith("/result/abort"))).toBe(false);

    // Hinweis führt weiter: stehende Scheiben fehlen noch, „Jetzt aufgeben“ wartet.
    expect(await screen.findByText("Aufgeben vorbereitet")).toBeInTheDocument();
    expect(
      await screen.findByText(/Trag noch Stehende Scheiben ein, dann tipp auf „Jetzt aufgeben“/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Jetzt aufgeben" })).toBeDisabled();

    // Das aktive Feld ist „Stehende Scheiben“ von Serie 2: eine Ziffer genügt.
    await user.keyboard("3");
    await waitFor(
      () => expect(screen.getByRole("button", { name: "Jetzt aufgeben" })).toBeEnabled(),
      { timeout: 3000 },
    );
    await user.click(screen.getByRole("button", { name: "Jetzt aufgeben" }));
    const zweiter = await screen.findByRole("dialog");
    expect(within(zweiter).getByRole("radio", { name: "Aufgegeben" })).toBeChecked();
    expect(within(zweiter).queryByText(/noch nicht fertig erfasst/)).toBeNull();
    await user.click(within(zweiter).getByRole("button", { name: "Start abbrechen" }));

    await waitFor(() =>
      expect(aufrufe.find((a) => a.pfad.endsWith("/result/abort"))?.inhalt).toEqual({
        abort_reason: "dnf",
        reason: null,
      }),
    );
    const letzteRohwerte = aufrufe.filter((a) => a.methode === "PUT").at(-1)?.inhalt as {
      raw: Rohwerte;
    };
    expect(letzteRohwerte.raw).toEqual({
      sections: {
        fallscheibe: {
          series: [
            { time_cs: 2000, standing: 0 },
            { status: "aborted_by_shooter", standing: 3 },
          ],
        },
      },
    });
  });

  it("ohne offene Serie läuft das Aufgeben wie bisher", async () => {
    const fertig = { sections: { fallscheibe: { series: [{ time_cs: 2000, standing: 0 }] } } };
    const aufrufe = routen(serverStand(fertig, { seq: 2 }));
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });

    const dialog = await aufgebenWaehlen(user);
    expect(within(dialog).queryByText(/noch nicht fertig erfasst/)).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Start abbrechen" }));
    await waitFor(() =>
      expect(aufrufe.find((a) => a.pfad.endsWith("/result/abort"))?.inhalt).toEqual({
        abort_reason: "dnf",
        reason: null,
      }),
    );
  });

  it("„Trotzdem aufgeben“ bricht mit offener Serie ab; andere Gründe fragen nicht nach Serien", async () => {
    const aufrufe = routen(serverStand(ANGEFANGEN, { seq: 3 }));
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });

    const dialog = await aufgebenWaehlen(user);
    await user.click(within(dialog).getByRole("radio", { name: "Disqualifiziert" }));
    expect(within(dialog).queryByText(/noch nicht fertig erfasst/)).toBeNull();
    await user.click(within(dialog).getByRole("radio", { name: "Aufgegeben" }));
    await user.click(within(dialog).getByRole("button", { name: "Trotzdem aufgeben, ohne Platz" }));
    await waitFor(() =>
      expect(aufrufe.find((a) => a.pfad.endsWith("/result/abort"))?.inhalt).toEqual({
        abort_reason: "dnf",
        reason: null,
      }),
    );
  });

  it("schon aufgegeben mit offener Serie: Hinweis „ohne Platz“ am Start", async () => {
    routen(serverStand(ANGEFANGEN, { seq: 4, status: "aborted", abort_reason: "dnf" }));
    anzeigen();
    expect(await screen.findByText("Ohne Platz in der Rangliste")).toBeInTheDocument();
    expect(screen.getByText(/Serie 2 war beim Aufgeben nicht fertig erfasst/)).toBeInTheDocument();
    expect(screen.getByText(/lässt sich aber nachträglich nicht mehr ändern/)).toBeInTheDocument();
  });

  it("disqualifiziert mit offener Serie: kein Hinweis", async () => {
    routen(serverStand(ANGEFANGEN, { seq: 4, status: "aborted", abort_reason: "dsq" }));
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    expect(screen.queryByText("Ohne Platz in der Rangliste")).toBeNull();
  });
});
