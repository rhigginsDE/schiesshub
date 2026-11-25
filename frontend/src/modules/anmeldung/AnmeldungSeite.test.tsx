import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UserPlus } from "lucide-react";
import { beforeEach, describe, expect, it } from "vitest";
import {
  BRANDT,
  MAIER,
  renderAnsicht,
  serverAttrappe,
  type TestAntwort,
  VEREIN_TELL,
} from "../teilnehmer/testhilfe";
import { AnmeldungSeite } from "./AnmeldungSeite";
import type { Anmeldung, AnmeldungStart } from "./api";

const SUCHE = "Person suchen";
const T = "78a0a62a-fd80-4ef3-876a-3e7ad7a332b6";
const R = "46c19d4d-52f9-4ff1-956e-32630f067fd0";
const W = "b5c26783-fdd4-4dfc-92d4-3fc47a9243d9";
const K = "2c22e880-61bb-488a-b3f4-954ad6a5cb91";

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

const uebersicht = {
  ...turnier,
  ranges: [{ id: R, tournament_id: T, name: "15-m-Stand", lane_count: 2, sort: 0 }],
  classes: [
    {
      id: K,
      tournament_id: T,
      code: "schuetzen",
      name: "Schützenklasse",
      short: "S",
      sort: 0,
      merge_into_id: null,
    },
  ],
  competitions: [
    {
      id: W,
      tournament_id: T,
      range_id: R,
      sort: 0,
      catalog_federation: "bds",
      catalog_code: "4401",
      name: "Selbstladeflinte",
      definition: {},
      capture_mode: "series",
      multi_start: true,
      max_starts: 3,
      multi_start_rule: "best",
      fee_first_cents: 800,
      fee_repeat_cents: 500,
      class_ids: [],
      combined_ranking: false,
      planning: "queue",
      heat_minutes: null,
      changeover_minutes: 5,
      definition_revision: 1,
    },
  ],
};

function start(
  id: string,
  attempt: number,
  fee: number,
  start_rights: AnmeldungStart["start_rights"] = [],
): AnmeldungStart {
  return {
    id,
    entry_id: "a1",
    called_at: null,
    on_lane: false,
    competition_id: W,
    attempt,
    fee_cents: fee,
    status: "registered",
    abort_reason: null,
    queue_position: attempt,
    heat_id: null,
    lane: null,
    created_at: "2026-11-22T10:00:00Z",
    updated_at: "2026-11-22T10:00:00Z",
    start_rights,
  };
}

function anmeldung(teil: Partial<Anmeldung> = {}): Anmeldung {
  return {
    id: "a1",
    tournament_id: T,
    start_number: 7,
    class_id: K,
    person: {
      id: BRANDT.id,
      name: BRANDT.name,
      display_name: BRANDT.name,
      club: VEREIN_TELL.name,
    },
    starts: [],
    fee_total_cents: 0,
    created_at: "2026-11-22T10:00:00Z",
    updated_at: "2026-11-22T10:00:00Z",
    ...teil,
  };
}

function grundRouten(
  anmeldungen: Anmeldung[] = [],
): Record<string, TestAntwort | ((aufruf: { inhalt: unknown }) => TestAntwort)> {
  return {
    "GET /tournaments": { inhalt: [turnier] },
    [`GET /tournaments/${T}/overview`]: { inhalt: uebersicht },
    [`GET /tournaments/${T}/entries`]: { inhalt: anmeldungen },
    "GET /clubs": { inhalt: [VEREIN_TELL] },
    "GET /katalog/klassen?verband=bds": {
      inhalt: [{ id: "schuetzen", kurz: "S", alter_hilfe: "mind. 21 zu Beginn des Sportjahres" }],
    },
    "GET /persons?limit=50": { inhalt: [BRANDT, MAIER], kopf: { "X-Total-Count": "2" } },
    "GET /persons?q=Brandt&limit=50": { inhalt: [BRANDT], kopf: { "X-Total-Count": "1" } },
  };
}

function zeigen() {
  return renderAnsicht(() => <AnmeldungSeite station="anmeldung" icon={UserPlus} />);
}

beforeEach(() => {
  localStorage.clear();
  // jsdom kennt scrollIntoView nicht; die Klassenauswahl (Combobox) ruft es auf.
  Element.prototype.scrollIntoView = () => undefined;
});

describe("Station Anmeldung", () => {
  it("nimmt das einzige aktive Turnier und zeigt es im Kopf mit „wechseln“", async () => {
    serverAttrappe(grundRouten());
    zeigen();
    expect(await screen.findByRole("heading", { name: "Anmeldung" })).toBeInTheDocument();
    expect(await screen.findByText("Herbstpokal")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Turnier wechseln/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Teilnehmer/ })).toHaveAttribute(
      "href",
      "/anmeldung/teilnehmer",
    );
  });

  it("meldet einen Schützen an, bucht Starts und bestätigt Startnummer und Betrag", async () => {
    const user = userEvent.setup();
    const aufrufe = serverAttrappe({
      ...grundRouten(),
      [`POST /tournaments/${T}/entries`]: { status: 201, inhalt: anmeldung() },
      [`POST /tournaments/${T}/entries/a1/starts`]: {
        status: 201,
        inhalt: [start("s1", 1, 800), start("s2", 2, 500)],
      },
    });
    zeigen();

    const suche = await screen.findByRole("searchbox", { name: SUCHE });
    await user.type(suche, "Brandt{Enter}");
    expect(await screen.findByRole("form", { name: "Markus Brandt" })).toBeDefined();

    await user.type(screen.getByRole("combobox", { name: "Klasse" }), "Sch{Enter}");
    expect(screen.getByText("mind. 21 zu Beginn des Sportjahres")).toBeInTheDocument();

    const mehr = screen.getByRole("button", { name: "4401 Selbstladeflinte: ein Start mehr" });
    await user.click(mehr);
    await user.click(mehr);
    expect(screen.getByText("1 Start + 1 Nachkauf")).toBeInTheDocument();
    expect(screen.getAllByText("13,00 €").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Anmelden" }));

    expect(await screen.findByText("Markus Brandt ist angemeldet.")).toBeInTheDocument();
    const bestaetigung = screen
      .getByText("Markus Brandt ist angemeldet.")
      .closest("[role=status]") as HTMLElement;
    expect(within(bestaetigung).getByText("7")).toBeInTheDocument();
    expect(within(bestaetigung).getByText("13,00 €")).toBeInTheDocument();

    const posts = aufrufe.filter((a) => a.methode === "POST");
    expect(posts.map((a) => a.inhalt)).toEqual([
      { person_id: BRANDT.id, class_id: K },
      { competition_id: W, count: 2 },
    ]);
    // Fokus zurück in die Suche für den nächsten Schützen
    expect(await screen.findByRole("searchbox", { name: SUCHE })).toHaveFocus();
  });

  it("findet eine Anmeldung über die Startnummer und zeigt den Nachkauf-Preis", async () => {
    const user = userEvent.setup();
    serverAttrappe({
      ...grundRouten([anmeldung({ starts: [start("s1", 1, 800)], fee_total_cents: 800 })]),
      "GET /persons?q=7&limit=50": { inhalt: [], kopf: { "X-Total-Count": "0" } },
    });
    zeigen();
    const suche = await screen.findByRole("searchbox", { name: SUCHE });
    await user.type(suche, "7");
    expect(await screen.findByText("Treffer über die Startnummer – Enter öffnet")).toBeVisible();
    await user.keyboard("{Enter}");

    expect(await screen.findByText("Schon angemeldet")).toBeInTheDocument();
    expect(screen.getByText("Nachkauf 5,00 €")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Starts buchen" })).toBeDisabled();
  });

  it("meldet eine Anmeldung ohne Start neutral, nicht als Erfolg", async () => {
    const user = userEvent.setup();
    serverAttrappe({
      ...grundRouten(),
      [`POST /tournaments/${T}/entries`]: { status: 201, inhalt: anmeldung() },
    });
    zeigen();
    const suche = await screen.findByRole("searchbox", { name: SUCHE });
    await user.type(suche, "Brandt{Enter}");
    await screen.findByRole("form", { name: "Markus Brandt" });
    await user.type(screen.getByRole("combobox", { name: "Klasse" }), "Sch{Enter}");
    expect(screen.getByText(/Noch kein Start gewählt/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Anmelden" }));
    const frage = await screen.findByRole("dialog", { name: "Ohne Start speichern?" });
    await user.click(within(frage).getByRole("button", { name: "Ohne Start speichern" }));

    const titel = await screen.findByText(
      "Markus Brandt ist angemeldet – noch kein Start gebucht.",
    );
    const meldung = titel.closest("[role=status]") as HTMLElement;
    expect(meldung).toHaveAttribute("data-ton", "hinweis");
    expect(within(meldung).getByText(/nichts zu zahlen/)).toBeInTheDocument();
    expect(within(meldung).queryByText("0,00 €")).toBeNull();
  });

  it("fragt vor dem Speichern ohne Start nach; Zurück und Esc speichern nichts und führen zur Startauswahl", async () => {
    const user = userEvent.setup();
    const aufrufe = serverAttrappe({
      ...grundRouten(),
      [`POST /tournaments/${T}/entries`]: { status: 201, inhalt: anmeldung() },
      [`POST /tournaments/${T}/entries/a1/starts`]: {
        status: 201,
        inhalt: [start("s1", 1, 800)],
      },
    });
    zeigen();
    const suche = await screen.findByRole("searchbox", { name: SUCHE });
    await user.type(suche, "Brandt{Enter}");
    await screen.findByRole("form", { name: "Markus Brandt" });
    await user.type(screen.getByRole("combobox", { name: "Klasse" }), "Sch{Enter}");

    // Strg+Enter wie an der Kasse
    await user.keyboard("{Control>}{Enter}{/Control}");
    let frage = await screen.findByRole("dialog", { name: "Ohne Start speichern?" });
    expect(
      within(frage).getByText(
        "Markus Brandt ist dann nicht für einen Wettbewerb gemeldet und schießt nicht.",
      ),
    ).toBeInTheDocument();
    // Fokus auf dem sicheren Knopf: Enter führt zurück, speichert nicht
    const zurueck = within(frage).getByRole("button", { name: "Zurück, Start wählen" });
    await waitFor(() => expect(zurueck).toHaveFocus());
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const anzahl = screen.getByRole("spinbutton", { name: "Neue Starts in 4401 Selbstladeflinte" });
    await waitFor(() => expect(anzahl).toHaveFocus());

    // Esc wirkt genauso
    await user.click(screen.getByRole("button", { name: "Anmelden" }));
    frage = await screen.findByRole("dialog", { name: "Ohne Start speichern?" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(anzahl).toHaveFocus());
    expect(aufrufe.filter((a) => a.methode === "POST")).toEqual([]);

    // Mit einem Start: keine Rückfrage
    await user.keyboard("+");
    await user.click(screen.getByRole("button", { name: "Anmelden" }));
    expect(await screen.findByText("Markus Brandt ist angemeldet.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("meldet eine reine Änderung als Änderung, nicht als gebuchte Starts", async () => {
    const user = userEvent.setup();
    const vorhanden = anmeldung({ starts: [start("s1", 1, 800)], fee_total_cents: 800 });
    serverAttrappe({
      ...grundRouten([vorhanden]),
      [`PATCH /tournaments/${T}/entries/a1`]: { inhalt: { ...vorhanden, start_number: 12 } },
    });
    zeigen();
    const suche = await screen.findByRole("searchbox", { name: SUCHE });
    await user.type(suche, "Brandt{Enter}");
    await screen.findByText("Schon angemeldet");
    const nummer = screen.getByRole("textbox", { name: "Startnummer" });
    await user.clear(nummer);
    await user.type(nummer, "12");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    const titel = await screen.findByText("Anmeldung von Markus Brandt geändert (Startnummer 12).");
    expect(titel.closest("[role=status]")).toHaveAttribute("data-ton", "hinweis");
    expect(screen.queryByText(/Starts für Markus Brandt gebucht/)).toBeNull();
  });

  it("zählt gewählte Starts mit und nennt die Grenze, wenn „+“ gesperrt ist", async () => {
    const user = userEvent.setup();
    serverAttrappe(
      grundRouten([anmeldung({ starts: [start("s1", 1, 800)], fee_total_cents: 800 })]),
    );
    zeigen();
    const suche = await screen.findByRole("searchbox", { name: SUCHE });
    await user.type(suche, "Brandt{Enter}");
    await screen.findByText("Schon angemeldet");
    expect(screen.getByText("noch 2 möglich")).toBeInTheDocument();
    const mehr = screen.getByRole("button", { name: "4401 Selbstladeflinte: ein Start mehr" });
    await user.click(mehr);
    expect(screen.getByText("noch 1 möglich")).toBeInTheDocument();
    await user.click(mehr);
    expect(screen.getByText("Höchstens 3 Starts erreicht")).toBeInTheDocument();
    expect(mehr).toBeDisabled();
  });

  it("zeigt den Konflikt der Startnummer direkt am Feld", async () => {
    const user = userEvent.setup();
    serverAttrappe({
      ...grundRouten(),
      [`POST /tournaments/${T}/entries`]: {
        status: 409,
        inhalt: { detail: "Die Startnummer 3 ist in diesem Turnier schon vergeben." },
      },
    });
    zeigen();
    const suche = await screen.findByRole("searchbox", { name: SUCHE });
    await user.type(suche, "Brandt{Enter}");
    await screen.findByRole("form", { name: "Markus Brandt" });
    await user.type(screen.getByRole("combobox", { name: "Klasse" }), "Sch{Enter}");
    await user.type(screen.getByRole("textbox", { name: "Startnummer" }), "3");
    await user.click(screen.getByRole("button", { name: "Anmelden" }));
    const frage = await screen.findByRole("dialog", { name: "Ohne Start speichern?" });
    await user.click(within(frage).getByRole("button", { name: "Ohne Start speichern" }));

    const feld = screen.getByRole("textbox", { name: "Startnummer" });
    expect(
      await screen.findByText("Die Startnummer 3 ist in diesem Turnier schon vergeben."),
    ).toBeVisible();
    expect(feld).toHaveAttribute("aria-invalid", "true");
  });
});

describe("Startrecht an der Kasse (Warnung mit Fundstelle, keine Sperre)", () => {
  const WARNUNG = {
    code: "kein_startrecht",
    severity: "warning",
    message_de:
      "Laut DM-Tabelle des DSB hat Klasse Schüler männlich (20) in KK - 100m (1.35) kein Startrecht.",
    source: "Startrecht-Tabelle DSB zur Deutschen Meisterschaft; Eintrag 1.35 „KK - 100m“",
  } as const;
  const HINWEIS = {
    code: "startet_bei",
    severity: "hint",
    message_de:
      "Laut DM-Tabelle des DSB startet Klasse Schüler weiblich (21) in Flinte Trap (3.10) bei Klasse Schüler männlich (20).",
    source: "Startrecht-Tabelle DSB zur Deutschen Meisterschaft; Eintrag 3.10 „Flinte Trap“",
  } as const;
  const auskunft = (status: string, start_rights: readonly object[]) => ({
    inhalt: [
      {
        competition_id: W,
        competition_name: "Selbstladeflinte",
        competition_code: "4401",
        status,
        start_rights,
      },
    ],
  });

  it("zeigt die Warnung vor dem Buchen am gewählten Wettbewerb, bucht ohne Rückfrage und zeigt sie danach", async () => {
    const user = userEvent.setup();
    const aufrufe = serverAttrappe({
      ...grundRouten(),
      [`GET /tournaments/${T}/start-rights?class_id=${K}`]: auskunft("kein_startrecht", [WARNUNG]),
      [`POST /tournaments/${T}/entries`]: { status: 201, inhalt: anmeldung() },
      [`POST /tournaments/${T}/entries/a1/starts`]: {
        status: 201,
        inhalt: [start("s1", 1, 800, [WARNUNG])],
      },
    });
    zeigen();
    const suche = await screen.findByRole("searchbox", { name: SUCHE });
    await user.type(suche, "Brandt{Enter}");
    await screen.findByRole("form", { name: "Markus Brandt" });
    await user.type(screen.getByRole("combobox", { name: "Klasse" }), "Sch{Enter}");
    // Noch kein Start gewählt: keine Meldung
    await waitFor(() =>
      expect(aufrufe.some((a) => a.pfad.includes("/start-rights?class_id="))).toBe(true),
    );
    expect(screen.queryByText(WARNUNG.message_de)).toBeNull();

    await user.click(screen.getByRole("button", { name: "4401 Selbstladeflinte: ein Start mehr" }));
    const liste = await screen.findByRole("list", { name: "Startrecht" });
    expect(within(liste).getByText("Startrecht: Warnung")).toBeInTheDocument();
    expect(within(liste).getByText(WARNUNG.message_de)).toBeInTheDocument();
    expect(within(liste).getByText(`Fundstelle: ${WARNUNG.source}`)).toBeInTheDocument();
    expect(within(liste).getByText("Der Start bleibt trotzdem buchbar.")).toBeInTheDocument();
    expect(within(liste).getByRole("listitem")).toHaveAttribute("data-ton", "warn");

    // Keine Sperre, kein Zwangsdialog
    const knopf = screen.getByRole("button", { name: "Anmelden" });
    expect(knopf).toBeEnabled();
    await user.click(knopf);
    const titel = await screen.findByText("Markus Brandt ist angemeldet.");
    expect(screen.queryByRole("dialog")).toBeNull();
    const bestaetigung = titel.closest("[role=status]") as HTMLElement;
    expect(within(bestaetigung).getByText(WARNUNG.message_de)).toBeInTheDocument();
    expect(within(bestaetigung).getByText(`Fundstelle: ${WARNUNG.source}`)).toBeInTheDocument();
    // Nach dem Buchen ohne den Satz zur Buchbarkeit
    expect(within(bestaetigung).queryByText("Der Start bleibt trotzdem buchbar.")).toBeNull();
  });

  it("Nachkauf: fragt über die Anmeldung, zeigt den Hinweis ruhig und die Warnung am gebuchten Start", async () => {
    const user = userEvent.setup();
    const vorhanden = anmeldung({
      starts: [start("s1", 1, 800, [WARNUNG]), start("s2", 2, 500, [WARNUNG])],
      fee_total_cents: 1300,
    });
    serverAttrappe({
      ...grundRouten([vorhanden]),
      [`GET /tournaments/${T}/start-rights?entry_id=a1`]: auskunft("startet_bei", [HINWEIS]),
    });
    zeigen();
    // In der Liste der Anmeldungen: Symbol mit Text am Start
    expect(await screen.findByRole("img", { name: "Warnung zum Startrecht" })).toBeInTheDocument();

    const suche = await screen.findByRole("searchbox", { name: SUCHE });
    await user.type(suche, "Brandt{Enter}");
    await screen.findByText("Schon angemeldet");
    // Gebuchte Starts: die Warnung einmal je Wettbewerb, nicht je Start
    const gebucht = screen.getByRole("region", { name: "Gebuchte Starts" });
    expect(within(gebucht).getAllByText(WARNUNG.message_de)).toHaveLength(1);
    expect(within(gebucht).getByText("Startrecht: Warnung")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "4401 Selbstladeflinte: ein Start mehr" }));
    const hinweis = (await screen.findByText(HINWEIS.message_de)).closest("li") as HTMLElement;
    expect(hinweis).toHaveAttribute("data-ton", "info");
    expect(within(hinweis).getByText("Startrecht: Hinweis")).toBeInTheDocument();
    expect(within(hinweis).queryByText("Der Start bleibt trotzdem buchbar.")).toBeNull();
    expect(screen.getByRole("button", { name: "Starts buchen" })).toBeEnabled();
  });

  it("ohne Meldung (keine Angabe, BDS) erscheint nichts; ein Fehler der Auskunft hält das Buchen nicht auf", async () => {
    const user = userEvent.setup();
    serverAttrappe({
      ...grundRouten(),
      [`GET /tournaments/${T}/start-rights?class_id=${K}`]: auskunft("keine_angabe", []),
    });
    zeigen();
    const suche = await screen.findByRole("searchbox", { name: SUCHE });
    await user.type(suche, "Brandt{Enter}");
    await screen.findByRole("form", { name: "Markus Brandt" });
    await user.type(screen.getByRole("combobox", { name: "Klasse" }), "Sch{Enter}");
    await user.click(screen.getByRole("button", { name: "4401 Selbstladeflinte: ein Start mehr" }));
    expect(screen.queryByRole("list", { name: "Startrecht" })).toBeNull();
    expect(screen.queryByText(/Startrecht/)).toBeNull();
  });

  it("Fehler der Auskunft: ruhiger Hinweis, Buchen bleibt möglich", async () => {
    const user = userEvent.setup();
    serverAttrappe({
      ...grundRouten(),
      [`GET /tournaments/${T}/start-rights?class_id=${K}`]: {
        status: 500,
        inhalt: { detail: "kaputt" },
      },
    });
    zeigen();
    const suche = await screen.findByRole("searchbox", { name: SUCHE });
    await user.type(suche, "Brandt{Enter}");
    await screen.findByRole("form", { name: "Markus Brandt" });
    await user.type(screen.getByRole("combobox", { name: "Klasse" }), "Sch{Enter}");
    await user.click(screen.getByRole("button", { name: "4401 Selbstladeflinte: ein Start mehr" }));
    expect(
      await screen.findByText("Startrecht gerade nicht prüfbar. Buchen geht trotzdem."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anmelden" })).toBeEnabled();
  });
});
