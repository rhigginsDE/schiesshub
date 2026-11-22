import { describe, expect, it } from "vitest";
import { bestimmeTurnier, sortiereTurniere } from "../../components/useAktivesTurnier";
import type { Turnier } from "../turnier/typen";
import type { Anmeldung, Start } from "./api";
import {
  bestaetigungsArt,
  betragVorschau,
  gebuchteStarts,
  kennzahlen,
  loeschbar,
  mengenHinweis,
  naechsteStartnummer,
  nochBuchbar,
  ohneStartNachfragen,
  sperreFuer,
  statusAnzeige,
  stornoSperre,
  sucheAnmeldungen,
  summe,
} from "./logik";
import { belegteBahnen, kommendeDurchgaenge } from "./PlatzWahl";

const W = { fee_first_cents: 800, fee_repeat_cents: 500, multi_start: true, max_starts: 3 };

function start(teil: Partial<Start> = {}): Start {
  return {
    id: "s",
    entry_id: "e",
    called_at: null,
    on_lane: false,
    competition_id: "w1",
    attempt: 1,
    fee_cents: 800,
    status: "registered",
    abort_reason: null,
    queue_position: 1,
    heat_id: null,
    lane: null,
    created_at: "2026-11-22T10:00:00Z",
    updated_at: "2026-11-22T10:00:00Z",
    ...teil,
  };
}

function anmeldung(nr: number, name: string, teil: Partial<Anmeldung> = {}): Anmeldung {
  return {
    id: `a${nr}`,
    tournament_id: "t",
    start_number: nr,
    class_id: "k",
    person: { id: `p${nr}`, name, display_name: name, club: "SV Tell Musterstadt" },
    starts: [],
    fee_total_cents: 0,
    created_at: "2026-11-22T10:00:00Z",
    updated_at: "2026-11-22T10:00:00Z",
    ...teil,
  };
}

describe("Betragsvorschau (wie start_fee im Server)", () => {
  it("erster Start zum Startgeld, jeder weitere als Nachkauf", () => {
    expect(betragVorschau(W, 0, 1)).toEqual({ cents: 800, erste: 1, nachkauf: 0 });
    expect(betragVorschau(W, 0, 3)).toEqual({ cents: 1800, erste: 1, nachkauf: 2 });
  });

  it("mit schon gebuchten Starts nur Nachkäufe", () => {
    expect(betragVorschau(W, 1, 2)).toEqual({ cents: 1000, erste: 0, nachkauf: 2 });
  });

  it("nichts gewählt: 0", () => {
    expect(betragVorschau(W, 2, 0)).toEqual({ cents: 0, erste: 0, nachkauf: 0 });
  });

  it("summiert Zeilen", () => {
    const gesamt = summe([betragVorschau(W, 0, 2), { cents: 600, erste: 1, nachkauf: 0 }]);
    expect(gesamt).toEqual({ cents: 1900, erste: 2, nachkauf: 1 });
  });
});

describe("Meldung nach dem Speichern", () => {
  it("unterscheidet Anmeldung, Anmeldung ohne Start, Nachbuchen und reine Änderung", () => {
    expect(bestaetigungsArt(true, 2)).toBe("angemeldet");
    expect(bestaetigungsArt(true, 0)).toBe("ohne_start");
    expect(bestaetigungsArt(false, 1)).toBe("gebucht");
    expect(bestaetigungsArt(false, 0)).toBe("geaendert");
  });
});

describe("Hinweis unter der Anzahl", () => {
  it("zieht die gerade gewählten Starts ab", () => {
    expect(mengenHinweis(W, 0, 0)).toEqual({ art: "noch", anzahl: 3 });
    expect(mengenHinweis(W, 0, 2)).toEqual({ art: "noch", anzahl: 1 });
    expect(mengenHinweis(W, 2, 0)).toEqual({ art: "noch", anzahl: 1 });
  });

  it("nennt die Grenze, sobald „+“ gesperrt ist", () => {
    expect(mengenHinweis(W, 1, 2)).toEqual({ art: "grenze", grenze: 3 });
    expect(mengenHinweis(W, 0, 3)).toEqual({ art: "grenze", grenze: 3 });
    expect(mengenHinweis({ multi_start: false, max_starts: 3 }, 0, 1)).toEqual({
      art: "grenze",
      grenze: 1,
    });
  });
});

describe("Grenzen und Zulassung", () => {
  const klasse = { id: "k1", name: "Jugendklasse 1" };

  it("ohne Mehrfachstart genau ein Start", () => {
    expect(nochBuchbar({ multi_start: false, max_starts: 3 }, 0)).toBe(1);
    expect(sperreFuer({ ...W, multi_start: false, class_ids: [] }, klasse, 1)).toEqual({
      art: "voll",
      grenze: 1,
    });
  });

  it("Höchstzahl erreicht", () => {
    expect(nochBuchbar(W, 2)).toBe(1);
    expect(sperreFuer({ ...W, class_ids: [] }, klasse, 3)).toEqual({ art: "voll", grenze: 3 });
  });

  it("Klasse nicht zugelassen, mit Namen begründet", () => {
    expect(sperreFuer({ ...W, class_ids: ["k2"] }, klasse, 0)).toEqual({
      art: "klasse",
      klasse: "Jugendklasse 1",
    });
  });

  it("eingeschränkter Wettbewerb braucht erst eine Klasse", () => {
    expect(sperreFuer({ ...W, class_ids: ["k2"] }, null, 0)).toEqual({ art: "ohne_klasse" });
    expect(sperreFuer({ ...W, class_ids: [] }, null, 0)).toBeNull();
  });

  it("zählt alle gebuchten Starts im Wettbewerb, auch abgebrochene", () => {
    const a = anmeldung(1, "A", {
      starts: [
        start(),
        start({ id: "s2", status: "aborted", abort_reason: "dns" }),
        start({ id: "s3", competition_id: "w2" }),
      ],
    });
    expect(gebuchteStarts(a, "w1")).toBe(2);
    expect(gebuchteStarts(null, "w1")).toBe(0);
  });
});

describe("Statusanzeige", () => {
  it("Texte und Farben je Status", () => {
    expect(statusAnzeige(start())).toMatchObject({ schluessel: "angemeldet", ton: "neutral" });
    expect(statusAnzeige(start({ status: "called", lane: 2 }))).toEqual({
      schluessel: "aufgerufen",
      ton: "info",
      bahn: 2,
    });
    expect(statusAnzeige(start({ status: "final" }))).toMatchObject({ ton: "gruen" });
    expect(statusAnzeige(start({ status: "aborted", abort_reason: "dns" }))).toMatchObject({
      schluessel: "dns",
      ton: "warn",
    });
    expect(statusAnzeige(start({ status: "aborted", abort_reason: "dsq" }))).toMatchObject({
      schluessel: "dsq",
      ton: "krit",
    });
  });

  it("stornieren nur, solange nicht aufgerufen", () => {
    expect(stornoSperre(start())).toBeNull();
    expect(stornoSperre(start({ status: "called" }))).toBe("aufgerufen");
    expect(stornoSperre(start({ status: "captured" }))).toBe("geschossen");
    expect(stornoSperre(start({ status: "aborted", abort_reason: "dns" }))).toBe("abgebrochen");
  });

  it("löschen nur, wenn alle Starts noch angemeldet sind", () => {
    expect(loeschbar(anmeldung(1, "A", { starts: [start()] }))).toBe(true);
    expect(loeschbar(anmeldung(1, "A", { starts: [start({ status: "called" })] }))).toBe(false);
  });
});

describe("Anmeldungen", () => {
  const liste = [
    anmeldung(1, "Markus Brandt"),
    anmeldung(2, "Jürgen Maier"),
    anmeldung(12, "Sabine Köhler", {
      person: { id: "p12", name: "Sabine Köhler", display_name: null, club: "SSV Hubertus" },
    }),
  ];

  it("nächste freie Startnummer ab der ersten", () => {
    expect(naechsteStartnummer(liste, 1)).toBe(3);
    expect(naechsteStartnummer(liste, 10)).toBe(10);
    expect(naechsteStartnummer([], 0)).toBe(1);
  });

  it("Suche: genaue Startnummer zuerst, dann Name und Verein ohne Akzente", () => {
    expect(sucheAnmeldungen(liste, "2").map((a) => a.start_number)).toEqual([2, 12]);
    expect(sucheAnmeldungen(liste, "kohler").map((a) => a.start_number)).toEqual([12]);
    expect(sucheAnmeldungen(liste, "maier tell").map((a) => a.start_number)).toEqual([2]);
    expect(sucheAnmeldungen(liste, " ")).toHaveLength(3);
  });

  it("Kennzahlen", () => {
    const a = anmeldung(1, "A", { starts: [start(), start({ id: "s2" })], fee_total_cents: 1300 });
    expect(kennzahlen([a, anmeldung(2, "B")])).toEqual({ schuetzen: 2, starts: 2, cents: 1300 });
  });
});

describe("Zeitplan", () => {
  it("belegte Bahnen je Durchgang ohne abgebrochene Starts", () => {
    const belegt = belegteBahnen([
      { heat_id: "d1", lane: 1, status: "registered" },
      { heat_id: "d1", lane: 2, status: "aborted" },
      { heat_id: null, lane: null, status: "registered" },
    ] as never);
    expect([...(belegt.get("d1") ?? [])]).toEqual([1]);
  });

  it("nur Durchgänge, die noch nicht vorbei sind", () => {
    const d = (id: string, von: string, bis: string) =>
      ({
        id,
        number: 1,
        starts_at: von,
        ends_at: bis,
        booked: 0,
        capacity: 4,
        range_id: "r",
      }) as const;
    const kommend = kommendeDurchgaenge(
      [
        d("b", "2026-11-22T11:00:00Z", "2026-11-22T11:15:00Z"),
        d("a", "2026-11-22T09:00:00Z", "2026-11-22T09:15:00Z"),
      ],
      new Date("2026-11-22T10:00:00Z"),
    );
    expect(kommend.map((x) => x.id)).toEqual(["b"]);
  });
});

describe("Turnierwahl", () => {
  const turnier = (id: string, status: Turnier["status"], datum = "2026-12-05") =>
    ({ id, name: id, status, date_from: datum, date_to: datum }) as Turnier;

  it("gespeicherte Wahl hat Vorrang", () => {
    const liste = [turnier("a", "active"), turnier("b", "draft")];
    expect(bestimmeTurnier(liste, "b")).toEqual({ turnier: liste[1], automatisch: false });
  });

  it("genau ein aktives Turnier wird von selbst genommen", () => {
    const liste = [turnier("a", "active"), turnier("b", "draft")];
    expect(bestimmeTurnier(liste, "weg")).toEqual({ turnier: liste[0], automatisch: true });
  });

  it("mehrere oder keine aktiven: wählen", () => {
    expect(
      bestimmeTurnier([turnier("a", "active"), turnier("b", "active")], null).turnier,
    ).toBeNull();
    expect(bestimmeTurnier([turnier("a", "draft")], null).turnier).toBeNull();
  });

  it("Auswahl: aktive zuerst, dann jüngstes Datum", () => {
    const liste = sortiereTurniere([
      turnier("alt", "closed", "2025-01-01"),
      turnier("entwurf", "draft", "2026-01-01"),
      turnier("aktiv", "active", "2025-06-01"),
      turnier("entwurf2", "draft", "2026-06-01"),
    ]);
    expect(liste.map((t) => t.id)).toEqual(["aktiv", "entwurf2", "entwurf", "alt"]);
  });
});

describe("ohneStartNachfragen", () => {
  it("fragt nur, wenn danach kein Start da wäre und einer buchbar ist", () => {
    expect(ohneStartNachfragen(0, 0, 2)).toBe(true);
    // Ein neuer oder ein schon gebuchter Start: keine Rückfrage
    expect(ohneStartNachfragen(0, 1, 2)).toBe(false);
    expect(ohneStartNachfragen(1, 0, 2)).toBe(false);
    // Nichts buchbar (keine Wettbewerbe, alles gesperrt): Die Frage hilft nicht
    expect(ohneStartNachfragen(0, 0, 0)).toBe(false);
  });
});
