import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderApp } from "../../test/app";
import { Blatt } from "./ausschreibung/Blatt";
import { druckModell } from "./ausschreibung/dokument";
import { beispielTurnier, TURNIER_ID, WETTBEWERB_ID } from "./testdaten";
import type { TurnierUebersicht } from "./typen";

// Mantines Textarea mit `autosize` horcht auf `document.fonts`; jsdom kennt das nicht.
if (!("fonts" in document)) {
  Object.defineProperty(document, "fonts", {
    configurable: true,
    value: { addEventListener() {}, removeEventListener() {}, ready: Promise.resolve() },
  });
}

type Antwort = unknown | ((koerper: unknown) => Response | unknown);

/**
 * Attrappe für `fetch` mit Methode: Schlüssel „METHODE /pfad“ (ohne `/api/v1`). Merkt sich alle
 * schreibenden Aufrufe mit Inhalt. Unbekannte Pfade antworten 404 wie eine fehlende Route.
 */
function api(antworten: Record<string, Antwort>) {
  const geschrieben: { methode: string; pfad: string; inhalt: unknown }[] = [];
  const attrappe = vi.fn(async (eingabe: RequestInfo | URL, init?: RequestInit) => {
    const methode = (init?.method ?? "GET").toUpperCase();
    const pfad = String(eingabe).replace(/^\/api\/v1/, "");
    const inhalt = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    if (methode !== "GET") geschrieben.push({ methode, pfad, inhalt });
    const schluessel = `${methode} ${pfad}`;
    if (!(schluessel in antworten)) {
      return new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
    }
    const eintrag = antworten[schluessel];
    const wert =
      typeof eintrag === "function" ? (eintrag as (k: unknown) => unknown)(inhalt) : eintrag;
    if (wert instanceof Response) return wert;
    return new Response(JSON.stringify(wert), {
      status: methode === "POST" ? 201 : 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", attrappe);
  return geschrieben;
}

const T = `/tournaments/${TURNIER_ID}`;

function grundlage(turnier: TurnierUebersicht = beispielTurnier()) {
  return {
    "GET /tournaments": [turnier],
    [`GET ${T}/overview`]: turnier,
    "GET /katalog/verbaende": [],
    "GET /katalog/disziplinen/bds/4401": {
      ...turnier.competitions[0],
      ablauf: {
        schluessel: "x",
        beschreibung: "x",
        varianten: [turnier.competitions[0]?.definition.variant],
      },
    },
  };
}

describe("Turnierliste", () => {
  it("zeigt Turniere mit Status und legt ein neues mit Vorlage an", async () => {
    const turnier = beispielTurnier();
    const geschrieben = api({
      ...grundlage(turnier),
      "POST /tournaments": { ...turnier, id: TURNIER_ID },
    });
    renderApp("/turnier");

    expect(await screen.findByText("Testturnier Fallscheibe")).toBeInTheDocument();
    expect(screen.getByText("Entwurf")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Disziplin-Katalog/ })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Turnier anlegen" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Name/), "Herbstpokal");
    await userEvent.click(within(dialog).getByRole("radio", { name: "Vereinsmeisterschaft" }));
    expect(within(dialog).getByText(/ein Start je Schütze/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Anlegen und einrichten" }));

    await waitFor(() => expect(geschrieben).toHaveLength(1));
    expect(geschrieben[0]).toMatchObject({
      methode: "POST",
      pfad: "/tournaments",
      inhalt: { name: "Herbstpokal", template: "club_championship" },
    });
  });
});

describe("Turnier einrichten", () => {
  it("markiert unvollständige Bereiche", async () => {
    api(grundlage({ ...beispielTurnier(), classes: [] }));
    renderApp(`/turnier/${TURNIER_ID}?bereich=stammdaten`);

    const nav = await screen.findByRole("navigation", { name: "Bereiche der Einrichtung" });
    const klassen = within(nav).getByRole("button", { name: /Klassen/ });
    expect(within(klassen).getByText("unvollständig")).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: /^Stände$/ })).toBeInTheDocument();
  });

  it("speichert eine Änderung am Ablauf als Definition", async () => {
    const turnier = beispielTurnier();
    const geschrieben = api({
      ...grundlage(turnier),
      [`PATCH ${T}/competitions/${WETTBEWERB_ID}`]: turnier.competitions[0],
    });
    renderApp(`/turnier/${TURNIER_ID}?bereich=wettbewerbe&wettbewerb=${WETTBEWERB_ID}`);

    const gewertet = await screen.findByRole("textbox", { name: /Gewertete Serien/ });
    await userEvent.type(gewertet, "3");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(geschrieben).toHaveLength(1));
    const inhalt = geschrieben[0]?.inhalt as { definition: { variant: { abschnitte: unknown[] } } };
    expect(inhalt.definition.variant.abschnitte[0]).toMatchObject({ serien_gewertet: 3 });
    expect(inhalt).not.toHaveProperty("reason");
  });

  it("verlangt bei aktivem Turnier einen Grund und zeigt Serverfehler am Feld", async () => {
    const turnier = beispielTurnier("active");
    let versuch = 0;
    const geschrieben = api({
      ...grundlage(turnier),
      [`PATCH ${T}/competitions/${WETTBEWERB_ID}`]: () => {
        versuch += 1;
        if (versuch === 1) {
          return new Response(
            JSON.stringify({
              detail: "Feld ‚serien‘: zu groß.",
              errors: [
                {
                  field: "definition.variant.abschnitte[0].serien",
                  message: "höchstens 10 Serien",
                },
              ],
            }),
            { status: 422 },
          );
        }
        return turnier.competitions[0];
      },
    });
    renderApp(`/turnier/${TURNIER_ID}?bereich=wettbewerbe&wettbewerb=${WETTBEWERB_ID}`);

    const serien = await screen.findByRole("textbox", { name: /^Serien/ });
    await userEvent.clear(serien);
    await userEvent.type(serien, "12");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/neu berechnet/)).toBeInTheDocument();
    const knopf = within(dialog).getByRole("button", { name: "Mit Grund speichern" });
    expect(knopf).toBeDisabled();
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Grund/ }), "Ausschreibung");
    await userEvent.click(knopf);

    await waitFor(() => expect(geschrieben).toHaveLength(1));
    expect(geschrieben[0]?.inhalt).toMatchObject({ reason: "Ausschreibung" });
    expect(await screen.findByText("höchstens 10 Serien")).toBeInTheDocument();
  });

  it("blendet die Ausschreibung aus, wenn das Backend sie nicht kennt", async () => {
    api(grundlage());
    renderApp(`/turnier/${TURNIER_ID}?bereich=stammdaten`);
    const nav = await screen.findByRole("navigation", { name: "Bereiche der Einrichtung" });
    await waitFor(() =>
      expect(within(nav).queryByRole("button", { name: /Ausschreibung/ })).not.toBeInTheDocument(),
    );
  });
});

describe("Ausschreibung als Blatt", () => {
  it("zeigt Kopf, Wettbewerbe mit Startgeld und lässt leere Texte weg", () => {
    const modell = druckModell(
      {
        title: "Ausschreibung Herbstpokal",
        tournament: {
          id: TURNIER_ID,
          name: "Herbstpokal",
          organizer: "SV Musterstadt",
          date_from: "2026-12-05",
          date_to: "2026-12-06",
          status: "draft",
          currency: "EUR",
        },
        facts: {},
        blocks: [
          { id: "leer", kind: "text", heading: "Sicherheit", body: "" },
          {
            id: "w",
            kind: "competitions",
            heading: "Wettbewerbe",
            body: "",
            competitions: [
              {
                id: "c1",
                name: "Repetierflinte",
                catalog_federation: "bds",
                catalog_code: "4403",
                group: null,
                range_name: "15-m-Stand",
                procedure: null,
                sections: [],
                multi_start: false,
                max_starts: 1,
                multi_start_rule: "best",
                multi_start_text: "Ein Start je Teilnehmer",
                deviates_from_catalog: false,
                deviations: [],
              },
            ],
          },
          {
            id: "f",
            kind: "fees",
            heading: "Startgeld",
            body: "",
            fees: {
              currency: "EUR",
              items: [
                {
                  competition_id: "c1",
                  name: "Repetierflinte",
                  fee_first_cents: 700,
                  fee_repeat_cents: null,
                },
              ],
            },
          },
        ],
      },
      "de",
    );
    render(<Blatt modell={modell} erstellt={new Date("2026-11-22T10:00:00")} />);

    expect(screen.getByRole("heading", { name: "Ausschreibung Herbstpokal" })).toBeInTheDocument();
    expect(screen.getByText("SV Musterstadt")).toBeInTheDocument();
    expect(screen.queryByText("Sicherheit")).not.toBeInTheDocument();
    const zeile = screen.getAllByRole("row").find((z) => within(z).queryByText("4403"));
    expect(zeile && within(zeile).getByText(/7,00/)).toBeTruthy();
    expect(screen.getByText("Stand 22.11.2026")).toBeInTheDocument();
    expect(screen.getByText("erstellt mit Schiesshub")).toBeInTheDocument();
  });
});
