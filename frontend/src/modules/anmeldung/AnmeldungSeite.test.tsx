import { screen, within } from "@testing-library/react";
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
import type { Anmeldung, Start } from "./api";

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

function start(id: string, attempt: number, fee: number): Start {
  return {
    id,
    entry_id: "a1",
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

    const feld = screen.getByRole("textbox", { name: "Startnummer" });
    expect(
      await screen.findByText("Die Startnummer 3 ist in diesem Turnier schon vergeben."),
    ).toBeVisible();
    expect(feld).toHaveAttribute("aria-invalid", "true");
  });
});
