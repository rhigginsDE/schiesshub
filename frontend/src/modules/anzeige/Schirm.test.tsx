import { MantineProvider } from "@mantine/core";
import { act, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { theme } from "../../theme";
import { SchirmAnsicht } from "./schirm/Schirm";
import type { FeedQuelle, FeedZustand } from "./schirm/useFeed";
import { beispielFeed, rangliste, szenen, zeile } from "./testdaten";
import type { Feed, FeedPerson, SzeneVon } from "./typen";

const QUELLE: FeedQuelle = { art: "anzeige", id: "a1" };

function zustand(feed: Feed | null, teil: Partial<FeedZustand> = {}) {
  return { feed, laedt: false, sperre: null, getrenntSeit: null, versatzMs: 0, ...teil };
}

function mitTheme(kind: ReactNode) {
  return <MantineProvider theme={theme}>{kind}</MantineProvider>;
}

function zeige(feed: Feed | null, teil: Partial<FeedZustand> = {}, quelle = QUELLE) {
  return render(mitTheme(<SchirmAnsicht zustand={zustand(feed, teil)} quelle={quelle} />));
}

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

  it("Siegerliste: Podest je Klasse", () => {
    zeige(beispielFeed({ scenes: [szenen.winners] }));
    const sieger = screen.getByRole("region", { name: "Siegerliste" });
    expect(within(sieger).getByText("Schützenklasse")).toBeVisible();
    expect(within(sieger).getByText("Clara Probe")).toBeVisible();
    expect(sieger.querySelectorAll('[data-rang="1"]')).toHaveLength(2);
    // Zwei geteilte Zweite stehen gleich hoch, auch wenn einer rechts (an Stelle 3) steht.
    expect(sieger.querySelectorAll('[data-stufe="2"]')).toHaveLength(2);
    expect(sieger.querySelectorAll('[data-stufe="3"]')).toHaveLength(0);
  });

  it("Startliste: Durchgang, Bahn, Status, weitere", () => {
    zeige(beispielFeed({ scenes: [szenen.startlist] }));
    const liste = screen.getByRole("region", { name: "Startliste" });
    expect(within(liste).getByText(/Durchgang 3 · \d\d:\d\d · Bahn 2/)).toBeVisible();
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
    expect(within(egon).getByText("aufgegeben")).toBeVisible();
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

  it("Siegerliste: Abgebrochene nie auf dem Podest, sondern mit Grund danach", () => {
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
    const region = screen.getByRole("region", { name: "Siegerliste" });
    expect(region.querySelectorAll("[data-rang]")).toHaveLength(1);
    expect(within(region).getByText("Ohne Platzierung")).toBeVisible();
    expect(within(region).queryByText("Weitere Plätze")).toBeNull();
    expect(within(region).getByText("Egon Abbruch")).toBeVisible();
    expect(within(region).getByText("SV Abbruch")).toBeVisible();
    expect(within(region).getByText("disqualifiziert")).toBeVisible();
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

  it("Standanzeige: Ablauf mit Positionen, Serien-Übersicht, Am Stand, Als Nächstes", () => {
    zeige(beispielFeed({ scenes: [szenen.range] }));
    const stand = screen.getByRole("region", { name: "25-m-Stand" });
    expect(within(stand).getByRole("heading", { name: "1201Pistole bis 9 mm" })).toBeVisible();
    expect(within(stand).queryByText(/Katalog/)).toBeNull();
    expect(within(stand).queryByText(/Sollzeit 60 s statt 50 s/)).toBeNull();
    expect(within(stand).getByRole("list", { name: "Parcours" })).toBeVisible();
    expect(within(stand).getByText("Es zählen 2 von 3 Serien")).toBeVisible();
    expect(within(stand).getByText("gestrichen – zählt nicht")).toBeVisible();
    expect(within(stand).getByText("Am Stand")).toBeVisible();
    expect(within(stand).getByText("frei")).toBeVisible();
    expect(within(stand).getByText("Dora Nächste")).toBeVisible();
  });

  it("QA G-7: „Als Nächstes“ je Wettbewerb mit Kennziffer, Bahn bzw. Platz beschriftet, wer gerade schießt", () => {
    zeige(beispielFeed({ scenes: [szenen.range] }));
    const stand = screen.getByRole("region", { name: "25-m-Stand" });
    const naechste = within(stand)
      .getByRole("heading", { name: "Als Nächstes" })
      .closest("section") as HTMLElement;
    expect(within(naechste).getByText("Durchgang 4 · 14:20")).toBeVisible();
    expect(within(naechste).getByText("1001")).toBeVisible();
    expect(within(naechste).getByText("Bahn")).toBeVisible();
    expect(within(naechste).getByText("Reihenfolge")).toBeVisible();
    expect(within(naechste).getByText("Platz")).toBeVisible();
    const dora = within(naechste).getByText("Dora Nächste").closest("[data-zeile]") as HTMLElement;
    expect(within(dora).getByText("3")).toBeVisible();
    const karl = within(naechste).getByText("Karl Weiß").closest("[data-zeile]") as HTMLElement;
    expect(karl).toHaveAttribute("data-besetzt");
    expect(within(karl).getByText("gerade auf Bahn 1, 15-m-Stand")).toBeVisible();
    expect(within(naechste).getByText("+ 2 weitere")).toBeVisible();
  });

  it("Standanzeige: ohne `current` keine Hervorhebung und kein Fortschritt", () => {
    zeige(beispielFeed({ scenes: [szenen.range] }));
    const stand = screen.getByRole("region", { name: "25-m-Stand" });
    expect(within(stand).queryByText(/^Jetzt/)).toBeNull();
    expect(within(stand).queryByText(/^\d+ von \d+$/)).toBeNull();
    expect(stand.querySelector("[aria-current]")).toBeNull();
    // Uhrzeit des nächsten Durchgangs aus `starts_at_local`
    expect(within(stand).getByText("Durchgang 4 · 14:20")).toBeVisible();
  });

  it("Standanzeige: hebt die laufende Serie hervor und zeigt je Bahn den Fortschritt", () => {
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
    const stand = screen.getByRole("region", { name: "25-m-Stand" });
    // Parcours (Positionen): aktive Karte und Textzeile
    const parcours = within(stand).getByRole("list", { name: "Parcours" });
    expect(within(parcours).getAllByRole("listitem")[1]).toHaveAttribute("aria-current", "step");
    expect(within(stand).getByText("Position 2: Bahn 1")).toBeVisible();
    // Präzision (Serien): Kachel mit Marke
    const praezision = within(stand).getByRole("list", { name: "Präzision" });
    const serien = within(praezision).getAllByRole("listitem");
    expect(serien[2]).toHaveAttribute("aria-current", "step");
    expect(within(serien[2] as HTMLElement).getByText("Jetzt · Bahn 2")).toBeVisible();
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
