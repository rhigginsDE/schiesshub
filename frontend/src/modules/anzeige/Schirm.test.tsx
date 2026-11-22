import { MantineProvider } from "@mantine/core";
import { act, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { theme } from "../../theme";
import { SchirmAnsicht } from "./schirm/Schirm";
import type { FeedQuelle, FeedZustand } from "./schirm/useFeed";
import { beispielFeed, szenen } from "./testdaten";
import type { Feed, SzeneVon } from "./typen";

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

  it("Standanzeige: Ablauf mit Positionen, Serien-Übersicht, Am Stand, Als Nächstes", () => {
    zeige(beispielFeed({ scenes: [szenen.range] }));
    const stand = screen.getByRole("region", { name: "25-m-Stand" });
    expect(within(stand).getByText("1201")).toBeVisible();
    expect(within(stand).getByText("Abweichend vom Sporthandbuch")).toBeVisible();
    expect(within(stand).getByText("Sollzeit 60 s statt 50 s")).toBeVisible();
    expect(within(stand).getByRole("list", { name: "Parcours" })).toBeVisible();
    expect(within(stand).getByText("Es zählen 2 von 3 Serien")).toBeVisible();
    expect(within(stand).getByText("gestrichen – zählt nicht")).toBeVisible();
    expect(within(stand).getByText("Am Stand")).toBeVisible();
    expect(within(stand).getByText("frei")).toBeVisible();
    expect(within(stand).getByText("Durchgang 4")).toBeVisible();
    expect(within(stand).getByText("Dora Nächste")).toBeVisible();
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
