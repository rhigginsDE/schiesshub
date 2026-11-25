import { MantineProvider } from "@mantine/core";
import { act, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BEGRIFFE_RUECKFALL, type Begriffssaetze } from "../../lib/begriffe";
import { theme } from "../../theme";
import { SchirmAnsicht } from "./schirm/Schirm";
import type { FeedQuelle, FeedZustand } from "./schirm/useFeed";
import {
  abbruchRangliste,
  beispielFeed,
  getrenntRangliste,
  rangliste,
  szenen,
  zeile,
} from "./testdaten";
import type { Feed, FeedPerson, SzeneVon } from "./typen";

const QUELLE: FeedQuelle = { art: "anzeige", id: "a1" };

function zustand(feed: Feed | null, teil: Partial<FeedZustand> = {}) {
  return { feed, laedt: false, sperre: null, getrenntSeit: null, versatzMs: 0, ...teil };
}

function mitTheme(kind: ReactNode) {
  return <MantineProvider theme={theme}>{kind}</MantineProvider>;
}

function zeige(
  feed: Feed | null,
  teil: Partial<FeedZustand> = {},
  quelle = QUELLE,
  begriffe: Begriffssaetze | null = null,
) {
  return render(
    mitTheme(<SchirmAnsicht zustand={zustand(feed, teil)} quelle={quelle} begriffe={begriffe} />),
  );
}

/**
 * Begriffssätze wie vom Server, mit einem erfundenen Verband „probe“, dessen Wörter sich überall
 * unterscheiden – so zeigt der Test, dass jedes Wort aus dem Satz des Verbands kommt.
 */
const BEGRIFFE: Begriffssaetze = {
  default: BEGRIFFE_RUECKFALL,
  federations: {
    dsb: { ...BEGRIFFE_RUECKFALL, kennziffer: "Kennzahl", trefferaufnahme: "Auswertung" },
    probe: {
      ...BEGRIFFE_RUECKFALL,
      durchgang: "Block",
      schuetzenstand: "Platz-am-Stand",
      schuetzenstaende: "Plätze-am-Stand",
      schiessstand: "Stand",
      serie: "Runde",
      serien: "Runden",
      trefferaufnahme: "Auswertung",
      kennziffer: "Kennzahl",
    },
  },
};

afterEach(() => vi.useRealTimers());

describe("Bildschirm", () => {
  it("zeigt Kopf mit Turnier, Veranstalter, Uhr nach Serverzeit und Laufzeile", () => {
    zeige(beispielFeed({ ticker: "Kaffee im Vereinsheim" }));
    expect(screen.getByRole("heading", { level: 1, name: "Herbstpokal 2026" })).toBeVisible();
    expect(screen.getByText(/SV Beispiel · 22\.11\.2026/)).toBeVisible();
    expect(screen.getByRole("time")).toHaveAttribute("dateTime", expect.stringMatching(/^2026-/));
    expect(screen.getAllByText("Kaffee im Vereinsheim").length).toBeGreaterThan(0);
  });

  it("Live-Wertung: Platz, geteilte Plätze, gestrichene Serie, Live-Punkt, Startnummer ohne Namen", () => {
    zeige(beispielFeed({ scenes: [szenen.live_ranking] }));
    const liste = screen.getByRole("region", { name: "Live-Wertung" });
    expect(within(liste).getByText("Anna Beispiel")).toBeVisible();
    expect(within(liste).getAllByText("geteilt")).toHaveLength(2);
    expect(within(liste).getByText("Startnummer 17")).toBeVisible();
    expect(within(liste).getAllByRole("img", { name: "läuft" }).length).toBeGreaterThan(0);
    expect(within(liste).getAllByText("88")[0]).toHaveAttribute("data-gestrichen");
    expect(within(liste).getByText("Damenklasse")).toBeVisible();
    expect(within(liste).getByText("+ 2 weitere Plätze")).toBeVisible();
    // Gold nur für Platz 1
    const erste = liste.querySelectorAll("[data-erster]");
    expect(erste).toHaveLength(2);
  });

  it("Ergebnisliste: Podest je Klasse", () => {
    zeige(beispielFeed({ scenes: [szenen.winners] }));
    const sieger = screen.getByRole("region", { name: "Ergebnisliste" });
    expect(within(sieger).getByText("Schützenklasse")).toBeVisible();
    expect(within(sieger).getByText("Clara Probe")).toBeVisible();
    expect(sieger.querySelectorAll('[data-rang="1"]')).toHaveLength(2);
    // Zwei geteilte Zweite stehen gleich hoch, auch wenn einer rechts (an Stelle 3) steht.
    expect(sieger.querySelectorAll('[data-stufe="2"]')).toHaveLength(2);
    expect(sieger.querySelectorAll('[data-stufe="3"]')).toHaveLength(0);
  });

  it("Startliste: Durchgang, Schützenstand, Status, weitere", () => {
    zeige(beispielFeed({ scenes: [szenen.startlist] }));
    const liste = screen.getByRole("region", { name: "Startliste" });
    expect(within(liste).getByText(/Durchgang 3 · \d\d:\d\d · Schützenstand 2/)).toBeVisible();
    expect(within(liste).getByText("aufgerufen")).toBeVisible();
    expect(within(liste).getByText("Startnummer 6")).toBeVisible();
    expect(within(liste).getByText("+ 4 weitere Starts")).toBeVisible();
  });

  it("Live-Wertung: Kennziffer vor dem Namen, kein Hinweis auf Katalog-Abweichung, Abgebrochene im Block „Ohne Platzierung“", () => {
    const basis = rangliste();
    const klasse = basis.groups[0];
    if (!klasse) throw new Error("Testdaten");
    const ranking = {
      ...basis,
      competition_code: "1201",
      deviates: true,
      deviations: ["Sollzeit 60 s statt 50 s"],
      groups: [
        {
          ...klasse,
          more: 0,
          unplaced: [
            zeile({
              start_id: "a1",
              place: null,
              group: "unranked",
              status: "aborted",
              abort_reason: "dnf",
              display_name: "Egon Abbruch",
              score_text: "30,00 s",
            }),
            zeile({
              start_id: "a2",
              place: null,
              group: "unranked",
              status: "aborted",
              abort_reason: "dns",
              display_name: "Rita Fern",
              score_text: null,
            }),
          ],
        },
      ],
    };
    const live = szenen.live_ranking as SzeneVon<"live_ranking">;
    zeige(beispielFeed({ scenes: [{ ...live, ranking }] }));
    const liste = screen.getByRole("region", { name: "Live-Wertung" });
    expect(within(liste).getByRole("heading", { name: "1201Pistole bis 9 mm" })).toBeVisible();
    // Abweichungen vom Katalog gehören in die Turnierverwaltung, nicht an den Schirm.
    expect(within(liste).queryByText(/Katalog/)).toBeNull();
    expect(within(liste).queryByText("Sollzeit 60 s statt 50 s")).toBeNull();
    expect(within(liste).queryByText(/Sporthandbuch/)).toBeNull();
    expect(within(liste).getByText("Ohne Platzierung")).toBeVisible();
    const ohne = Array.from(liste.querySelectorAll<HTMLElement>("[data-ohne-platz]"));
    expect(ohne).toHaveLength(2);
    const [egon, rita] = ohne as [HTMLElement, HTMLElement];
    expect(within(egon).getByText("Egon Abbruch")).toBeVisible();
    expect(within(egon).getByText("Abbruch (AB)")).toBeVisible();
    expect(within(egon).getByText("30,00 s")).toBeVisible();
    // „Nicht angetreten“: weder Platz noch Wert, nur der Grund
    expect(within(rita).getByText("nicht angetreten")).toBeVisible();
    expect(rita.querySelector("[data-erster]")).toBeNull();
    expect(within(rita).queryByText("–")).toBeNull();
    expect(within(rita).queryByText(/0,00/)).toBeNull();
    // Hinter allen Plätzen
    const alle = Array.from(liste.querySelectorAll("[data-gruppe]"));
    expect(alle.slice(-2)).toEqual(ohne);
  });

  it("Zehntelwertung und Stechen: Ringe mit Komma, geteilter Platz mit dezentem Hinweis", () => {
    const zehntel = (nr: number, rings: string) => ({
      section_id: "wertung",
      number: nr,
      struck: false,
      status: "normal",
      rings,
      time_cs: null,
      standing: null,
      total_cs: null,
    });
    const basis = rangliste();
    const ranking = {
      ...basis,
      tie_word: "Ringgleichheit",
      groups: [
        {
          class_id: "k1",
          class_name: "Schützenklasse",
          class_short: "S",
          more: 0,
          unplaced: [],
          // Reihenfolge und Plätze wie vom Server: nichts wird im Frontend neu sortiert.
          rows: [
            zeile({
              start_id: "z1",
              place: 1,
              tied: true,
              needs_shootoff: true,
              tie_unresolved: true,
              tie_reason: "shootoff",
              tie_note: "Ringgleichheit auf Platz 1: Stechen",
              display_name: "Hanna Zehntel",
              score_text: "208,4 Ringe",
              series: [zehntel(1, "104.3"), zehntel(2, "104.1")],
            }),
            zeile({
              start_id: "z2",
              place: 1,
              tied: true,
              needs_shootoff: true,
              tie_unresolved: true,
              tie_reason: "shootoff",
              tie_note: "Ringgleichheit auf Platz 1: Stechen",
              display_name: "Ida Zehntel",
              score_text: "208,4 Ringe",
              series: [zehntel(1, "103.9"), zehntel(2, "104.5")],
            }),
            zeile({
              start_id: "z3",
              place: 3,
              tied: true,
              tie_unresolved: true,
              tie_reason: "manual",
              tie_note: "Ringgleichheit: nach Sportordnung manuell entscheiden",
              display_name: "Jan Zehntel",
              score_text: "201,0 Ringe",
              series: [zehntel(1, "100.0"), zehntel(2, "101.0")],
            }),
          ],
        },
      ],
    };
    const live = szenen.live_ranking as SzeneVon<"live_ranking">;
    zeige(beispielFeed({ scenes: [{ ...live, ranking }] }));
    const liste = screen.getByRole("region", { name: "Live-Wertung" });
    expect(within(liste).getByText("104,3")).toBeVisible();
    expect(within(liste).getByText("101,0")).toBeVisible();
    expect(within(liste).getAllByText("208,4")).toHaveLength(2);
    // Das formelle Wort kommt aus `tie_word` der Rangliste.
    expect(within(liste).getAllByText("Ringgleichheit: Stechen")).toHaveLength(2);
    expect(within(liste).queryByText(/Gleichstand/)).toBeNull();
    expect(within(liste).getByText("Ringgleichheit: manuell entscheiden")).toBeVisible();
    const namen = Array.from(liste.querySelectorAll("[data-gruppe] b")).map((b) => b.textContent);
    expect(namen.map((n) => n?.replace(/^\d+/, ""))).toEqual([
      "Hanna Zehntel",
      "Ida Zehntel",
      "Jan Zehntel",
    ]);
  });

  it("Ergebnisliste: Abgebrochene nie auf dem Podest, sondern mit Grund danach", () => {
    const basis = rangliste();
    const ranking = {
      ...basis,
      groups: [
        {
          class_id: "k1",
          class_name: "Schützenklasse",
          class_short: "S",
          more: 0,
          rows: [zeile({ start_id: "w1", place: 1, display_name: "Anna Beispiel" })],
          unplaced: [
            zeile({
              start_id: "w2",
              place: null,
              group: "unranked" as const,
              status: "aborted" as const,
              abort_reason: "dsq" as const,
              display_name: "Egon Abbruch",
              club: "SV Abbruch",
              score_text: null,
            }),
          ],
        },
      ],
    };
    const sieger = szenen.winners as SzeneVon<"winners">;
    zeige(beispielFeed({ scenes: [{ ...sieger, ranking }] }));
    const region = screen.getByRole("region", { name: "Ergebnisliste" });
    expect(region.querySelectorAll("[data-rang]")).toHaveLength(1);
    expect(within(region).getByText("Ohne Platzierung")).toBeVisible();
    expect(within(region).queryByText("Weitere Plätze")).toBeNull();
    expect(within(region).getByText("Egon Abbruch")).toBeVisible();
    expect(within(region).getByText("SV Abbruch")).toBeVisible();
    expect(within(region).getByText("disqualifiziert")).toBeVisible();
  });

  it("Live-Wertung: Abbruch nach „Feuer“ mit Platz und Kennzeichen, ohne Platz mit Begründung", () => {
    const live = szenen.live_ranking as SzeneVon<"live_ranking">;
    zeige(beispielFeed({ scenes: [{ ...live, ranking: abbruchRangliste() }] }));
    const liste = screen.getByRole("region", { name: "Live-Wertung" });
    const zeilen = Array.from(liste.querySelectorAll<HTMLElement>("[data-gruppe]"));
    const egon = zeilen.find((z) => z.textContent?.includes("Egon Abbruch"));
    if (!egon) throw new Error("Egon fehlt");
    // Unter den Plätzen, mit Platz und gewertetem Ergebnis, nicht im Block „Ohne Platzierung“
    expect(egon).not.toHaveAttribute("data-ohne-platz");
    expect(within(egon).getByText("2")).toBeVisible();
    expect(within(egon).getByText("25,10")).toBeVisible();
    const marke = within(egon).getByText("Abbruch (AB)");
    expect(marke.className).toMatch(/abbruchMarke/);
    expect(marke.className).not.toMatch(/(^|\s)\S*abbruch(\s|$)/);
    // Ohne Platz: Kennzeichen und Begründung vom Server
    const ohne = Array.from(liste.querySelectorAll<HTMLElement>("[data-ohne-platz]"));
    expect(ohne).toHaveLength(2);
    const [rita, karl] = ohne as [HTMLElement, HTMLElement];
    expect(within(rita).getByText("Abbruch (AB)")).toBeVisible();
    expect(
      within(rita).getByText("Ergebnis nicht vergleichbar: Serie 2 unvollständig erfasst"),
    ).toBeVisible();
    expect(within(karl).getByText("disqualifiziert")).toBeVisible();
    // Gleichstand mit dem Wort des Servers
    expect(within(liste).getAllByText("gleiches Ergebnis: Stechen")).toHaveLength(2);
  });

  it("Ergebnisliste: Abbruch nach „Feuer“ auf dem Podest mit Kennzeichen, nicht gold", () => {
    const sieger = szenen.winners as SzeneVon<"winners">;
    zeige(beispielFeed({ scenes: [{ ...sieger, ranking: abbruchRangliste() }] }));
    const region = screen.getByRole("region", { name: "Ergebnisliste" });
    const stufen = Array.from(region.querySelectorAll<HTMLElement>("[data-rang]"));
    expect(stufen).toHaveLength(3);
    const zweiter = region.querySelector<HTMLElement>('[data-rang="2"]');
    if (!zweiter) throw new Error("Platz 2 fehlt");
    expect(within(zweiter).getByText("Egon Abbruch")).toBeVisible();
    expect(within(zweiter).getByText("Abbruch (AB)")).toBeVisible();
    expect(zweiter).toHaveAttribute("data-abbruch");
    expect(zweiter).not.toHaveAttribute("data-erster");
    // Ohne Platz: eigener Block mit Kennzeichen und Begründung
    expect(within(region).getByText("Ohne Platzierung")).toBeVisible();
    expect(within(region).getByText("Rita Fern")).toBeVisible();
    expect(
      within(region).getByText("Ergebnis nicht vergleichbar: Serie 2 unvollständig erfasst"),
    ).toBeVisible();
  });

  it("Abbruch-Kennzeichen: Text des Servers vor dem eigenen, eigener nur als Rückfall", () => {
    const basis = abbruchRangliste();
    const gruppe = basis.groups[0];
    if (!gruppe) throw new Error("Testdaten");
    const ranking = {
      ...basis,
      groups: [
        {
          ...gruppe,
          rows: gruppe.rows.map((z) =>
            z.start_id === "f2" ? { ...z, abort_label: "aufgegeben (DSB)" } : z,
          ),
          unplaced: gruppe.unplaced.map((z) => ({ ...z, abort_label: undefined })),
        },
      ],
    };
    const live = szenen.live_ranking as SzeneVon<"live_ranking">;
    zeige(beispielFeed({ scenes: [{ ...live, ranking }] }));
    const liste = screen.getByRole("region", { name: "Live-Wertung" });
    expect(within(liste).getByText("aufgegeben (DSB)")).toBeVisible();
    // Ohne `abort_label`: bisheriger Text zum Grund
    expect(within(liste).getByText("Abbruch (AB)")).toBeVisible();
    expect(within(liste).getByText("disqualifiziert")).toBeVisible();
  });

  it("Startliste: Grund des Abbruchs statt „abgebrochen“, Kennziffer, kein Hinweis auf Katalog-Abweichung", () => {
    const start = szenen.startlist as SzeneVon<"startlist">;
    const startlist = {
      ...start.startlist,
      competition_code: "1201",
      deviates: true,
      deviations: ["Sollzeit 60 s statt 50 s"],
      starts: [
        ...start.startlist.starts,
        {
          ...(start.startlist.starts[0] as FeedPerson),
          start_id: "p3",
          start_number: 9,
          status: "aborted" as const,
          abort_reason: "dns" as const,
        },
      ],
    };
    zeige(beispielFeed({ scenes: [{ ...start, startlist }] }));
    const liste = screen.getByRole("region", { name: "Startliste" });
    expect(within(liste).getByRole("heading", { name: "1201Pistole bis 9 mm" })).toBeVisible();
    expect(within(liste).queryByText(/Katalog/)).toBeNull();
    expect(within(liste).queryByText("Sollzeit 60 s statt 50 s")).toBeNull();
    expect(within(liste).getByText("nicht angetreten")).toBeVisible();
    expect(within(liste).queryByText("abgebrochen")).toBeNull();
  });

  it("Standanzeige: Ablauf mit Positionen, Serien-Übersicht, Am Schießstand, Als Nächstes", () => {
    zeige(beispielFeed({ scenes: [szenen.range] }));
    const stand = screen.getByRole("region", { name: "Schießstand Kurzwaffe 25 m" });
    expect(within(stand).getByRole("heading", { name: "1201Pistole bis 9 mm" })).toBeVisible();
    expect(within(stand).queryByText(/Katalog/)).toBeNull();
    expect(within(stand).queryByText(/Sollzeit 60 s statt 50 s/)).toBeNull();
    expect(within(stand).getByRole("list", { name: "Parcours" })).toBeVisible();
    expect(within(stand).getByText("Es zählen 2 von 3 Serien")).toBeVisible();
    expect(within(stand).getByText("gestrichen – zählt nicht")).toBeVisible();
    expect(within(stand).getByText("Am Schießstand")).toBeVisible();
    expect(within(stand).getByText("frei")).toBeVisible();
    expect(within(stand).getByText("Dora Nächste")).toBeVisible();
  });

  it("QA G-7: „Als Nächstes“ je Wettbewerb mit Kennziffer, Schützenstand bzw. Platz beschriftet, wer gerade schießt", () => {
    zeige(beispielFeed({ scenes: [szenen.range] }));
    const stand = screen.getByRole("region", { name: "Schießstand Kurzwaffe 25 m" });
    const naechste = within(stand)
      .getByRole("heading", { name: "Als Nächstes" })
      .closest("section") as HTMLElement;
    expect(within(naechste).getByText("Durchgang 4 · 14:20")).toBeVisible();
    expect(within(naechste).getByText("1001")).toBeVisible();
    expect(within(naechste).getByText("Schützenstand")).toBeVisible();
    expect(within(naechste).getByText("Reihenfolge")).toBeVisible();
    expect(within(naechste).getByText("Platz")).toBeVisible();
    const dora = within(naechste).getByText("Dora Nächste").closest("[data-zeile]") as HTMLElement;
    expect(within(dora).getByText("3")).toBeVisible();
    const karl = within(naechste).getByText("Karl Weiß").closest("[data-zeile]") as HTMLElement;
    expect(karl).toHaveAttribute("data-besetzt");
    expect(
      within(karl).getByText("gerade am Schießstand Flinte 15 m, Schützenstand 1"),
    ).toBeVisible();
    expect(within(naechste).getByText("+ 2 weitere")).toBeVisible();
  });

  it("Standanzeige: ohne `current` keine Hervorhebung und kein Fortschritt", () => {
    zeige(beispielFeed({ scenes: [szenen.range] }));
    const stand = screen.getByRole("region", { name: "Schießstand Kurzwaffe 25 m" });
    expect(within(stand).queryByText(/^Jetzt/)).toBeNull();
    expect(within(stand).queryByText(/^\d+ von \d+$/)).toBeNull();
    expect(stand.querySelector("[aria-current]")).toBeNull();
    // Uhrzeit des nächsten Durchgangs aus `starts_at_local`
    expect(within(stand).getByText("Durchgang 4 · 14:20")).toBeVisible();
  });

  it("Standanzeige: hebt die laufende Serie hervor und zeigt je Schützenstand den Fortschritt", () => {
    const basis = szenen.range as SzeneVon<"range">;
    const [ablauf] = basis.range.procedures;
    if (!ablauf) throw new Error("Testdaten ohne Ablauf");
    const auf = (lane: number, nr: number): FeedPerson => ({
      start_id: `s${lane}`,
      start_number: 10 + lane,
      display_name: `Schütze ${lane}`,
      club: null,
      class_short: "S",
      competition_id: ablauf.competition_id,
      competition_name: ablauf.competition_name,
      attempt: 1,
      status: nr === 1 ? "called" : "captured",
      lane,
      heat_number: null,
      heat_starts_at: null,
      heat_starts_at_local: null,
    });
    const szene: SzeneVon<"range"> = {
      ...basis,
      range: {
        ...basis.range,
        procedures: [
          {
            ...ablauf,
            current: [
              { lane: 1, start_id: "s1", section_id: "parcours", series_number: 2 },
              { lane: 2, start_id: "s2", section_id: "praezision", series_number: 3 },
            ],
          },
        ],
        lanes: [
          {
            lane: 1,
            start: auf(1, 2),
            progress: {
              section_id: "parcours",
              series_done: 1,
              series_total: 2,
              complete: false,
              section_number: 1,
              section_count: 2,
              series_done_overall: 1,
              series_total_overall: 5,
            },
          },
          {
            lane: 2,
            start: auf(2, 3),
            progress: {
              section_id: "praezision",
              series_done: 2,
              series_total: 3,
              complete: false,
              section_number: 2,
              section_count: 2,
              series_done_overall: 4,
              series_total_overall: 5,
            },
          },
        ],
      },
    };
    zeige(beispielFeed({ scenes: [szene] }));
    const stand = screen.getByRole("region", { name: "Schießstand Kurzwaffe 25 m" });
    // Parcours (Positionen): aktive Karte und Textzeile
    const parcours = within(stand).getByRole("list", { name: "Parcours" });
    expect(within(parcours).getAllByRole("listitem")[1]).toHaveAttribute("aria-current", "step");
    expect(within(stand).getByText("Position 2: Schützenstand 1")).toBeVisible();
    // Präzision (Serien): Kachel mit Marke
    const praezision = within(stand).getByRole("list", { name: "Präzision" });
    const serien = within(praezision).getAllByRole("listitem");
    expect(serien[2]).toHaveAttribute("aria-current", "step");
    expect(within(serien[2] as HTMLElement).getByText("Jetzt · Schützenstand 2")).toBeVisible();
    // Fortschritt je Bahn
    const bahn1 = within(stand).getByText("Schütze 1").closest("[data-zeile]") as HTMLElement;
    expect(bahn1).toHaveTextContent("Parcours · Position 2 von 2");
    const bahn2 = within(stand).getByText("Schütze 2").closest("[data-zeile]") as HTMLElement;
    expect(bahn2).toHaveTextContent("Präzision · Serie 3 von 3");
  });

  it("Hinweis und Ruhe zeigen den Text des Servers", () => {
    const { unmount } = zeige(beispielFeed({ scenes: [szenen.notice] }));
    expect(screen.getByRole("heading", { name: "Siegerehrung um 16:00 Uhr" })).toBeVisible();
    unmount();
    zeige(beispielFeed({ scenes: [szenen.idle] }));
    expect(screen.getByText("Gleich geht es los")).toBeVisible();
  });

  it("Ruhe wiederholt den Turniernamen nicht als Unterzeile", () => {
    const ruhe = szenen.idle as SzeneVon<"idle">;
    zeige(beispielFeed({ scenes: [{ ...ruhe, heading: "Herbstpokal 2026" }] }));
    const region = screen.getByRole("region", { name: szenen.idle.title });
    expect(within(region).getAllByText("Herbstpokal 2026")).toHaveLength(1);
  });

  it("zeigt Warnungen und den Hinweis „vorläufig“ nur, wenn der Feed sie liefert", () => {
    const { unmount } = zeige(beispielFeed());
    expect(screen.queryByRole("alert")).toBeNull();
    unmount();
    zeige(
      beispielFeed({
        warnings: [
          { code: "backup_stick_missing", message: "Sicherungs-Stick fehlt" },
          { code: "provisional", message: "Ergebnisse vorläufig – Einspruchsfrist läuft." },
        ],
      }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Sicherungs-Stick fehlt");
    expect(screen.getByText("Ergebnisse vorläufig – Einspruchsfrist läuft.")).toBeVisible();
  });

  it("wechselt die Szenen nach ihrer Dauer; eine einzelne steht still", () => {
    vi.useFakeTimers();
    zeige(
      beispielFeed({
        scenes: [
          { ...szenen.notice, seconds: 5 },
          { ...szenen.idle, seconds: 5 },
        ],
      }),
    );
    expect(screen.getByText("Siegerehrung um 16:00 Uhr")).toBeInTheDocument();
    expect(screen.getByText(/1\/2 · als Nächstes Ruhe/)).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(5100));
    expect(screen.getByText("Gleich geht es los")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(5100));
    expect(screen.getByText("Siegerehrung um 16:00 Uhr")).toBeInTheDocument();
  });

  it("ohne Verbindung bleibt der letzte Stand stehen, mit Marke", () => {
    zeige(beispielFeed(), { getrenntSeit: new Date("2026-11-22T12:40:00Z") });
    expect(screen.getByText("Anna Beispiel")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(/Verbindung unterbrochen seit \d\d:\d\d/);
    // Die Marke steht im Fuß und überdeckt den Turniernamen nicht.
    expect(screen.getByRole("status").closest("footer")).not.toBeNull();
  });

  it("sagt bei fehlender Zuweisung, was zu tun ist", () => {
    zeige(null, { sperre: "nicht_gefunden" }, { art: "geraet" });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Dieser Bildschirm ist keiner Anzeige zugewiesen – in Anzeige → Bildschirm zuweisen.",
    );
  });

  it("nimmt das Thema aus dem Feed, nicht vom Gerät", () => {
    zeige(beispielFeed({ theme: "light" }));
    const buehne = document.querySelector<HTMLElement>('[style*="--sh-bg"]');
    expect(buehne?.style.getPropertyValue("--sh-bg").toUpperCase()).toBe("#F2F4F7");
    expect(buehne?.style.colorScheme).toBe("light");
  });
});

describe("Bildschirm: Gleichstand nach Server, Wörter je Verband, Übung", () => {
  it("Höchstergebnis: geteilter Platz entschieden, dezent erklärt, ohne Aufforderung", () => {
    const basis = rangliste();
    const geteilt = (start_id: string, display_name: string) =>
      zeile({
        start_id,
        place: 1,
        tied: true,
        tie_unresolved: false,
        tie_reason: "max_score",
        tie_note: "Höchstergebnis: gleicher Platz",
        display_name,
        score_text: "400 Ringe",
      });
    const ranking = {
      ...basis,
      tie_word: "Ergebnisgleichheit",
      federation: "dsb",
      groups: [
        {
          class_id: "k1",
          class_name: "Schützenklasse",
          class_short: "S",
          more: 0,
          unplaced: [],
          rows: [geteilt("h1", "Hanna Höchst"), geteilt("h2", "Ida Höchst")],
        },
      ],
    };
    for (const szene of [szenen.live_ranking, szenen.winners] as const) {
      const { unmount } = zeige(
        beispielFeed({ scenes: [{ ...szene, ranking }] as Feed["scenes"] }),
      );
      const region = screen.getByRole("region", { name: szene.title });
      const hinweise = within(region).getAllByText("Höchstergebnis: gleicher Platz");
      expect(hinweise).toHaveLength(2);
      for (const hinweis of hinweise) {
        expect(hinweis).toHaveAttribute("data-geteilt", "entschieden");
        expect(hinweis.className).not.toMatch(/(^|\s)\S*gleichstand(\s|$)/);
      }
      expect(within(region).queryByText(/Stechen|manuell/)).toBeNull();
      unmount();
    }
  });

  it("Höchstergebnis mit Stechen: offen, mit dem Text des Servers; unbekannter Grund mit Text", () => {
    const basis = rangliste();
    const ranking = {
      ...basis,
      tie_word: "Ringgleichheit",
      federation: "dsb",
      groups: [
        {
          class_id: "k1",
          class_name: "Schützenklasse",
          class_short: "S",
          more: 0,
          unplaced: [],
          rows: [
            zeile({
              start_id: "m1",
              place: 1,
              tied: true,
              tie_unresolved: true,
              needs_shootoff: true,
              tie_reason: "max_score_shootoff",
              tie_note: "Höchstergebnis auf Platz 1: Stechen",
              display_name: "Hanna Höchst",
              score_text: "400 Ringe",
            }),
            zeile({
              start_id: "m2",
              place: 3,
              tied: true,
              tie_unresolved: false,
              // Grund, den diese Version nicht kennt: der Hinweis des Servers erscheint trotzdem.
              tie_reason: "neu_vom_server" as never,
              tie_note: "Neuer Hinweis vom Server",
              display_name: "Ida Neu",
              score_text: "399 Ringe",
            }),
          ],
        },
      ],
    };
    const live = szenen.live_ranking as SzeneVon<"live_ranking">;
    zeige(beispielFeed({ scenes: [{ ...live, ranking }] }));
    const region = screen.getByRole("region", { name: live.title });
    expect(within(region).getByText("Höchstergebnis auf Platz 1: Stechen")).toHaveAttribute(
      "data-geteilt",
      "offen",
    );
    expect(within(region).getByText("Neuer Hinweis vom Server")).toHaveAttribute(
      "data-geteilt",
      "entschieden",
    );
  });

  it("durch die Kette entschieden: kein geteilter Platz, Hinweis nur in der Live-Wertung", () => {
    const ranking = getrenntRangliste();
    // Das Wort vorn fällt auf dem Schirm weg; der volle Wortlaut (`tie_note_long`) steht im `title`.
    const hinweis = "entschieden nach: letzte Zehnerserie";

    const live = szenen.live_ranking as SzeneVon<"live_ranking">;
    const { unmount } = zeige(beispielFeed({ scenes: [{ ...live, ranking }] }));
    const liste = screen.getByRole("region", { name: live.title });
    const hinweise = within(liste).getAllByText(hinweis);
    expect(hinweise).toHaveLength(2);
    for (const h of hinweise) {
      expect(h).toHaveAttribute("data-geteilt", "getrennt");
      expect(h).toHaveAttribute(
        "title",
        "Ringgleichheit, entschieden nach: letzte Zehnerserie, dann rückwärts in 10-Schuss-Serien",
      );
    }
    expect(within(liste).queryByText("geteilt")).toBeNull();
    expect(within(liste).queryByText(/Stechen|manuell/)).toBeNull();
    // Trefferzählung/ohne Zehner: nichts von Zehnern auf dem Schirm
    expect(liste.textContent).not.toMatch(/\d\s*(Innen)?[Zz]ehner\b/);
    unmount();

    // Ergebnisliste: Podest ohne den langen Hinweis, Plätze 2 und 3 nicht geteilt
    const sieger = szenen.winners as SzeneVon<"winners">;
    zeige(beispielFeed({ scenes: [{ ...sieger, ranking }] }));
    const ergebnis = screen.getByRole("region", { name: sieger.title });
    expect(within(ergebnis).queryByText(/entschieden nach/)).toBeNull();
    expect(within(ergebnis).queryByText(/Stechen|manuell|geteilt/)).toBeNull();
  });

  it("Hinweis „Stechen“ nur bei offenem Gleichstand, nicht nach dem Wortlaut von tie_note", () => {
    const basis = rangliste();
    const ranking = {
      ...basis,
      tie_word: "Ringgleichheit",
      groups: [
        {
          class_id: "k1",
          class_name: "Schützenklasse",
          class_short: "S",
          more: 0,
          unplaced: [],
          rows: [
            // Stechen schon geschossen: entschieden, auch wenn der alte Text noch dasteht
            zeile({
              start_id: "e1",
              place: 1,
              tied: false,
              needs_shootoff: false,
              tie_unresolved: false,
              tie_reason: null,
              tie_note: "Ringgleichheit auf Platz 1: Stechen",
              display_name: "Erich Entschieden",
            }),
            zeile({
              start_id: "o1",
              place: 2,
              tied: true,
              tie_unresolved: true,
              tie_reason: "missing_data",
              tie_note: null,
              display_name: "Olga Offen",
            }),
          ],
        },
      ],
    };
    const live = szenen.live_ranking as SzeneVon<"live_ranking">;
    zeige(beispielFeed({ scenes: [{ ...live, ranking }] }));
    const liste = screen.getByRole("region", { name: "Live-Wertung" });
    expect(within(liste).queryByText(/Stechen/)).toBeNull();
    expect(within(liste).getByText("Ringgleichheit: manuell entscheiden")).toHaveAttribute(
      "data-geteilt",
      "offen",
    );
  });

  it("Startliste: Wörter des Verbands, Kennzeichen des Abbruchs vom Server, Rückfall ohne", () => {
    const start = szenen.startlist as SzeneVon<"startlist">;
    const [erste] = start.startlist.starts as [FeedPerson];
    const startlist = {
      ...start.startlist,
      competition_code: "1.10",
      federation: "probe",
      starts: [
        erste,
        {
          ...erste,
          start_id: "a1",
          start_number: 7,
          status: "aborted" as const,
          abort_reason: "dnf" as const,
          abort_label: "abgebrochen",
        },
        {
          ...erste,
          start_id: "a2",
          start_number: 8,
          status: "aborted" as const,
          abort_reason: "dsq" as const,
          abort_label: null,
        },
      ],
    };
    zeige(beispielFeed({ scenes: [{ ...start, startlist }] }), {}, QUELLE, BEGRIFFE);
    const liste = screen.getByRole("region", { name: "Startliste" });
    expect(within(liste).getAllByText(/^Block 3 · \d\d:\d\d · Platz-am-Stand 2$/)).toHaveLength(3);
    expect(within(liste).getByText("abgebrochen")).toBeVisible();
    expect(within(liste).queryByText("Abbruch (AB)")).toBeNull();
    expect(within(liste).getByText("disqualifiziert")).toBeVisible();
    expect(within(liste).getByText("1.10")).toHaveAttribute("title", "Kennzahl 1.10");
  });

  it("Standanzeige und Live-Wertung: Wörter des Verbands aus `federation`", () => {
    const basis = szenen.range as SzeneVon<"range">;
    const [ablauf] = basis.range.procedures;
    if (!ablauf) throw new Error("Testdaten ohne Ablauf");
    const szene: SzeneVon<"range"> = {
      ...basis,
      range: {
        ...basis.range,
        procedures: [
          {
            ...ablauf,
            federation: "probe",
            current: [{ lane: 2, start_id: "p3", section_id: "praezision", series_number: 1 }],
            // Trefferaufnahme nach der 1. Serie der Präzision (Serien-Übersicht)
            sections: ablauf.sections.map((abschnitt) =>
              abschnitt.id === "praezision"
                ? {
                    ...abschnitt,
                    series: abschnitt.series.map((serie) => ({
                      ...serie,
                      hit_review_after: serie.number === 1,
                    })),
                  }
                : abschnitt,
            ),
          },
        ],
      },
    };
    const { unmount } = zeige(beispielFeed({ scenes: [szene] }), {}, QUELLE, BEGRIFFE);
    const stand = screen.getByRole("region", { name: "Schießstand Kurzwaffe 25 m" });
    expect(within(stand).getByText("Disziplin am Stand")).toBeVisible();
    expect(within(stand).getByText("Am Stand")).toBeVisible();
    expect(within(stand).getByText("Es zählen 2 von 3 Runden")).toBeVisible();
    expect(within(stand).getByText("Runde 3")).toBeVisible();
    expect(within(stand).getByText("Jetzt · Platz-am-Stand 2")).toBeVisible();
    expect(within(stand).getAllByText("Auswertung").length).toBeGreaterThan(0);
    expect(within(stand).getByText("Block 4 · 14:20")).toBeVisible();
    expect(within(stand).getByText("Platz-am-Stand")).toBeVisible();
    expect(
      within(stand).getByText("gerade am Schießstand Flinte 15 m, Platz-am-Stand 1"),
    ).toBeVisible();
    unmount();

    const live = szenen.live_ranking as SzeneVon<"live_ranking">;
    zeige(
      beispielFeed({ scenes: [{ ...live, ranking: { ...rangliste(), federation: "PROBE" } }] }),
      {},
      QUELLE,
      BEGRIFFE,
    );
    expect(screen.getByText("Runde 1")).toBeInTheDocument();
  });

  it("ohne Begriffe vom Server: die bisherigen Wörter (Rückfall)", () => {
    const start = szenen.startlist as SzeneVon<"startlist">;
    zeige(
      beispielFeed({
        scenes: [{ ...start, startlist: { ...start.startlist, federation: "dsb" } }],
      }),
    );
    const liste = screen.getByRole("region", { name: "Startliste" });
    expect(within(liste).getByText(/Durchgang 3 · \d\d:\d\d · Schützenstand 2/)).toBeVisible();
  });

  it("Übungsturnier: Kennzeichen „Übung“ im Kopf, sonst nicht", () => {
    const { unmount } = zeige(beispielFeed());
    expect(screen.queryByText("Übung")).toBeNull();
    unmount();
    const feed = beispielFeed();
    zeige({ ...feed, header: { ...feed.header, is_practice: true } });
    const marke = screen.getByText("Übung");
    expect(marke).toBeVisible();
    const kopf = marke.closest("header") as HTMLElement;
    expect(marke).toHaveAttribute("title", expect.stringMatching(/Übungsturnier/));
    expect(within(kopf).getByRole("heading", { level: 1, name: "Herbstpokal 2026" })).toBeVisible();
  });
});
