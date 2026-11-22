import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Target } from "lucide-react";
import { beforeEach, describe, expect, it } from "vitest";
import { meldungenLeeren } from "../../components/Meldungen";
import {
  type Aufruf,
  renderAnsicht,
  serverAttrappe,
  type TestAntwort,
} from "../teilnehmer/testhilfe";
import type { ErgebnisStand, Rohwerte } from "./api";
import { ErfassungSeite } from "./ErfassungSeite";
import { FALLSCHEIBE, maske, PRAEZISION, stand, wertung } from "./testdaten";

const T = "78a0a62a-fd80-4ef3-876a-3e7ad7a332b6";
const R = "46c19d4d-52f9-4ff1-956e-32630f067fd0";
const S = "s-1";

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
  ranges: [{ id: R, tournament_id: T, name: "15-m-Stand", lane_count: 2, sort: 0 }],
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
  status: "called",
  abort_reason: null,
  queue_position: null,
  lane: 1,
  heat_id: null,
  heat_number: null,
  heat_starts_at: null,
  called_at: null,
};

/** Antwort des Servers auf Rohwerte: „gerechnet“ wird hier nur zum Schein. */
function gerechnet(raw: Rohwerte, seq: number): ErgebnisStand {
  const serien = ((raw.sections as Record<string, { series?: unknown[] }> | undefined)?.fallscheibe
    ?.series ?? []) as (Record<string, number> | null)[];
  const vollstaendig = serien.filter((s) => s?.time_cs && s.standing !== undefined).length;
  return stand({
    raw,
    seq,
    status: "captured",
    computed: wertung({
      score: "77.70",
      complete: vollstaendig >= 2,
      progress: {
        shots_entered: 0,
        shots_expected: 0,
        series_complete: vollstaendig,
        series_expected: 2,
        section_times_entered: 0,
        section_times_expected: 0,
      },
      steps: ["Serie 1: 12,84 s + 10 s"],
    }),
  });
}

function routen(extra: Record<string, TestAntwort | ((a: Aufruf) => TestAntwort)> = {}) {
  return serverAttrappe({
    "GET /tournaments": { inhalt: [turnier] },
    [`GET /tournaments/${T}/overview`]: { inhalt: uebersicht },
    [`GET /tournaments/${T}/startlist`]: { inhalt: [startZeile] },
    [`GET /tournaments/${T}/entries`]: { inhalt: [] },
    [`GET /tournaments/${T}/results/needs-review`]: { inhalt: [] },
    [`GET /tournaments/${T}/starts/${S}/form`]: { inhalt: maske(FALLSCHEIBE, stand()) },
    [`GET /tournaments/${T}/starts/${S}/events`]: { inhalt: [] },
    [`PUT /tournaments/${T}/starts/${S}/raw`]: (aufruf) => {
      const inhalt = aufruf.inhalt as { raw: Rohwerte; base_seq: number };
      return { inhalt: gerechnet(inhalt.raw, inhalt.base_seq + 1) };
    },
    ...extra,
  });
}

function anzeigen(start: string | undefined = S, art?: "shot" | "series") {
  return renderAnsicht(() => (
    <ErfassungSeite station="erfassung" icon={Target} suche={{ start, art }} onSuche={() => {}} />
  ));
}

/** Auswahlfelder „Ablauf der Serie“. */
function statusFelder() {
  return screen.getAllByRole("combobox", { name: "Ablauf der Serie" });
}

beforeEach(() => {
  // jsdom kennt kein scrollIntoView (Mantine-Auswahl und aktives Feld nutzen es).
  Element.prototype.scrollIntoView = () => {};
  localStorage.clear();
  meldungenLeeren();
});

describe("Erfassungsterminal", () => {
  it("baut die Maske aus der Formularbeschreibung und zeigt den Kopf", async () => {
    routen();
    anzeigen();
    expect(await screen.findByRole("heading", { name: "Markus Brandt" })).toBeInTheDocument();
    expect(screen.getAllByText("4401").length).toBeGreaterThan(0);
    expect(screen.getByText("Start 1 von 2")).toBeInTheDocument();
    expect(statusFelder()).toHaveLength(2);
    expect(screen.getByText("danach Trefferaufnahme")).toBeInTheDocument();
    expect(screen.getByText("gestrichen, zählt nicht")).toBeInTheDocument();
  });

  it("sendet Eingaben als Rohwerte, zeigt die Antwort und schließt ab", async () => {
    const aufrufe = routen({
      [`POST /tournaments/${T}/starts/${S}/finalize`]: (aufruf) => ({
        inhalt: stand({
          ...gerechnet(
            {
              sections: {
                fallscheibe: {
                  series: [
                    { time_cs: 1284, standing: 1 },
                    { time_cs: 1120, standing: 0 },
                  ],
                },
              },
            },
            (aufruf.inhalt as { base_seq: number }).base_seq + 1,
          ),
          status: "final",
          is_final: true,
        }),
      }),
    });
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });

    await user.keyboard("12,84{Enter}1");
    await user.keyboard("11,2{Enter}0");

    await waitFor(
      () => expect(screen.getByRole("button", { name: /Ergebnis abschließen/ })).toBeEnabled(),
      { timeout: 3000 },
    );
    const gesendet = aufrufe.filter((a) => a.methode === "PUT").at(-1);
    expect(gesendet?.inhalt).toEqual({
      raw: {
        sections: {
          fallscheibe: {
            series: [
              { time_cs: 1284, standing: 1 },
              { time_cs: 1120, standing: 0 },
            ],
          },
        },
      },
      base_seq: expect.any(Number),
    });
    expect(screen.getByText("gespeichert")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Ergebnis abschließen/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("77,70 s")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Abschließen" }));
    expect(await screen.findByText("Abgeschlossen: 77,70 s")).toBeInTheDocument();
    expect(aufrufe.some((a) => a.methode === "POST" && a.pfad.endsWith("/finalize"))).toBe(true);
    expect(screen.getByRole("button", { name: "Korrigieren" })).toBeInTheDocument();
  });

  it("Status „Zeitlimit“ sperrt die Zeit und sendet sie nicht", async () => {
    const aufrufe = routen();
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    await user.click(statusFelder()[0] as HTMLElement);
    await user.click(
      (await screen.findAllByRole("option", { name: /Zeitlimit/, hidden: true }))[0] as HTMLElement,
    );
    expect(screen.getAllByRole("button", { name: "Zeit: entfällt" })[0]).toBeDisabled();
    await user.click(document.body);
    await user.keyboard("2");
    await waitFor(
      () =>
        expect(
          aufrufe.some((a) => a.methode === "PUT" && JSON.stringify(a.inhalt).includes("standing")),
        ).toBe(true),
      { timeout: 3000 },
    );
    expect(aufrufe.filter((a) => a.methode === "PUT").at(-1)?.inhalt).toMatchObject({
      raw: { sections: { fallscheibe: { series: [{ status: "time_limit", standing: 2 }] } } },
    });
  });

  it("Netzfehler: Eingabe bleibt, „noch nicht gespeichert“, Abschluss gesperrt", async () => {
    routen({ [`PUT /tournaments/${T}/starts/${S}/raw`]: { status: 503, inhalt: {} } });
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    await user.keyboard("12,84");
    expect(
      await screen.findByText(/Noch nicht gespeichert/, {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Zeit: 12,84/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ergebnis abschließen/ })).toBeDisabled();
  });

  it("409: zeigt den Stand des Servers und fragt, statt zu überschreiben", async () => {
    const fremd = gerechnet(
      { sections: { fallscheibe: { series: [{ time_cs: 1500, standing: 0 }] } } },
      5,
    );
    routen({
      [`PUT /tournaments/${T}/starts/${S}/raw`]: {
        status: 409,
        inhalt: { detail: "veraltet", current: fremd },
      },
    });
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    await user.keyboard("9");
    expect(
      await screen.findByText("Ein anderes Gerät hat diesen Start geändert", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stand des Servers laden" }));
    expect(screen.getByRole("button", { name: /Zeit: 15,00/ })).toBeInTheDocument();
    expect(
      screen.queryByText("Ein anderes Gerät hat diesen Start geändert"),
    ).not.toBeInTheDocument();
  });

  it("Prüffehler des Servers erscheinen am Feld", async () => {
    routen({
      [`PUT /tournaments/${T}/starts/${S}/raw`]: {
        status: 422,
        inhalt: {
          detail: "Eingabe prüfen",
          errors: [
            {
              field: "raw.sections.fallscheibe.series[0].time_cs",
              message: "Serie 1: Zeit zu kurz",
            },
          ],
        },
      },
    });
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    await user.keyboard("1");
    expect(
      await screen.findByText("Serie 1: Zeit zu kurz", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
  });

  it("Einzelschuss: erlaubte Werte als Tasten, „1“ „0“ ergibt 10", async () => {
    const aufrufe = routen({
      [`GET /tournaments/${T}/starts/${S}/form?capture_mode=shot`]: {
        inhalt: maske(PRAEZISION, stand()),
      },
    });
    const user = userEvent.setup();
    anzeigen(S, "shot");
    await screen.findByRole("heading", { name: "Markus Brandt" });
    expect(screen.getByRole("button", { name: /^XInnenzehner$/ })).toBeInTheDocument();
    await user.keyboard("10x");
    await user.click(screen.getByRole("button", { name: "9" }));
    await waitFor(() => expect(aufrufe.some((a) => a.methode === "PUT")).toBe(true), {
      timeout: 3000,
    });
    expect(aufrufe.filter((a) => a.methode === "PUT").at(-1)?.inhalt).toMatchObject({
      raw: { sections: { praezision: { series: [{ shots: [10, "X", 9] }] } } },
    });
  });

  it("zeigt Bahnen am Stand und die Liste „Zu prüfen“", async () => {
    localStorage.setItem("schiesshub.erfassung.stand", JSON.stringify({ [T]: R }));
    routen({
      [`GET /tournaments/${T}/results/needs-review`]: {
        inhalt: [
          {
            start_id: "s-9",
            competition_id: "w",
            competition_name: "Selbstladeflinte",
            start_number: 12,
            display_name: "K. Vogel",
            attempt: 1,
            status: "final",
            review_reason: "Ablauf geändert",
            definition_revision: 2,
          },
        ],
      },
    });
    anzeigen(undefined);
    expect(await screen.findByText("Zu prüfen · 1")).toBeInTheDocument();
    expect(screen.getByText(/Ablauf geändert/)).toBeInTheDocument();
    expect(screen.getByText("Am Stand · 1")).toBeInTheDocument();
    expect(screen.getByText("Bahn frei")).toBeInTheDocument();
  });
});
