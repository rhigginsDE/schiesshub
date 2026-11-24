import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { bestimmeTurnier, sortiereTurniere } from "../../components/useAktivesTurnier";
import { renderApp } from "../../test/app";
import {
  heute,
  hinweisKennung,
  katalogGeaendert,
  naechsterTermin,
  nameMitJahr,
  nameVergeben,
  tage,
} from "./anfang";
import { beispielTurnier, beispielWettbewerb, TURNIER_ID, WETTBEWERB_ID } from "./testdaten";
import type { KopierterWettbewerb, Turnier, TurnierUebersicht, TurnierVorlage } from "./typen";

type Antwort = unknown | ((koerper: unknown) => Response | unknown);

/** Attrappe für `fetch` mit Methode (wie in TurnierSeite.test.tsx); merkt sich Schreibzugriffe. */
function api(antworten: Record<string, Antwort>) {
  const geschrieben: { methode: string; pfad: string; inhalt: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (eingabe: RequestInfo | URL, init?: RequestInit) => {
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
      return new Response(JSON.stringify(wert ?? null), {
        status: methode === "POST" ? 201 : 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return geschrieben;
}

const NEU_ID = "66666666-6666-4666-8666-666666666666";

function neuesTurnier(name: string): TurnierUebersicht {
  return { ...beispielTurnier(), id: NEU_ID, name };
}

function vorlage(id: string, name: string, verfuegbar = true): TurnierVorlage {
  return {
    id,
    name,
    description: `${name}: ein Satz, was drin ist.`,
    template: "custom",
    classes_federation: "bds",
    ranges: [{ name: "Flintenstand 15 m", lane_count: 2 }],
    competitions: [
      {
        catalog_federation: "bds",
        catalog_code: "4401",
        name: "Selbstladeflinte",
        available: true,
      },
      {
        catalog_federation: "bds",
        catalog_code: "4402",
        name: "Selbstladeflinte optisch",
        available: verfuegbar,
      },
    ],
  };
}

async function dialogOeffnen() {
  await userEvent.click(await screen.findByRole("button", { name: "Turnier anlegen" }));
  return screen.findByRole("dialog", { name: "Turnier anlegen" });
}

afterEach(() => {
  window.localStorage.clear();
});

describe("Turnier anlegen: drei Wege", () => {
  it("fragt zuerst, wie das Turnier beginnt, und bietet die Übung dezent an", async () => {
    api({ "GET /tournaments": [beispielTurnier()] });
    renderApp("/turnier");
    const dialog = await dialogOeffnen();

    expect(within(dialog).getByText("Wie möchtest du beginnen?")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /Leer beginnen/ })).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: /Wie ein früheres Turnier.*Teilnehmer/ }),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /Aus einer Vorlage/ })).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: /Übungsturnier mit Beispieldaten/ }),
    ).toBeInTheDocument();
    // Die Frage selbst hat keine grüne Hauptaktion; keine Formularfelder auf einmal.
    expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("leer: meldet einen doppelten Namen am Feld und sendet erst mit neuem Namen", async () => {
    const geschrieben = api({
      "GET /tournaments": [beispielTurnier()],
      "POST /tournaments": neuesTurnier("Herbstpokal"),
      [`GET /tournaments/${NEU_ID}/overview`]: neuesTurnier("Herbstpokal"),
    });
    renderApp("/turnier");
    const dialog = await dialogOeffnen();
    await userEvent.click(within(dialog).getByRole("button", { name: /Leer beginnen/ }));

    const name = within(dialog).getByRole("textbox", { name: /Name/ });
    const datum = within(dialog).getByLabelText(/^Datum/) as HTMLInputElement;
    await userEvent.clear(datum);
    await userEvent.type(datum, "2026-12-05");
    await userEvent.type(name, "testturnier fallscheibe");
    expect(within(dialog).getByText(/An diesem Tag gibt es schon/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Anlegen und einrichten" }));
    expect(geschrieben).toHaveLength(0);

    // Gleicher Name an einem anderen Tag ist erlaubt (wie die Serverregel).
    await userEvent.clear(datum);
    await userEvent.type(datum, "2026-12-06");
    expect(within(dialog).queryByText(/gibt es schon/)).not.toBeInTheDocument();
    await userEvent.clear(datum);
    await userEvent.type(datum, "2026-12-05");

    await userEvent.clear(name);
    await userEvent.click(within(dialog).getByRole("button", { name: "Anlegen und einrichten" }));
    expect(within(dialog).getByText("Gib dem Turnier einen Namen.")).toBeInTheDocument();

    await userEvent.type(name, "Herbstpokal");
    await userEvent.click(within(dialog).getByRole("button", { name: "Anlegen und einrichten" }));
    await waitFor(() => expect(geschrieben).toHaveLength(1));
    expect(geschrieben[0]).toMatchObject({ methode: "POST", pfad: "/tournaments" });
  });

  it("wie ein früheres: Name mit neuem Jahr, Veranstalter vorbelegt, danach geänderte Katalog-Wettbewerbe vom Server", async () => {
    const quelle = {
      ...beispielTurnier("closed"),
      name: "Herbstpokal 2025",
      date_from: "2025-12-05",
      date_to: "2025-12-05",
    };
    const geaendert: KopierterWettbewerb = {
      id: WETTBEWERB_ID,
      source_id: WETTBEWERB_ID,
      name: "Selbstladeflinte, offene Visierung",
      catalog_federation: "bds",
      catalog_code: "4401",
      catalog_changed: true,
      catalog_stand_then: "2025-06-30",
      catalog_stand_now: "2026-06-30",
      catalog_diff: {
        deviates: true,
        catalog_available: true,
        differences: [
          {
            path: "variant.abschnitte[0].serien",
            catalog_value: 5,
            tournament_value: 4,
            text: "Fallscheibe: 4 Serien statt 5",
          },
        ],
      },
    };
    // Der Server meldet `catalog_changed` an jedem Abruf des kopierten Wettbewerbs.
    const kopie = {
      ...beispielTurnier(),
      id: NEU_ID,
      competitions: [
        {
          ...beispielWettbewerb(),
          tournament_id: NEU_ID,
          catalog_changed: true,
          catalog_stand_then: "2025-06-30",
          catalog_stand_now: "2026-06-30",
        },
      ],
    };
    const geschrieben = api({
      "GET /tournaments": [quelle],
      [`POST /tournaments/${TURNIER_ID}/copy`]: (inhalt: unknown) => ({
        tournament: { ...kopie, ...(inhalt as object) },
        competitions: [geaendert, { ...geaendert, id: "x", catalog_changed: false }],
      }),
      [`GET /tournaments/${NEU_ID}/overview`]: { ...kopie, name: "Herbstpokal 2031" },
    });
    renderApp("/turnier");
    const dialog = await dialogOeffnen();
    await userEvent.click(within(dialog).getByRole("button", { name: /Wie ein früheres Turnier/ }));

    const name = within(dialog).getByRole("textbox", { name: /Name/ });
    const datum = within(dialog).getByLabelText(/Datum des neuen Turniers/) as HTMLInputElement;
    expect(datum.value).toBe(naechsterTermin("2025-12-05"));
    expect(name).toHaveValue(`Herbstpokal ${datum.value.slice(0, 4)}`);
    expect(within(dialog).getByText("Kommt nicht mit")).toBeInTheDocument();
    expect(
      within(dialog).getByText(/Teilnehmer, Anmeldungen, Durchgänge und Ergebnisse/),
    ).toBeInTheDocument();

    // Das Jahr im Namen folgt dem Datum.
    await userEvent.clear(datum);
    await userEvent.type(datum, "2031-05-01");
    expect(name).toHaveValue("Herbstpokal 2031");

    // Veranstalter: vorbelegt mit dem des Vorbilds, änderbar.
    const veranstalter = within(dialog).getByRole("textbox", { name: /Veranstalter/ });
    expect(veranstalter).toHaveValue("SV Musterstadt");
    await userEvent.clear(veranstalter);
    await userEvent.type(veranstalter, "SG Nachbarort");

    await userEvent.click(within(dialog).getByRole("button", { name: "Kopieren und einrichten" }));
    await waitFor(() => expect(geschrieben).toHaveLength(1));
    expect(geschrieben[0]).toMatchObject({
      pfad: `/tournaments/${TURNIER_ID}/copy`,
      inhalt: { name: "Herbstpokal 2031", date_from: "2031-05-01", organizer: "SG Nachbarort" },
    });
    // Nichts mehr nur auf diesem Gerät gemerkt.
    expect(window.localStorage.getItem(`schiesshub.kopie.${NEU_ID}`)).toBeNull();

    // In der Einrichtung: der Hinweis aus `catalog_changed`, mit Stand damals → heute.
    expect(
      await screen.findByText("Bei einem Wettbewerb hat sich der Katalog geändert"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Katalogstand damals 30.06.2025, heute 30.06.2026"),
    ).toBeInTheDocument();
    const pruefen = screen.getByRole("link", {
      name: "„Selbstladeflinte, offene Visierung“ prüfen",
    });
    expect(pruefen.getAttribute("href")).toContain(`wettbewerb=${WETTBEWERB_ID}`);

    // Ausblenden gilt nur auf diesem Gerät.
    await userEvent.click(screen.getByRole("button", { name: "Auf diesem Gerät ausblenden" }));
    expect(screen.queryByText(/hat sich der Katalog geändert/)).not.toBeInTheDocument();
  });

  it("wie ein früheres: 409 am Namen steht in Klartext am Feld", async () => {
    const quelle = { ...beispielTurnier("closed"), name: "Herbstpokal 2025" };
    api({
      "GET /tournaments": [quelle],
      [`POST /tournaments/${TURNIER_ID}/copy`]: () =>
        new Response(
          JSON.stringify({
            detail: "Ein Turnier mit diesem Namen und Datum gibt es schon.",
            errors: [
              { field: "name", message: "Ein Turnier mit diesem Namen und Datum gibt es schon." },
            ],
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
    });
    renderApp("/turnier");
    const dialog = await dialogOeffnen();
    await userEvent.click(within(dialog).getByRole("button", { name: /Wie ein früheres Turnier/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Kopieren und einrichten" }));
    expect(
      await within(dialog).findByText("Ein Turnier mit diesem Namen und Datum gibt es schon."),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: /Name/ })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("aus einer Vorlage: 409 template_unavailable sagt, was im Katalog fehlt", async () => {
    api({
      "GET /tournaments": [],
      "GET /tournament-templates": [vorlage("fallscheibe", "Fallscheibe Flinte 15 m")],
      "POST /tournaments/from-template": () =>
        new Response(
          JSON.stringify({
            detail: "Die Vorlage passt nicht zum aktuellen Katalog.",
            code: "template_unavailable",
            template_id: "fallscheibe",
            missing: [
              {
                kind: "competition",
                federation: "bds",
                code: "4403",
                variant_id: null,
                message_de: "Kennziffer 4403 (BDS)",
              },
              { kind: "classes", federation: "bds", message_de: "Klassen des Verbands BDS" },
            ],
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
    });
    renderApp("/turnier");
    const dialog = await dialogOeffnen();
    await userEvent.click(within(dialog).getByRole("button", { name: /Aus einer Vorlage/ }));
    await userEvent.click(
      await within(dialog).findByRole("radio", { name: "Fallscheibe Flinte 15 m" }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Anlegen und einrichten" }));

    expect(
      await within(dialog).findByText("Die Vorlage „Fallscheibe Flinte 15 m“ geht gerade nicht"),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Kennziffer 4403 (BDS) fehlt im Katalog.")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Klassen des Verbands BDS fehlen im Katalog."),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/Angelegt wurde nichts/)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Katalog ansehen" })).toBeInTheDocument();
  });

  it("aus einer Vorlage: Liste mit einem Satz, fehlende Disziplin gesperrt, Name vorbelegt", async () => {
    const geschrieben = api({
      "GET /tournaments": [beispielTurnier()],
      "GET /tournament-templates": [
        vorlage("fallscheibe", "Fallscheibe Flinte 15 m"),
        vorlage("kaputt", "Kaputte Vorlage", false),
      ],
      "POST /tournaments/from-template": neuesTurnier("Fallscheibe Flinte 15 m"),
      [`GET /tournaments/${NEU_ID}/overview`]: neuesTurnier("Fallscheibe Flinte 15 m"),
    });
    renderApp("/turnier");
    const dialog = await dialogOeffnen();
    await userEvent.click(within(dialog).getByRole("button", { name: /Aus einer Vorlage/ }));

    expect(
      await within(dialog).findByText("Fallscheibe Flinte 15 m: ein Satz, was drin ist."),
    ).toBeInTheDocument();
    expect(within(dialog).getAllByText("2 Wettbewerbe · Flintenstand 15 m")).toHaveLength(2);
    expect(within(dialog).getByRole("radio", { name: "Kaputte Vorlage" })).toBeDisabled();
    expect(within(dialog).getByText(/fehlt im Katalog/)).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("radio", { name: "Fallscheibe Flinte 15 m" }));
    const jahr = heute().slice(0, 4);
    expect(within(dialog).getByRole("textbox", { name: /Name/ })).toHaveValue(
      `Fallscheibe Flinte 15 m ${jahr}`,
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Anlegen und einrichten" }));
    await waitFor(() => expect(geschrieben).toHaveLength(1));
    expect(geschrieben[0]).toMatchObject({
      pfad: "/tournaments/from-template",
      inhalt: {
        template_id: "fallscheibe",
        name: `Fallscheibe Flinte 15 m ${jahr}`,
        date_from: heute(),
      },
    });
  });
});

describe("Übungsturnier", () => {
  const uebung = (): TurnierUebersicht => ({
    ...beispielTurnier("active"),
    name: "Übungsturnier",
    is_practice: true,
  });

  it("öffnet bei 409 practice_exists das vorhandene, kennzeichnet es und löscht es nach Rückfrage", async () => {
    const geschrieben = api({
      "GET /tournaments": [],
      "POST /tournaments/practice": () =>
        new Response(
          JSON.stringify({
            detail: "Es gibt schon ein Übungsturnier.",
            code: "practice_exists",
            tournament_id: TURNIER_ID,
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      [`GET /tournaments/${TURNIER_ID}/overview`]: uebung(),
      [`DELETE /tournaments/${TURNIER_ID}`]: () => new Response(null, { status: 204 }),
    });
    renderApp("/turnier");

    // Leerzustand ohne Turnier: Einstieg zum Ausprobieren.
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Zum Ausprobieren: Übungsturnier mit Beispieldaten",
      }),
    );
    expect(await screen.findByText("Das ist das Übungsturnier")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Übungsturnier", level: 1 })).toBeInTheDocument();
    expect(screen.getAllByText("Übung").length).toBeGreaterThan(0);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Übung löschen" }));
    const frage = await screen.findByRole("dialog", { name: "Übungsturnier löschen?" });
    expect(
      within(frage).getByText(
        /Alle Beispieldaten und alles, was du darin ausprobiert hast, werden gelöscht/,
      ),
    ).toBeInTheDocument();
    await userEvent.click(within(frage).getByRole("button", { name: "Übung löschen" }));
    await waitFor(() =>
      expect(geschrieben.map((g) => `${g.methode} ${g.pfad}`)).toEqual([
        "POST /tournaments/practice",
        `DELETE /tournaments/${TURNIER_ID}`,
      ]),
    );
    expect(await screen.findByRole("heading", { name: "Turnier", level: 1 })).toBeInTheDocument();
  });

  it("wird nie von selbst als Turnier der Stationen gewählt und steht unten", () => {
    const echt = { ...beispielTurnier("draft"), id: "echt", name: "Herbstpokal" } as Turnier;
    const ueb = { ...uebung(), id: "uebung" } as Turnier;
    expect(bestimmeTurnier([echt, ueb], null).turnier).toBeNull();
    expect(sortiereTurniere([ueb, echt]).map((t) => t.id)).toEqual(["echt", "uebung"]);
  });
});

describe("Hilfen für den Anfang", () => {
  it("setzt das neue Jahr in den Namen oder hängt es an", () => {
    expect(nameMitJahr("Herbstpokal 2025", "2026")).toBe("Herbstpokal 2026");
    expect(nameMitJahr("2025 Pokal 2025", "2026")).toBe("2025 Pokal 2026");
    expect(nameMitJahr("Vereinsmeisterschaft", "2026")).toBe("Vereinsmeisterschaft 2026");
  });

  it("schlägt denselben Tag im nächsten passenden Jahr vor", () => {
    expect(naechsterTermin("2025-12-05", "2026-11-23")).toBe("2026-12-05");
    expect(naechsterTermin("2025-06-01", "2026-11-23")).toBe("2027-06-01");
    expect(naechsterTermin("2024-02-29", "2024-11-23")).toBe("2025-02-28");
  });

  it("doppelter Name wie der Server: nur am selben Anfangsdatum, ohne Übung und ohne sich selbst", () => {
    const liste = [
      { ...beispielTurnier(), id: "a", name: "Herbstpokal 2026", date_from: "2026-12-05" },
      { ...beispielTurnier(), id: "u", name: "Übung", date_from: "2026-12-05", is_practice: true },
    ] as Turnier[];
    expect(nameVergeben(" herbstpokal 2026 ", "2026-12-05", liste)).toBe(true);
    expect(nameVergeben("Herbstpokal 2026", "2026-12-06", liste)).toBe(false);
    expect(nameVergeben("Herbstpokal 2026", "2026-12-05", liste, "a")).toBe(false);
    expect(nameVergeben("Übung", "2026-12-05", liste)).toBe(false);
    expect(nameVergeben("", "2026-12-05", liste)).toBe(false);
  });

  it("zählt Turniertage und findet Wettbewerbe mit geändertem Katalog", () => {
    expect(tage({ date_from: "2026-03-28", date_to: "2026-03-30" })).toBe(3);
    expect(tage({ date_from: "2026-03-28", date_to: "2026-03-28" })).toBe(1);
    const liste = [
      { id: "b", catalog_changed: true, catalog_stand_now: "2026-06-30" },
      { id: "a", catalog_changed: false, catalog_stand_now: "2026-06-30" },
      { id: "c", catalog_changed: true, catalog_stand_now: null },
    ];
    expect(katalogGeaendert(liste).map((w) => w.id)).toEqual(["b", "c"]);
    // Neue Änderung → neue Kennung → ein ausgeblendeter Hinweis erscheint wieder.
    expect(hinweisKennung(katalogGeaendert(liste))).toBe("b@2026-06-30,c@-");
  });
});
