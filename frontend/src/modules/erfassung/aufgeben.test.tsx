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
  RanglistenZeile,
  Rohwerte,
  SerienWertung,
} from "./api";
import {
  gemeinsamerStatus,
  nurWerteFehlen,
  offeneSerien,
  orteText,
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
 * Vorabauskunft wie beim Server (`abort_preview.py`), für diese Testdaten nachgestellt: `open_series`
 * nennt alle gewerteten Serien, die nicht fertig sind (auch nicht geschossene).
 */
function auskunftFuer(stand: ErgebnisStand): AufgebenAuskunft | null {
  if (stand.status === "final" || stand.status === "aborted") return null;
  const serien = stand.computed?.sections[0]?.series ?? [];
  const offen = serien.filter((x) => !x.struck && !x.complete);
  const nummern = offen.map((x) => x.number);
  if (!serien.some((x) => x.captured)) {
    return {
      would_place: false,
      reason_code: "no_values",
      message_de: "Noch kein Wertungsschuss erfasst: Abbruch ohne Platz.",
      open_series: nummern,
      score_text: null,
    };
  }
  if (offen.some((x) => x.captured)) {
    return {
      would_place: false,
      reason_code: "incomplete_series",
      message_de: "Serie 2 ist unvollständig erfasst – Text des Servers.",
      open_series: nummern,
      score_text: null,
    };
  }
  return {
    would_place: true,
    reason_code: "placed",
    message_de: "Würde nach dem bisherigen Ergebnis platziert (20,00 s).",
    open_series: nummern,
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
};

describe("Serien zur Vorabauskunft", () => {
  it("nimmt die offenen Serien des Servers, soweit angefangen (nicht geschossene nicht)", () => {
    const liste = serienDerAuskunft(FALLSCHEIBE, fallscheibeWertung(ANGEFANGEN), AUSKUNFT_OFFEN);
    expect(liste.map((o) => o.ort)).toEqual(["Serie 2"]);
    expect(liste[0]?.abbruchStatus).toBe("Abbruch durch den Schützen");
    expect(gemeinsamerStatus(liste)).toBe("Abbruch durch den Schützen");
  });

  it("rechnet keine Regel nach: Nur bei „incomplete_series“ gibt es Serien", () => {
    const wertungAngefangen = fallscheibeWertung(ANGEFANGEN);
    for (const reason_code of ["placed", "no_values", "no_rule", "invalid"] as const) {
      expect(
        serienDerAuskunft(FALLSCHEIBE, wertungAngefangen, { ...AUSKUNFT_OFFEN, reason_code }),
      ).toEqual([]);
    }
    expect(serienDerAuskunft(FALLSCHEIBE, wertungAngefangen, null)).toEqual([]);
    // Nennt der Server die Serie nicht, ist sie auch nicht offen.
    expect(
      serienDerAuskunft(FALLSCHEIBE, wertungAngefangen, { ...AUSKUNFT_OFFEN, open_series: [3] }),
    ).toEqual([]);
  });

  it("offeneSerien ohne Nummern: angefangen und nicht fertig laut Wertung; Orte als Aufzählung", () => {
    expect(offeneSerien(FALLSCHEIBE, null)).toEqual([]);
    const o = offeneSerien(FALLSCHEIBE, fallscheibeWertung(ANGEFANGEN));
    expect(o.map((x) => x.ort)).toEqual(["Serie 2"]);
    expect(orteText([...o, ...o, ...o], "und")).toBe("Serie 2, Serie 2 und Serie 2");
    expect(gemeinsamerStatus([])).toBeNull();
  });

  it("Status schon eingetragen, Werte fehlen: erkennt das an der Wertung des Servers", () => {
    const gesetzt: Rohwerte = {
      sections: {
        fallscheibe: { series: [{ time_cs: 1200, standing: 0 }, { status: "aborted_by_shooter" }] },
      },
    };
    const liste = serienDerAuskunft(FALLSCHEIBE, fallscheibeWertung(gesetzt), AUSKUNFT_OFFEN);
    expect(liste.map((o) => o.ort)).toEqual(["Serie 2"]);
    expect(nurWerteFehlen(liste)).toBe(true);
    expect(
      nurWerteFehlen(
        serienDerAuskunft(FALLSCHEIBE, fallscheibeWertung(ANGEFANGEN), AUSKUNFT_OFFEN),
      ),
    ).toBe(false);
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

/** Zeile der Rangliste für diesen Start (nur, was die Erfassung liest). */
function ranglistenZeile(teil: Partial<RanglistenZeile>): RanglistenZeile {
  return {
    place: null,
    tied: false,
    tie_unresolved: false,
    needs_shootoff: false,
    group: "unranked",
    start_id: S,
    entry_id: "e-1",
    start_number: 7,
    attempt: 1,
    display_name: "M. Brandt",
    club: null,
    class_id: "k",
    class_short: "S",
    score: "43.00",
    score_text: "43,00 s",
    complete: false,
    tens: null,
    inner_tens: null,
    series: [],
    status: "aborted",
    abort_reason: "dnf",
    provisional_until: null,
    abort_note: "Ergebnis nicht vergleichbar: Serie 2 unvollständig erfasst",
    ...teil,
  };
}

function routen(
  anfang: ErgebnisStand,
  extra: Record<string, TestAntwort | ((a: { inhalt: unknown }) => TestAntwort)> = {},
) {
  let server = anfang;
  const form = () => ({
    inhalt: { ...maske(FALLSCHEIBE, server), abort_preview: auskunftFuer(server) },
  });
  const zeile = () => (server.status === "aborted" ? [ranglistenZeile({})] : []);
  return serverAttrappe({
    "GET /tournaments": { inhalt: [turnier] },
    [`GET /tournaments/${T}/overview`]: { inhalt: uebersicht },
    [`GET /tournaments/${T}/startlist?names=full`]: { inhalt: [startZeile] },
    [`GET /tournaments/${T}/results/needs-review`]: { inhalt: [] },
    [`GET /tournaments/${T}/starts/${S}/form`]: form,
    [`GET /tournaments/${T}/starts/${S}/form?capture_mode=series`]: form,
    [`GET /tournaments/${T}/starts/${S}/events`]: { inhalt: [] },
    [`GET /tournaments/${T}/competitions/w/ranking?class_id=k`]: () => ({
      inhalt: { groups: [{ class_id: "k", rows: zeile() }] },
    }),
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
            { status: "aborted_by_shooter", standing: 3 },
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

describe("Aufgegeben ohne Platz", () => {
  it("nennt den Grund der Rangliste und trägt den Serienstatus als Korrektur nach", async () => {
    const aufrufe = routen(
      serverStand(ANGEFANGEN, { seq: 4, status: "aborted", abort_reason: "dnf" }),
    );
    const user = userEvent.setup();
    anzeigen();
    expect(await screen.findByText("Ohne Platz in der Rangliste")).toBeInTheDocument();
    expect(
      screen.getByText("Grund: Ergebnis nicht vergleichbar: Serie 2 unvollständig erfasst."),
    ).toBeInTheDocument();
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
                { status: "aborted_by_shooter", standing: 3 },
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
