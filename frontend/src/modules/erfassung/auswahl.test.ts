import { describe, expect, it } from "vitest";
import type { StationStart } from "../anmeldung/api";
import {
  bahnenAmStand,
  bestimmeStand,
  direktOeffnen,
  kachelStatus,
  naechsterOffener,
  namenAus,
  suche,
  uebrige,
  vollstaendigkeit,
  wartende,
} from "./auswahl";

const R = "r-15";

function start(teil: Partial<StationStart> & { start_id: string }): StationStart {
  return {
    entry_id: `e-${teil.start_id}`,
    start_number: 1,
    display_name: "M. Brandt",
    club: null,
    class_id: "k",
    class_short: "S",
    competition_id: "w",
    competition_name: "Selbstladeflinte",
    range_id: R,
    attempt: 1,
    status: "registered",
    abort_reason: null,
    queue_position: null,
    lane: null,
    heat_id: null,
    heat_number: null,
    heat_starts_at: null,
    called_at: null,
    ...teil,
  } as StationStart;
}

const starts = [
  start({ start_id: "a", start_number: 3, status: "called", lane: 1 }),
  start({ start_id: "b", start_number: 4, status: "captured", lane: 2 }),
  start({ start_id: "c", start_number: 5, status: "final", lane: 2 }),
  start({ start_id: "d", start_number: 8, queue_position: 2, display_name: "Jürgen Maier" }),
  start({ start_id: "e", start_number: 7, queue_position: 1 }),
  start({ start_id: "f", start_number: 9, status: "aborted", abort_reason: "dns" }),
  start({ start_id: "g", start_number: 30, range_id: "anderer" }),
];

describe("Startauswahl", () => {
  it("zeigt je Bahn den aufgerufenen oder gerade erfassten Start", () => {
    const bahnen = bahnenAmStand(starts, R, 3);
    expect(bahnen.map((b) => b.start?.start_id ?? null)).toEqual(["a", "b", null]);
  });

  it("Wartende in der Reihenfolge, übrige ohne Bahn", () => {
    expect(wartende(starts, R).map((s) => s.start_id)).toEqual(["e", "d"]);
    const belegung = bahnenAmStand(starts, R, 3);
    expect(uebrige(starts, R, belegung).map((s) => s.start_id)).toEqual(["c", "f"]);
  });

  it("Status der Kachel", () => {
    expect(kachelStatus(starts[0] as StationStart)).toBe("offen");
    expect(kachelStatus(starts[0] as StationStart, "a")).toBe("in_erfassung");
    expect(kachelStatus(starts[1] as StationStart)).toBe("erfasst");
    expect(kachelStatus(starts[2] as StationStart, "c")).toBe("abgeschlossen");
  });

  it("sucht Startnummern im ganzen Turnier und Namen ohne Akzente", () => {
    expect(suche(starts, "3", new Map(), true).map((s) => s.start_id)).toEqual(["a", "g"]);
    expect(suche(starts, "jurgen", new Map(), true).map((s) => s.start_id)).toEqual(["d"]);
    const namen = namenAus([{ entry_id: "e-e", full_name: "Sabine Köhler" } as never]);
    expect(suche(starts, "köhler", namen, true).map((s) => s.start_id)).toEqual(["e"]);
    expect(suche(starts, "5", new Map(), true)).toEqual([]);
    expect(suche(starts, "5", new Map(), false).map((s) => s.start_id)).toEqual(["c"]);
  });

  it("schlägt nach dem Abschluss den nächsten offenen Start vor", () => {
    expect(naechsterOffener(starts, R, 3, "a")?.start_id).toBe("b");
    expect(naechsterOffener(starts.slice(2), R, 3, null)?.start_id).toBe("e");
  });

  it("merkt den Stand je Turnier", () => {
    const staende = [{ id: "x" }, { id: "y" }];
    expect(bestimmeStand(staende, { t: "y" }, "t")).toBe("y");
    expect(bestimmeStand(staende, {}, "t")).toBeNull();
    expect(bestimmeStand([{ id: "x" }], {}, "t")).toBe("x");
  });
});

describe("Suche mit mehreren Starts derselben Person", () => {
  const bernd = [
    start({ start_id: "a", start_number: 2, competition_id: "w1", competition_name: "4401" }),
    start({ start_id: "b", start_number: 2, competition_id: "w2", competition_name: "4403" }),
    start({ start_id: "c", start_number: 21 }),
  ];

  it("öffnet nie automatisch den ersten von mehreren Treffern", () => {
    const treffer = suche(bernd, "2", new Map(), false);
    expect(treffer.map((s) => s.start_id)).toEqual(["a", "b", "c"]);
    expect(direktOeffnen(treffer)).toBeNull();
  });

  it("öffnet direkt nur bei genau einem Treffer", () => {
    expect(direktOeffnen(suche(bernd, "21", new Map(), false))?.start_id).toBe("c");
  });
});

describe("Vollständigkeit je Wettbewerb", () => {
  it("zählt erledigte Starts und nennt die offenen", () => {
    const liste = [
      start({ start_id: "1", start_number: 3, status: "final" }),
      start({ start_id: "2", start_number: 5, status: "aborted" }),
      start({ start_id: "3", start_number: 9, status: "captured" }),
      start({ start_id: "4", start_number: 1, status: "registered" }),
      start({ start_id: "5", start_number: 2, status: "final", competition_id: "w2" }),
    ];
    const stand = vollstaendigkeit(liste, [{ competition_id: "w2" }]);
    expect(stand.map((w) => [w.competitionId, w.gesamt, w.abgeschlossen, w.abgebrochen])).toEqual([
      ["w", 4, 1, 1],
      ["w2", 1, 1, 0],
    ]);
    expect(stand[0]?.offen.map((s) => s.start_number)).toEqual([1, 9]);
    expect(stand[1]?.zuPruefen).toBe(1);
  });
});
