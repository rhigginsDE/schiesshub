import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Disziplin, DisziplinDetail, Gruppe, Health, Verband } from "../../api/typen";
import { type ApiAttrappe, apiAttrappe, renderApp } from "../../test/app";

const health: Health = {
  status: "ok",
  version: "0.1.0",
  db: "ok",
  katalog: {
    verbaende: 1,
    gruppen: 2,
    disziplinen: 3,
    klassen: 0,
    importiert_am: "2026-11-21T10:00:00Z",
    fehler: [],
  },
};

const verbaende: Verband[] = [
  {
    id: "bds",
    kuerzel: "BDS",
    name: "Bund Deutscher Sportschützen 1975 e.V.",
    regelwerk: { name: "BDS-Sporthandbuch", stand: "2026-06-30" },
    status: "entwurf",
    anzahl_gruppen: 2,
    anzahl_disziplinen: 3,
  },
];

const gruppen: Gruppe[] = [
  {
    verband: "bds",
    id: "kw-25m-praezision",
    name: "KW 25 m Präzision",
    waffenart: "kurzwaffe",
    distanz_m: 25,
    art: "praezision",
    anzahl: 2,
    wertung_modell: "ringe",
    geprueft: true,
  },
  {
    verband: "bds",
    id: "kw-25m-speed",
    name: "KW 25 m Speed",
    waffenart: "kurzwaffe",
    distanz_m: 25,
    art: "speed",
    anzahl: 1,
    wertung_modell: "ringe_minus_zeit",
    geprueft: false,
  },
];

function disziplin(kennziffer: string, name: string, gruppe: Gruppe): Disziplin {
  return {
    verband: "bds",
    kennziffer,
    name,
    gruppe_id: gruppe.id,
    gruppe_name: gruppe.name,
    waffe: "Pistole",
    munition: "bis 9 mm",
    visierung: "offen",
    anschlag: "stehend",
    scheibe: "Kurzwaffenscheibe",
    optional: false,
    hinweis: null,
  };
}

const [praezision, speed] = gruppen as [Gruppe, Gruppe];
const disziplinen: Disziplin[] = [
  disziplin("1001", "Pistole bis 9 mm", praezision),
  disziplin("1002", "Pistole über 9 mm", praezision),
  disziplin("1401", "Pistole Standardkaliber", speed),
];

const detail1401: DisziplinDetail = {
  ...disziplin("1401", "Pistole Standardkaliber", speed),
  pruefen: [],
  fruehere_kennziffer: null,
  ablauf: {
    schluessel: "speed-4x5",
    beschreibung: "4 Serien à 5 Schuss auf Zeit",
    varianten: [
      {
        id: "bm-lm",
        name: "Bezirks-/Landesmeisterschaft",
        abschnitte: [
          {
            id: "speed",
            name: "Speed",
            serien: 4,
            schuss_je_serie: 5,
            ziele_je_serie: 5,
            max_zeit_je_serie_s: 60,
            zeit_wird_gemessen: true,
          },
        ],
      },
    ],
  },
  wertung: { modell: "ringe_minus_zeit", rangfolge: "absteigend", geprueft: false },
};

const basis: ApiAttrappe = {
  "/health": health,
  "/katalog/verbaende": verbaende,
  "/katalog/gruppen?verband=bds": gruppen,
  "/katalog/disziplinen?verband=bds": disziplinen,
  "/katalog/disziplinen/bds/1401": detail1401,
};

describe("Katalogseite", () => {
  it("zeigt Gruppen mit Anzahl und die Disziplinen des Verbands", async () => {
    apiAttrappe(basis);
    renderApp("/turnier/katalog");

    const liste = await screen.findByRole("region", { name: "Alle Gruppen" });
    expect(await within(liste).findByText("Pistole bis 9 mm")).toBeInTheDocument();
    expect(within(liste).getByText("1001")).toBeInTheDocument();
    expect(within(liste).getByText("1401")).toBeInTheDocument();
    expect(within(liste).getAllByRole("link")).toHaveLength(3);
    expect(within(liste).getByText("3 Disziplinen")).toBeInTheDocument();

    const speedKnopf = screen.getByRole("button", { name: /KW 25 m Speed/ });
    expect(within(speedKnopf).getByText("1")).toBeInTheDocument();
    expect(
      within(speedKnopf).getByText("Noch nicht mit dem Regelwerk abgeglichen"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Alle Gruppen/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    expect(screen.getByText(/BDS-Sporthandbuch, Stand 30\.06\.2026/)).toBeInTheDocument();
    expect(await screen.findByText("Server verbunden")).toBeInTheDocument();
  });

  it("öffnet die Detailansicht mit Ablauf und Wertung in Klartext", async () => {
    apiAttrappe(basis);
    renderApp("/turnier/katalog");

    await userEvent.click(await screen.findByRole("link", { name: /1401/ }));

    expect(await screen.findByRole("heading", { name: "Pistole Standardkaliber" })).toBeVisible();
    expect(screen.getByText("Noch nicht geprüft")).toBeInTheDocument();
    expect(screen.getByText("20 Schuss gesamt")).toBeInTheDocument();
    for (const teil of ["4 Serien", "5 Schuss", "5 Ziele", "max. 1 Min.", "Zeit wird gemessen"]) {
      expect(screen.getByText(teil)).toBeInTheDocument();
    }
    expect(screen.getByText("Ringe minus Zeit")).toBeInTheDocument();
    expect(
      screen.getByText("Das Regelwerk nennt für diese Wertung keine Regel bei Gleichstand."),
    ).toBeInTheDocument();
  });

  it("sagt bei leerer Suche, was los ist, und bietet die Suche in allen Gruppen an", async () => {
    apiAttrappe({
      ...basis,
      "/katalog/disziplinen?verband=bds&gruppe=kw-25m-speed&q=Revolver": [],
    });
    renderApp("/turnier/katalog?gruppe=kw-25m-speed&q=Revolver");

    expect(await screen.findByText("Keine Disziplin gefunden")).toBeInTheDocument();
    expect(
      screen.getByText(/In der Gruppe „KW 25 m Speed“ passt nichts zu „Revolver“/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "In allen Gruppen suchen" })).toBeInTheDocument();
  });

  it("erklärt einen Serverfehler und bietet einen neuen Versuch an", async () => {
    apiAttrappe({
      ...basis,
      "/katalog/disziplinen?verband=bds": () =>
        new Response(JSON.stringify({ detail: "Datenbank nicht bereit" }), { status: 500 }),
    });
    renderApp("/turnier/katalog");

    const meldung = await screen.findByRole("alert");
    expect(within(meldung).getByText("Fehler im Server")).toBeInTheDocument();
    expect(within(meldung).getByText(/Datenbank nicht bereit/)).toBeInTheDocument();
    expect(within(meldung).getByRole("button", { name: "Erneut versuchen" })).toBeInTheDocument();
  });

  it("meldet fehlende Verbindung, wenn der Server nicht antwortet", async () => {
    apiAttrappe({});
    globalThis.fetch = (() => Promise.reject(new TypeError("Failed to fetch"))) as typeof fetch;
    renderApp("/turnier/katalog");

    expect(await screen.findByText("Keine Verbindung zum Server")).toBeInTheDocument();
    expect(await screen.findByText("Keine Verbindung")).toBeInTheDocument();
  });
});
