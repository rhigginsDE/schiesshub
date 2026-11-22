import { describe, expect, it } from "vitest";
import type { Bahn, Durchgang } from "../anmeldung/api";
import {
  belegungDurchgang,
  bestimmeStand,
  durchgangErledigt,
  ersterAufrufbarer,
  freieBahnen,
  freieBahnenDurchgang,
  hauptAktion,
  lokalesDatum,
  lokaleUhrzeit,
  naechsterWartenderDurchgang,
  vorschlagDatum,
  zeitpunktAusEingabe,
} from "./logik";
import { stationStart } from "./testdaten";

function durchgang(id: string, beginn: string, teil: Partial<Durchgang> = {}): Durchgang {
  const start = new Date(beginn);
  return {
    id,
    range_id: "r",
    number: 1,
    starts_at: start.toISOString(),
    ends_at: new Date(start.getTime() + 15 * 60_000).toISOString(),
    booked: 0,
    capacity: 4,
    ...teil,
  };
}

describe("Stand wählen", () => {
  const staende = [{ id: "a" }, { id: "b" }];
  it("nimmt die gespeicherte Wahl, solange es den Stand gibt", () => {
    expect(bestimmeStand(staende, { t1: "b" }, "t1")).toBe("b");
    expect(bestimmeStand(staende, { t1: "weg" }, "t1")).toBeNull();
    expect(bestimmeStand(staende, { t2: "b" }, "t1")).toBeNull();
  });
  it("nimmt bei genau einem Stand diesen", () => {
    expect(bestimmeStand([{ id: "a" }], null, "t1")).toBe("a");
  });
});

describe("Zeit", () => {
  it("rechnet lokale Eingaben in einen ISO-Zeitpunkt und zurück", () => {
    const iso = zeitpunktAusEingabe("2026-12-05", "09:30");
    expect(iso).not.toBeNull();
    expect(lokalesDatum(iso as string)).toBe("2026-12-05");
    expect(lokaleUhrzeit(iso as string)).toBe("09:30");
  });
  it("lehnt unvollständige Eingaben ab", () => {
    expect(zeitpunktAusEingabe("", "09:30")).toBeNull();
    expect(zeitpunktAusEingabe("2026-12-05", "9")).toBeNull();
  });
  it("schlägt heute vor, wenn es im Turnierzeitraum liegt, sonst den ersten Tag", () => {
    expect(vorschlagDatum("2026-12-05", "2026-12-06", new Date(2026, 11, 6, 10))).toBe(
      "2026-12-06",
    );
    expect(vorschlagDatum("2026-12-05", "2026-12-06", new Date(2026, 10, 22, 10))).toBe(
      "2026-12-05",
    );
  });
});

describe("Belegung", () => {
  const d = durchgang("d1", "2026-12-05T10:00:00");
  const starts = [
    stationStart({ start_id: "s1", heat_id: "d1", lane: 2 }),
    stationStart({
      start_id: "s2",
      heat_id: "d1",
      lane: 3,
      status: "aborted",
      abort_reason: "dns",
    }),
    stationStart({ start_id: "s3", heat_id: "d2", lane: 1 }),
  ];
  it("zeigt je Bahn den Start; abgebrochene geben den Platz frei", () => {
    const belegung = belegungDurchgang(d, starts);
    expect(belegung.map((b) => b.start?.start_id ?? null)).toEqual([null, "s1", null, null]);
  });
  it("zählt beim Umsetzen den eigenen Platz als frei", () => {
    expect(freieBahnenDurchgang(d, starts)).toEqual([1, 3, 4]);
    expect(freieBahnenDurchgang(d, starts, "s1")).toEqual([1, 2, 3, 4]);
  });
  it("findet die freien Bahnen des Stands", () => {
    const bahnen: Bahn[] = [
      { lane: 1, start: stationStart({ start_id: "x", status: "called", lane: 1 }) },
      { lane: 2, start: null },
    ];
    expect(freieBahnen(bahnen)).toEqual([2]);
  });
});

describe("Durchgänge", () => {
  const frueh = durchgang("d1", "2026-12-05T10:00:00", { number: 1 });
  const spaet = durchgang("d2", "2026-12-05T10:15:00", { number: 2 });
  it("nimmt den frühesten Durchgang mit Wartenden", () => {
    const starts = [
      stationStart({ start_id: "a", heat_id: "d1", status: "captured" }),
      stationStart({ start_id: "b", heat_id: "d2" }),
    ];
    expect(naechsterWartenderDurchgang([spaet, frueh], starts)?.id).toBe("d2");
    expect(naechsterWartenderDurchgang([spaet, frueh], [])).toBeNull();
  });
  it("gilt als erledigt, wenn er vorbei ist und niemand mehr wartet oder schießt", () => {
    const danach = new Date("2026-12-05T11:00:00");
    expect(durchgangErledigt(frueh, [], danach)).toBe(true);
    expect(durchgangErledigt(frueh, [stationStart({ start_id: "a", heat_id: "d1" })], danach)).toBe(
      false,
    );
    expect(durchgangErledigt(frueh, [], new Date("2026-12-05T10:05:00"))).toBe(false);
  });
});

describe("Hauptaktion", () => {
  const d = durchgang("d1", "2026-12-05T10:00:00");
  it("ist „Nächste aufrufen“, sobald Wettbewerbe nach Reihenfolge laufen", () => {
    expect(hauptAktion(true, d)).toEqual({ art: "naechste" });
  });
  it("ist sonst der nächste Durchgang mit Wartenden, oder keine", () => {
    expect(hauptAktion(false, d)).toEqual({ art: "durchgang", durchgang: d });
    expect(hauptAktion(false, null)).toEqual({ art: "keine" });
  });
  it("überspringt beim Aufrufen auf eine Bahn, wer schon auf einer steht", () => {
    const wartende = [
      stationStart({ start_id: "a", entry_id: "e1" }),
      stationStart({ start_id: "b", entry_id: "e2" }),
    ];
    expect(ersterAufrufbarer(wartende, new Set(["e1"]))?.start_id).toBe("b");
    expect(ersterAufrufbarer(wartende, new Set(["e1", "e2"]))).toBeNull();
  });
});
