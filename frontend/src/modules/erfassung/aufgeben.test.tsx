import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Target } from "lucide-react";
import { beforeEach, describe, expect, it } from "vitest";
import { meldungenLeeren } from "../../components/Meldungen";
import { renderAnsicht, serverAttrappe, type TestAntwort } from "../teilnehmer/testhilfe";
import type {
  AbschnittWertung,
  AufgebenAuskunft,
  ErgebnisStand,
  Rohwerte,
  SerienWertung,
} from "./api";
import {
  aufzaehlung,
  gemeinsamerStatus,
  nurWerteFehlen,
  offeneJeAbschnitt,
  serienDerAuskunft,
} from "./aufgeben";
import { ErfassungSeite } from "./ErfassungSeite";
import { FALLSCHEIBE, maske, stand, wertung } from "./testdaten";

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

/**
 * Vorabauskunft wie beim Server (`abort_preview.py`), für diese Testdaten nachgestellt:
 * `open_series_items` nennt alle gewerteten Serien, die nicht fertig sind (angefangen oder nicht
 * geschossen); angefangen ohne Status ist `incomplete_series`, mit Status und fehlenden Werten
 * `missing_values`. Beim abgebrochenen Start dieselbe Rechnung, `dns`/`dsq` ohne Platz.
 */
function auskunftFuer(stand: ErgebnisStand): AufgebenAuskunft | null {
  if (stand.status === "final") return null;
  const abgebrochen = stand.status === "aborted";
  const serien = stand.computed?.sections[0]?.series ?? [];
  const offen = serien.filter((x) => !x.struck && !x.complete);
  const nummern = offen.map((x) => x.number);
  const pfad = (x: SerienWertung) => `sections.fallscheibe.series[${x.number - 1}]`;
  const basis = {
    open_series: nummern,
    open_series_items: offen.map((x) => ({
      section_id: "fallscheibe",
      section_name: "Fallscheibe",
      series: x.number,
      path: pfad(x),
      state: x.captured ? ("started" as const) : ("not_shot" as const),
    })),
    missing_fields: [],
    score_text: null,
  };
  if (abgebrochen && stand.abort_reason === "dns") {
    return {
      ...basis,
      would_place: false,
      reason_code: "not_started",
      message_de: "Nicht angetreten: ohne Platz.",
    };
  }
  if (abgebrochen && stand.abort_reason === "dsq") {
    return {
      ...basis,
      would_place: false,
      reason_code: "disqualified",
      message_de: "Disqualifiziert: ohne Platz.",
    };
  }
  if (!serien.some((x) => x.captured)) {
    return {
      ...basis,
      would_place: false,
      reason_code: "no_values",
      message_de: "Noch kein Wertungsschuss erfasst: Abbruch (AB) ohne Platz.",
    };
  }
  const ohneStatus = offen.filter((x) => x.captured && x.status === "normal");
  const mitStatus = offen.filter((x) => x.captured && x.status !== "normal");
  if (ohneStatus.length > 0) {
    return {
      ...basis,
      would_place: false,
      reason_code: "incomplete_series",
      message_de: "Serie 2 ist unvollständig erfasst – Text des Servers.",
    };
  }
  if (mitStatus.length > 0) {
    return {
      ...basis,
      would_place: false,
      reason_code: "missing_values",
      // Form wie beim Server: die fehlenden Werte und die Folge in einem Text.
      message_de: `Es fehlen noch: ${mitStatus
        .map((x) => `Serie ${x.number} (Stehende Scheiben)`)
        .join(" und ")}. Ohne diese Werte bleibt der Start ohne Platz.`,
      missing_fields: mitStatus.map((x) => ({
        path: pfad(x),
        key: "standing",
        label: "Stehende Scheiben",
      })),
    };
  }
  return {
    ...basis,
    would_place: true,
    reason_code: "placed",
    message_de: abgebrochen
      ? "Abbruch (AB): kommt nach dem bisherigen Ergebnis in die Rangliste (20,00 s)."
      : "Würde nach dem bisherigen Ergebnis platziert (20,00 s).",
    score_text: "20,00 s",
  };
}

function serverStand(raw: Rohwerte, teil: Partial<ErgebnisStand> = {}): ErgebnisStand {
  return stand({ raw, status: "captured", computed: fallscheibeWertung(raw), ...teil });
}

// Serie 1 fertig, Serie 2 angefangen: nur die Zeit ist erfasst.
const ANGEFANGEN: Rohwerte = {
  sections: { fallscheibe: { series: [{ time_cs: 2000, standing: 0 }, { time_cs: 1500 }] } },
};

const AUSKUNFT_OFFEN: AufgebenAuskunft = {
  would_place: false,
  reason_code: "incomplete_series",
  message_de: "…",
  open_series: [2, 3],
  score_text: null,
  open_series_items: [
    {
      section_id: "fallscheibe",
      section_name: "Fallscheibe",
      series: 2,
      path: "sections.fallscheibe.series[1]",
      state: "started",
    },
    {
      section_id: "fallscheibe",
      section_name: "Fallscheibe",
      series: 3,
      path: "sections.fallscheibe.series[2]",
      state: "not_shot",
    },
  ],
  missing_fields: [],
};

describe("Serien zur Vorabauskunft", () => {
  it("nimmt die angefangenen Serien des Servers (nicht geschossene nicht)", () => {
    const liste = serienDerAuskunft(FALLSCHEIBE, fallscheibeWertung(ANGEFANGEN), AUSKUNFT_OFFEN);
    expect(liste.map((o) => o.ort)).toEqual(["Serie 2"]);
    expect(liste[0]?.abbruchStatus).toBe("Abbruch durch den Schützen");
    expect(liste[0]?.statusGesetzt).toBe(false);
    expect(gemeinsamerStatus(liste)).toBe("Abbruch durch den Schützen");
  });

  it("rechnet keine Regel nach: Serien nur bei „incomplete_series“ und „missing_values“", () => {
    const wertungAngefangen = fallscheibeWertung(ANGEFANGEN);
    for (const reason_code of [
      "placed",
      "no_values",
      "no_rule",
      "invalid",
      "not_started",
      "disqualified",
    ] as const) {
      expect(
        serienDerAuskunft(FALLSCHEIBE, wertungAngefangen, { ...AUSKUNFT_OFFEN, reason_code }),
      ).toEqual([]);
    }
    expect(serienDerAuskunft(FALLSCHEIBE, wertungAngefangen, null)).toEqual([]);
    // Nennt der Server die Serie nicht als angefangen, ist sie auch nicht offen.
    expect(
      serienDerAuskunft(FALLSCHEIBE, wertungAngefangen, {
        ...AUSKUNFT_OFFEN,
        open_series_items: AUSKUNFT_OFFEN.open_series_items.slice(1),
      }),
    ).toEqual([]);
  });

  it("fehlende Werte bei gesetztem Status: Serie und Feld aus `missing_fields`", () => {
    const gesetzt: Rohwerte = {
      sections: {
        fallscheibe: { series: [{ time_cs: 1200, standing: 0 }, { status: "aborted_by_shooter" }] },
      },
    };
    const liste = serienDerAuskunft(FALLSCHEIBE, fallscheibeWertung(gesetzt), {
      ...AUSKUNFT_OFFEN,
      reason_code: "missing_values",
      missing_fields: [
        { path: "sections.fallscheibe.series[1]", key: "standing", label: "Stehende Scheiben" },
      ],
    });
    expect(liste.map((o) => o.ort)).toEqual(["Serie 2"]);
    expect(liste[0]?.fehlend).toEqual(["standing"]);
    expect(nurWerteFehlen(liste)).toBe(true);
    expect(
      nurWerteFehlen(
        serienDerAuskunft(FALLSCHEIBE, fallscheibeWertung(ANGEFANGEN), AUSKUNFT_OFFEN),
      ),
    ).toBe(false);
  });

  it("offene Serien je Abschnitt: angefangen und nicht geschossen getrennt", () => {
    expect(offeneJeAbschnitt(null)).toEqual([]);
    expect(offeneJeAbschnitt(AUSKUNFT_OFFEN)).toEqual([
      {
        abschnittId: "fallscheibe",
        name: "Fallscheibe",
        angefangen: [{ nummer: 2, pfad: "sections.fallscheibe.series.1" }],
        nichtGeschossen: [{ nummer: 3, pfad: "sections.fallscheibe.series.2" }],
      },
    ]);
    expect(aufzaehlung(["1", "2", "4"], "und")).toBe("1, 2 und 4");
    expect(gemeinsamerStatus([])).toBeNull();
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

function routen(
  anfang: ErgebnisStand,
  extra: Record<string, TestAntwort | ((a: { inhalt: unknown }) => TestAntwort)> = {},
) {
  let server = anfang;
  const form = () => ({
    inhalt: { ...maske(FALLSCHEIBE, server), abort_preview: auskunftFuer(server) },
  });
  return serverAttrappe({
    "GET /tournaments": { inhalt: [turnier] },
    [`GET /tournaments/${T}/overview`]: { inhalt: uebersicht },
    [`GET /tournaments/${T}/startlist?names=full`]: { inhalt: [startZeile] },
    [`GET /tournaments/${T}/results/needs-review`]: { inhalt: [] },
    [`GET /tournaments/${T}/starts/${S}/form`]: form,
    [`GET /tournaments/${T}/starts/${S}/form?capture_mode=series`]: form,
    [`GET /tournaments/${T}/starts/${S}/events`]: { inhalt: [] },
    [`POST /tournaments/${T}/starts/${S}/preview`]: (aufruf) => {
      const roh = (aufruf.inhalt as { raw: Rohwerte }).raw;
      const probe = serverStand(roh, { seq: server.seq, status: server.status });
      return { inhalt: { computed: probe.computed, abort_preview: auskunftFuer(probe) } };
    },
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
    [`POST /tournaments/${T}/starts/${S}/correct`]: (aufruf) => {
      const inhalt = aufruf.inhalt as { raw: Rohwerte; base_seq: number };
      server = serverStand(inhalt.raw, {
        seq: inhalt.base_seq + 1,
        status: "aborted",
        abort_reason: server.abort_reason,
      });
      return { inhalt: server };
    },
    [`POST /tournaments/${T}/starts/${S}/result/undo-abort`]: (aufruf) => {
      const inhalt = aufruf.inhalt as { base_seq: number };
      server = { ...server, status: "captured", abort_reason: null, seq: inhalt.base_seq + 1 };
      return { inhalt: server };
    },
    ...extra,
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

describe("Aufgeben in der Erfassung (Vorabauskunft)", () => {
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

    // Kein Abbruch, sondern der Status an der Serie. Die erfasste Zeit bleibt (nicht gewertet).
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(
      () =>
        expect(aufrufe.filter((a) => a.methode === "PUT").at(-1)?.inhalt).toEqual({
          raw: {
            sections: {
              fallscheibe: {
                series: [
                  { time_cs: 2000, standing: 0 },
                  { status: "aborted_by_shooter", time_cs: 1500 },
                ],
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
    expect(
      screen.getByRole("button", { name: "Zeit: 15,00 s, wird nicht gewertet" }),
    ).toBeEnabled();

    // Das aktive Feld ist „Stehende Scheiben“ von Serie 2: eine Ziffer genügt.
    await user.keyboard("3");
    await waitFor(
      () => expect(screen.getByRole("button", { name: "Jetzt aufgeben" })).toBeEnabled(),
      { timeout: 3000 },
    );
    await user.click(screen.getByRole("button", { name: "Jetzt aufgeben" }));
    const zweiter = await screen.findByRole("dialog");
    expect(within(zweiter).getByRole("radio", { name: "Aufgegeben" })).toBeChecked();
    // Jetzt sagt die Auskunft des Servers: gewertet, mit dem Ergebnis.
    expect(
      await within(zweiter).findByText(
        "Markus Brandt wird mit dem bisherigen Ergebnis gewertet: 20,00 s.",
      ),
    ).toBeInTheDocument();
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
            { status: "aborted_by_shooter", time_cs: 1500, standing: 3 },
          ],
        },
      },
    });
  });

  it("würde platziert: Rückfrage nennt das Ergebnis des Servers", async () => {
    const fertig = { sections: { fallscheibe: { series: [{ time_cs: 2000, standing: 0 }] } } };
    const aufrufe = routen(serverStand(fertig, { seq: 2 }));
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });

    const dialog = await aufgebenWaehlen(user);
    expect(
      within(dialog).getByText("Markus Brandt wird mit dem bisherigen Ergebnis gewertet: 20,00 s."),
    ).toBeInTheDocument();
    expect(within(dialog).queryByText(/noch nicht fertig erfasst/)).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Start abbrechen" }));
    await waitFor(() =>
      expect(aufrufe.find((a) => a.pfad.endsWith("/result/abort"))?.inhalt).toEqual({
        abort_reason: "dnf",
        reason: null,
      }),
    );
  });

  it("ohne Wertungsschuss: eigener Klartext, ohne Platz; abbrechen geht direkt", async () => {
    const aufrufe = routen(serverStand({}, { seq: 0, status: "called" }));
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });

    const dialog = await aufgebenWaehlen(user);
    expect(
      within(dialog).getByText("Markus Brandt stünde ohne Platz in der Rangliste."),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/Es ist noch kein Wertungsschuss erfasst/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Start abbrechen" }));
    await waitFor(() => expect(aufrufe.some((a) => a.pfad.endsWith("/result/abort"))).toBe(true));
  });

  it("unbekannter Fall (Serie laut Server offen, aber keine angefangen): Text des Servers", async () => {
    const fertig = { sections: { fallscheibe: { series: [{ time_cs: 2000, standing: 0 }] } } };
    routen(serverStand(fertig, { seq: 2 }), {
      [`GET /tournaments/${T}/starts/${S}/form`]: {
        inhalt: {
          ...maske(FALLSCHEIBE, serverStand(fertig, { seq: 2 })),
          abort_preview: {
            ...AUSKUNFT_OFFEN,
            open_series: [2],
            open_series_items: [],
            message_de: "Präzision · Serie 2 ist unvollständig erfasst.",
          },
        },
      },
    });
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    const dialog = await aufgebenWaehlen(user);
    expect(
      within(dialog).getByText("Präzision · Serie 2 ist unvollständig erfasst."),
    ).toBeInTheDocument();
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
});

describe("Offene Serien und fehlende Werte (Vorabauskunft)", () => {
  // Serie 1 fertig, Serie 2 mit „Abbruch durch den Schützen“, aber ohne stehende Scheiben.
  const STATUS_OHNE_WERT: Rohwerte = {
    sections: {
      fallscheibe: {
        series: [
          { time_cs: 2000, standing: 0 },
          { status: "aborted_by_shooter", time_cs: 1500 },
        ],
      },
    },
  };

  it("fehlende Werte: Text des Servers, und ein Tipp führt zum fehlenden Feld", async () => {
    const aufrufe = routen(serverStand(STATUS_OHNE_WERT, { seq: 3 }));
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });

    const dialog = await aufgebenWaehlen(user);
    expect(within(dialog).getByText("Serie 2 ist noch nicht fertig erfasst.")).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "Es fehlen noch: Serie 2 (Stehende Scheiben). Ohne diese Werte bleibt der Start ohne Platz.",
      ),
    ).toBeInTheDocument();
    // Die Folge sagt der Text des Servers schon; kein zweites „ohne Platz“.
    expect(within(dialog).queryByText(/Gibst du jetzt trotzdem auf/)).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Zum fehlenden Feld" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // Das aktive Feld: stehende Scheiben in Serie 2 (nicht die nicht gewertete Zeit).
    expect(screen.getByText("Serie 2 · Stehende Scheiben")).toBeInTheDocument();
    await user.keyboard("2");
    await waitFor(
      () =>
        expect(aufrufe.filter((a) => a.methode === "PUT").at(-1)?.inhalt).toMatchObject({
          raw: {
            sections: {
              fallscheibe: {
                series: [
                  { time_cs: 2000, standing: 0 },
                  { status: "aborted_by_shooter", time_cs: 1500, standing: 2 },
                ],
              },
            },
          },
        }),
      { timeout: 3000 },
    );
    await waitFor(
      () => expect(screen.getByRole("button", { name: "Jetzt aufgeben" })).toBeEnabled(),
      { timeout: 3000 },
    );
  });

  it("nennt offene Serien: angefangen mit Sprung zur Serie, nicht geschossen ohne", async () => {
    routen(serverStand(ANGEFANGEN, { seq: 3 }));
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    const dialog = await aufgebenWaehlen(user);
    expect(within(dialog).getByText("Offene Serien")).toBeInTheDocument();
    expect(within(dialog).getByText("Serie 2 angefangen")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Zu Serie 2" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByText("Serie 2 · Stehende Scheiben")).toBeInTheDocument();
  });

  it("würde platziert: nicht geschossene Serien stehen dabei, ohne Sprung", async () => {
    const fertig = { sections: { fallscheibe: { series: [{ time_cs: 2000, standing: 0 }] } } };
    routen(serverStand(fertig, { seq: 2 }));
    const user = userEvent.setup();
    anzeigen();
    await screen.findByRole("heading", { name: "Markus Brandt" });
    const dialog = await aufgebenWaehlen(user);
    expect(within(dialog).getByText("Serie 2 noch nicht geschossen")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /^Zu Serie/ })).toBeNull();
  });
});

describe("Abgebrochener Start: Auskunft des Servers", () => {
  const FERTIG: Rohwerte = {
    sections: {
      fallscheibe: {
        series: [
          { time_cs: 2000, standing: 0 },
          { time_cs: 1500, standing: 1 },
        ],
      },
    },
  };

  it("aufgegeben mit Platz: Text des Servers, Knöpfe gleich da, keine Abfrage der Rangliste", async () => {
    const aufrufe = routen(serverStand(FERTIG, { seq: 5, status: "aborted", abort_reason: "dnf" }));
    anzeigen();
    expect(
      await screen.findByText(
        "Abbruch (AB): kommt nach dem bisherigen Ergebnis in die Rangliste (20,00 s).",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abbruch zurücknehmen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Korrigieren" })).toBeInTheDocument();
    expect(screen.queryByText("Ohne Platz in der Rangliste")).toBeNull();
    expect(aufrufe.some((a) => a.pfad.includes("/ranking"))).toBe(false);
  });

  it("disqualifiziert: Text des Servers, kein Hinweis „ohne Platz“", async () => {
    routen(serverStand(FERTIG, { seq: 5, status: "aborted", abort_reason: "dsq" }));
    anzeigen();
    expect(await screen.findByText("Disqualifiziert: ohne Platz.")).toBeInTheDocument();
    expect(screen.queryByText("Ohne Platz in der Rangliste")).toBeNull();
  });

  it("ohne Platz: Sprung zur angefangenen Serie beginnt eine Korrektur", async () => {
    routen(serverStand(ANGEFANGEN, { seq: 4, status: "aborted", abort_reason: "dnf" }));
    const user = userEvent.setup();
    anzeigen();
    const hinweis = (await screen.findByText("Ohne Platz in der Rangliste")).closest("div");
    if (!hinweis) throw new Error("Hinweis fehlt");
    expect(within(hinweis).getByText("Serie 2 angefangen")).toBeInTheDocument();
    await user.click(within(hinweis).getByRole("button", { name: "Zu Serie 2" }));
    expect(await screen.findByText(/Der Start bleibt abgebrochen/)).toBeInTheDocument();
    expect(screen.getByText("Serie 2 · Stehende Scheiben")).toBeInTheDocument();
  });
});

describe("Aufgegeben ohne Platz", () => {
  it("nennt den Grund des Servers und trägt den Serienstatus als Korrektur nach", async () => {
    const aufrufe = routen(
      serverStand(ANGEFANGEN, { seq: 4, status: "aborted", abort_reason: "dnf" }),
    );
    const user = userEvent.setup();
    anzeigen();
    expect(await screen.findByText("Ohne Platz in der Rangliste")).toBeInTheDocument();
    expect(
      screen.getByText("Serie 2 ist unvollständig erfasst – Text des Servers."),
    ).toBeInTheDocument();
    // Ohne Abfrage der Rangliste: Die Auskunft kommt mit der Maske.
    expect(aufrufe.some((a) => a.pfad.includes("/ranking"))).toBe(false);
    expect(screen.getByText(/Serienstatus nachtragen: Trag für Serie 2/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abbruch zurücknehmen" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Serienstatus nachtragen" }));
    // Korrektur mit vorbelegtem Status; nichts wird von selbst gesendet.
    expect(await screen.findByText(/Der Start bleibt abgebrochen/)).toBeInTheDocument();
    expect(screen.queryByText("Ohne Platz in der Rangliste")).toBeNull();
    await user.keyboard("3");
    await user.click(screen.getByRole("button", { name: "Korrektur speichern" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox"), "Abbruch durch den Schützen nachgetragen");
    await user.click(within(dialog).getByRole("button", { name: "Korrektur speichern" }));

    await waitFor(() =>
      expect(aufrufe.find((a) => a.pfad.endsWith("/correct"))?.inhalt).toEqual({
        raw: {
          sections: {
            fallscheibe: {
              series: [
                { time_cs: 2000, standing: 0 },
                { status: "aborted_by_shooter", time_cs: 1500, standing: 3 },
              ],
            },
          },
        },
        reason: "Abbruch durch den Schützen nachgetragen",
        base_seq: 4,
      }),
    );
    expect(aufrufe.some((a) => a.methode === "PUT")).toBe(false);
  });

  it("nimmt den Abbruch mit Pflichtgrund zurück und sagt, was danach gilt", async () => {
    const aufrufe = routen(
      serverStand(ANGEFANGEN, { seq: 4, status: "aborted", abort_reason: "dnf" }),
    );
    const user = userEvent.setup();
    anzeigen();
    // Ohne Platz stehen beide Wege im Hinweis.
    const hinweis = (await screen.findByText("Ohne Platz in der Rangliste")).closest("div");
    if (!hinweis) throw new Error("Hinweis fehlt");
    await user.click(within(hinweis).getByRole("button", { name: "Abbruch zurücknehmen" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/„Aufgegeben“ wird zurückgenommen/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Der Start ist wieder in Erfassung/)).toBeInTheDocument();
    expect(within(dialog).getByText(/ruf ihn am Schießstand neu auf/)).toBeInTheDocument();
    const knopf = within(dialog).getByRole("button", { name: "Abbruch zurücknehmen" });
    expect(knopf).toBeDisabled();
    await user.type(within(dialog).getByRole("textbox"), "Schütze schießt weiter");
    await user.click(knopf);

    await waitFor(() =>
      expect(aufrufe.find((a) => a.pfad.endsWith("/undo-abort"))?.inhalt).toEqual({
        reason: "Schütze schießt weiter",
        base_seq: 4,
      }),
    );
    // Wieder offen: abschließen und abbrechen stehen wieder da.
    expect(await screen.findByRole("button", { name: "Ergebnis abschließen" })).toBeInTheDocument();
  });

  it("409 beim Zurücknehmen: Klartext statt Fehlercode", async () => {
    routen(serverStand(ANGEFANGEN, { seq: 4, status: "aborted", abort_reason: "dsq" }), {
      [`POST /tournaments/${T}/starts/${S}/result/undo-abort`]: {
        status: 409,
        inhalt: { detail: "Zurücknehmen lässt sich nur der Abbruch eines abgebrochenen Starts." },
      },
    });
    const user = userEvent.setup();
    anzeigen();
    // Disqualifiziert: kein Hinweis „ohne Platz“, aber zurücknehmen und korrigieren gehen.
    await user.click(await screen.findByRole("button", { name: "Abbruch zurücknehmen" }));
    expect(screen.queryByText("Ohne Platz in der Rangliste")).toBeNull();
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox"), "Irrtum");
    await user.click(within(dialog).getByRole("button", { name: "Abbruch zurücknehmen" }));
    expect(
      await within(dialog).findByText(/Der Start ist nicht mehr abgebrochen/),
    ).toBeInTheDocument();
  });
});
