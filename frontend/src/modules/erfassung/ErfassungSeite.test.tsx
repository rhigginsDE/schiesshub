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
  // Der Stand des Servers: Rohwerte-Sendungen ändern ihn, die Maske liefert ihn (Prüfansicht).
  let server = stand();
  return serverAttrappe({
    "GET /tournaments": { inhalt: [turnier] },
    [`GET /tournaments/${T}/overview`]: { inhalt: uebersicht },
    [`GET /tournaments/${T}/startlist?names=full`]: { inhalt: [startZeile] },
    [`GET /tournaments/${T}/results/needs-review`]: { inhalt: [] },
    [`GET /tournaments/${T}/starts/${S}/form`]: () => ({ inhalt: maske(FALLSCHEIBE, server) }),
    [`GET /tournaments/${T}/starts/${S}/form?capture_mode=series`]: () => ({
      inhalt: maske(FALLSCHEIBE, server),
    }),
    [`GET /tournaments/${T}/starts/${S}/events`]: { inhalt: [] },
    [`PUT /tournaments/${T}/starts/${S}/raw`]: (aufruf) => {
      const inhalt = aufruf.inhalt as { raw: Rohwerte; base_seq: number };
      server = gerechnet(inhalt.raw, inhalt.base_seq + 1);
      return { inhalt: server };
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
  sessionStorage.clear();
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
    expect(screen.getByText("Gespeichert")).toBeInTheDocument();

    // Prüfansicht: zeigt den Stand des Servers (frisch geladen) mit allen Serien und der Summe.
    await user.click(screen.getByRole("button", { name: /Ergebnis abschließen/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("77,70")).toBeInTheDocument();
    expect(within(dialog).getByText("12,84 s")).toBeInTheDocument();
    expect(within(dialog).getByText("11,20 s")).toBeInTheDocument();
    expect(within(dialog).getByText("Markus Brandt")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Abschließen" }));
    expect(await screen.findByText("Abgeschlossen: 77,70 s")).toBeInTheDocument();
    const abschluss = aufrufe.find((a) => a.methode === "POST" && a.pfad.endsWith("/finalize"));
    // Genau der Stand, den die Prüfansicht gezeigt hat: Sequenz und Ergebnis gehen mit.
    const geprueft = abschluss?.inhalt as { base_seq: number; expected_seq: number };
    expect(geprueft).toEqual({
      base_seq: expect.any(Number),
      expected_seq: geprueft.base_seq,
      expected_score: "77.70",
    });
    expect(screen.getByRole("button", { name: "Korrigieren" })).toBeInTheDocument();
  });

  it("409 beim Abschließen: sagt es in Klartext und lädt die Prüfansicht neu", async () => {
    let server = stand();
    const aufrufe = routen({
      [`PUT /tournaments/${T}/starts/${S}/raw`]: (aufruf) => {
        const inhalt = aufruf.inhalt as { raw: Rohwerte; base_seq: number };
        server = gerechnet(inhalt.raw, inhalt.base_seq + 1);
        return { inhalt: server };
      },
      [`GET /tournaments/${T}/starts/${S}/form?capture_mode=series`]: () => ({
        inhalt: maske(FALLSCHEIBE, server),
      }),
      [`POST /tournaments/${T}/starts/${S}/finalize`]: () => {
        // Inzwischen hat ein anderes Gerät ein anderes Ergebnis erzeugt (gleiche Rohwerte hier).
        server = { ...server, seq: server.seq + 1, computed: wertung({ score: "80.00" }) };
        return {
          status: 409,
          inhalt: { detail: "Das Ergebnis auf dem Server weicht ab.", current: server },
        };
      },
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
    await user.click(screen.getByRole("button", { name: /Ergebnis abschließen/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("77,70")).toBeInTheDocument();
    const formVorher = aufrufe.filter((a) => a.pfad.endsWith("/form?capture_mode=series")).length;
    await user.click(within(dialog).getByRole("button", { name: "Abschließen" }));

    expect(
      await within(dialog).findByText(
        "Die Werte haben sich inzwischen geändert – bitte neu prüfen.",
      ),
    ).toBeInTheDocument();
    expect(await within(dialog).findByText("80,00")).toBeInTheDocument();
    expect(
      aufrufe.filter((a) => a.pfad.endsWith("/form?capture_mode=series")).length,
    ).toBeGreaterThan(formVorher);
    expect(screen.queryByText(/Abgeschlossen:/)).toBeNull();
  });

  it("QA B1: Enter nach dem letzten Feld holt das angetippte Feld nicht zurück", async () => {
    routen();
    const user = userEvent.setup({ delay: null });
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    await user.click(screen.getAllByRole("button", { name: /^Zeit:/ })[0] as HTMLElement);
    await user.keyboard("12,34{Enter}1{Enter}10,5{Enter}0{Enter}");
    // Danach weitertippen: Es darf nichts überschrieben werden.
    await user.keyboard("2,00{Enter}");
    const zeiten = screen.getAllByRole("button", { name: /^Zeit:/ });
    const stehend = screen.getAllByRole("button", { name: /^Stehende Scheiben:/ });
    expect(zeiten[0]).toHaveAccessibleName("Zeit: 12,34 s");
    expect(stehend[0]).toHaveAccessibleName("Stehende Scheiben: 1, 0 bis 5");
    expect(zeiten[1]).toHaveAccessibleName("Zeit: 10,50 s");
    expect(stehend[1]).toHaveAccessibleName("Stehende Scheiben: 0, 0 bis 5");
    expect(screen.getByText("Kein Feld aktiv. Feld antippen.")).toBeInTheDocument();
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
      await screen.findByText(/Nicht gespeichert – keine Verbindung/, {}, { timeout: 3000 }),
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

  it("Warnung des Servers: Abschließen erst nach ausdrücklicher Bestätigung", async () => {
    // Über dem Zeitlimit, aber unter der Plausibilitätsgrenze: nur eine Warnung des Servers.
    const warnung = "Serie 1: 70,00 s liegt über dem Zeitlimit von 60 s.";
    let letzter = stand();
    const mitWarnung = (raw: Rohwerte, seq: number): ErgebnisStand => {
      const antwort = gerechnet(raw, seq);
      return {
        ...antwort,
        computed: antwort.computed && {
          ...antwort.computed,
          warnings: [{ path: "sections.fallscheibe.series[0].time_cs", message: warnung }],
        },
      };
    };
    routen({
      [`PUT /tournaments/${T}/starts/${S}/raw`]: (aufruf) => {
        const inhalt = aufruf.inhalt as { raw: Rohwerte; base_seq: number };
        letzter = mitWarnung(inhalt.raw, inhalt.base_seq + 1);
        return { inhalt: letzter };
      },
      [`GET /tournaments/${T}/starts/${S}/form?capture_mode=series`]: () => ({
        inhalt: maske(FALLSCHEIBE, letzter),
      }),
    });
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    await user.keyboard("70{Enter}0");
    await user.keyboard("11,2{Enter}0");
    await waitFor(
      () => expect(screen.getByRole("button", { name: /Ergebnis abschließen/ })).toBeEnabled(),
      { timeout: 3000 },
    );
    await user.click(screen.getByRole("button", { name: /Ergebnis abschließen/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(warnung)).toBeInTheDocument();
    const abschliessen = within(dialog).getByRole("button", { name: "Abschließen" });
    expect(abschliessen).toBeDisabled();
    await user.click(within(dialog).getByRole("checkbox", { name: /Sie stimmen/ }));
    expect(abschliessen).toBeEnabled();
  });

  it("Zeit über der Grenze der Formularbeschreibung: Fehler am Feld schon bei der Eingabe", async () => {
    routen({
      [`PUT /tournaments/${T}/starts/${S}/raw`]: {
        status: 422,
        inhalt: {
          detail: "Zeit nicht plausibel",
          errors: [{ field: "raw.sections.fallscheibe.series[0].time_cs", message: "zu groß" }],
        },
      },
    });
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    await user.keyboard("200");
    expect(
      await screen.findByText(
        "Diese Zeit ist nicht plausibel: höchstens 180,00 s. Bitte mit dem Startzettel vergleichen.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("zu groß")).toBeNull();
    expect(screen.getByRole("button", { name: /Ergebnis abschließen/ })).toBeDisabled();
  });

  it("Prüfansicht: weicht der Server von der Eingabe ab, geht es nur zurück", async () => {
    // Gestellter Fehlerfall: gleiche Sequenznummer, aber andere Werte beim Server.
    let seq = 0;
    routen({
      [`PUT /tournaments/${T}/starts/${S}/raw`]: (aufruf) => {
        const inhalt = aufruf.inhalt as { raw: Rohwerte; base_seq: number };
        seq = inhalt.base_seq + 1;
        return { inhalt: gerechnet(inhalt.raw, seq) };
      },
      [`GET /tournaments/${T}/starts/${S}/form?capture_mode=series`]: () => ({
        inhalt: maske(
          FALLSCHEIBE,
          gerechnet(
            {
              sections: {
                fallscheibe: {
                  series: [
                    { time_cs: 1284, standing: 1 },
                    { time_cs: 1070, standing: 0 },
                  ],
                },
              },
            },
            seq,
          ),
        ),
      }),
    });
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    await user.keyboard("12,84{Enter}1");
    await user.keyboard("10,5{Enter}0");
    await waitFor(
      () => expect(screen.getByRole("button", { name: /Ergebnis abschließen/ })).toBeEnabled(),
      { timeout: 3000 },
    );
    await user.click(screen.getByRole("button", { name: /Ergebnis abschließen/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/Beim Server steht etwas anderes/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Abschließen" })).toBeDisabled();
  });

  it("Startnummer mit mehreren Starts öffnet nicht den ersten, sondern zeigt die Auswahl", async () => {
    routen({
      [`GET /tournaments/${T}/startlist?names=full`]: {
        inhalt: [
          startZeile,
          {
            ...startZeile,
            start_id: "s-2",
            competition_id: "w2",
            competition_name: "Selbstladeflinte, Zielfernrohr",
          },
        ],
      },
    });
    const gewaehlt: unknown[] = [];
    const user = userEvent.setup();
    renderAnsicht(() => (
      <ErfassungSeite
        station="erfassung"
        icon={Target}
        suche={{}}
        onSuche={(neu) => gewaehlt.push(neu)}
      />
    ));
    const feld = await screen.findByRole("searchbox", { name: "Startnummer oder Name suchen" });
    await user.type(feld, "7{Enter}");
    expect(await screen.findByText(/2 Starts passen/)).toBeInTheDocument();
    expect(gewaehlt).toEqual([]);
    await user.click(screen.getByRole("button", { name: /Zielfernrohr/ }));
    expect(gewaehlt).toEqual([{ start: "s-2", art: undefined }]);
  });

  it("Korrektur: zeigt das neue Ergebnis aus der Vorschau des Servers vor dem Speichern", async () => {
    const raw = {
      sections: {
        fallscheibe: {
          series: [
            { time_cs: 1234, standing: 0 },
            { time_cs: 1520, standing: 1 },
          ],
        },
      },
    };
    const fertig = stand({
      status: "final",
      is_final: true,
      seq: 3,
      raw,
      score: "82.00",
      computed: wertung({ score: "82.00", complete: true }),
    });
    const aufrufe = routen({
      [`GET /tournaments/${T}/starts/${S}/form?capture_mode=series`]: {
        inhalt: maske(FALLSCHEIBE, fertig),
      },
      [`GET /tournaments/${T}/starts/${S}/form`]: { inhalt: maske(FALLSCHEIBE, fertig) },
      [`POST /tournaments/${T}/starts/${S}/preview`]: {
        inhalt: {
          start_id: S,
          status: "final",
          seq: 3,
          definition_revision: 1,
          valid: true,
          errors: [],
          complete: true,
          finalize_errors: [],
          computed: wertung({ score: "72.00", complete: true }),
          score: "72.00",
        },
      },
    });
    const user = userEvent.setup();
    anzeigen();
    await user.click(await screen.findByRole("button", { name: /Korrigieren/ }));
    await user.click(
      screen.getAllByRole("button", { name: /Stehende Scheiben/ })[1] as HTMLElement,
    );
    await user.keyboard("0");
    expect(
      await screen.findByText(
        /Neues Ergebnis, noch nicht gespeichert · bisher 82,00 s/,
        {},
        {
          timeout: 3000,
        },
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("72,00")).toBeInTheDocument();
    const vorschau = aufrufe.find((a) => a.pfad.endsWith("/preview"));
    expect(vorschau?.inhalt).toMatchObject({
      raw: { sections: { fallscheibe: { series: [{ standing: 0 }, { standing: 0 }] } } },
    });
    // Gespeichert wird nichts ohne Grund.
    expect(aufrufe.some((a) => a.methode === "PUT" || a.pfad.endsWith("/correct"))).toBe(false);
  });

  it("ein anderer Start beginnt mit der Erfassungsart seines Wettbewerbs", async () => {
    routen();
    const gewaehlt: Record<string, unknown>[] = [];
    const user = userEvent.setup();
    renderAnsicht(() => (
      <ErfassungSeite
        station="erfassung"
        icon={Target}
        suche={{ art: "shot" }}
        onSuche={(neu) => gewaehlt.push({ ...neu })}
      />
    ));
    const feld = await screen.findByRole("searchbox", { name: "Startnummer oder Name suchen" });
    await user.type(feld, "7{Enter}");
    await waitFor(() => expect(gewaehlt).toHaveLength(1));
    expect(gewaehlt[0]).toEqual({ start: S });
    expect(gewaehlt[0]).not.toHaveProperty("art");
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

  it("zeigt am Stand den vollen Namen aus der Startliste (names=full), ohne die Anmeldungen zu laden", async () => {
    localStorage.setItem("schiesshub.erfassung.stand", JSON.stringify({ [T]: R }));
    const aufrufe = routen({
      [`GET /tournaments/${T}/startlist?names=full`]: {
        inhalt: [{ ...startZeile, full_name: "Markus Brandt", full_club: "SV Tell" }],
      },
    });
    anzeigen(undefined);
    expect(await screen.findByText("Am Stand · 1")).toBeInTheDocument();
    expect(screen.getAllByText("Markus Brandt").length).toBeGreaterThan(0);
    expect(screen.queryByText("M. Brandt")).toBeNull();
    expect(aufrufe.some((a) => a.pfad.includes("/entries"))).toBe(false);
  });
});
