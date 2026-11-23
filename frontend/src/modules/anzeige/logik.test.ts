import { describe, expect, it } from "vitest";
import { csvIstLeer, exportPfad } from "../../components/ExportKnoepfe";
import { ereignisseZumNachladen, passtEreignis } from "./ereignisse";
import {
  abbruchText,
  alsPosition,
  bahnFortschritt,
  feedUhrzeit,
  gesamtTeile,
  gleichstandHinweis,
  gleichstandWort,
  hauptSerie,
  istPlatzierterAbbruch,
  laengstesWort,
  laufendeSerien,
  mitErgebnis,
  mitWeiterenPlaetzen,
  naechsteEintraege,
  naechsteSeiten,
  podestReihenfolge,
  podestStufe,
  ranglistenEintraege,
  ranglistenSeiten,
  serienAnzahl,
  serienBreite,
  serienPassen,
  serienWert,
  siegerAufteilung,
  uhrzeitInZone,
  uhrzeitLokal,
} from "./format";
import {
  indexNachWechsel,
  inSeiten,
  naechsterIndex,
  restSekunden,
  seiteZurZeit,
  teilTakt,
  zeilenProSeite,
} from "./rotation";
import { startlistenZeilen } from "./schirm/Startliste";
import { abbruchRangliste, beispielFeed, rangliste, szenen, zeile } from "./testdaten";
import type { SzeneVon } from "./typen";
import {
  type Entwurf,
  fehlerZu,
  gleicherEntwurf,
  neueSzene,
  neueSzenenId,
  speicherSchritte,
  uebrigeFehler,
  vorschauAnfrage,
} from "./verwaltung/entwurf";

describe("Szenenwechsel", () => {
  const a = { scene_id: "live", part: 1 };
  const b = { scene_id: "live", part: 2 };
  const c = { scene_id: "start", part: 1 };

  it("bleibt bei derselben Seite, wenn es sie im neuen Feed noch gibt", () => {
    expect(indexNachWechsel([a, b, c], [c, a, b], 1)).toBe(2);
  });

  it("behält die Stelle, wenn die Seite fehlt, sonst von vorn", () => {
    expect(indexNachWechsel([a, b, c], [a, c], 1)).toBe(1);
    expect(indexNachWechsel([a, b, c], [a], 2)).toBe(0);
    expect(indexNachWechsel([a], [], 0)).toBe(0);
  });

  it("geht im Kreis; eine einzelne Szene steht still", () => {
    expect(naechsterIndex(0, 3)).toBe(1);
    expect(naechsterIndex(2, 3)).toBe(0);
    expect(naechsterIndex(0, 1)).toBe(0);
  });
});

describe("Zeitscheiben und Seiten", () => {
  const takt = { start: 1000, dauer: 30000 };

  it("verteilt Seiten gleichmäßig auf die Dauer und beginnt danach von vorn", () => {
    expect(seiteZurZeit(takt, 1000, 3)).toBe(0);
    expect(seiteZurZeit(takt, 11000, 3)).toBe(1);
    expect(seiteZurZeit(takt, 30999, 3)).toBe(2);
    expect(seiteZurZeit(takt, 31000, 3)).toBe(0);
    expect(seiteZurZeit(takt, 50000, 1)).toBe(0);
  });

  it("teilt eine Zeitscheibe in gleiche Teile", () => {
    expect(teilTakt(takt, 1, 3)).toEqual({ start: 11000, dauer: 10000 });
    expect(teilTakt(takt, 0, 1)).toBe(takt);
  });

  it("zählt die Restsekunden aufgerundet", () => {
    expect(restSekunden(takt, 1000)).toBe(30);
    expect(restSekunden(takt, 30500)).toBe(1);
    expect(restSekunden(takt, 99999)).toBe(0);
  });

  it("berechnet Zeilen je Seite aus der Höhe; ohne Messung null", () => {
    expect(zeilenProSeite(800, 72, 8)).toBe(10);
    expect(zeilenProSeite(50, 72, 8)).toBe(1);
    expect(zeilenProSeite(0, 72)).toBeNull();
    expect(zeilenProSeite(800, 0)).toBeNull();
  });

  it("teilt Listen in Seiten, immer mindestens eine", () => {
    expect(inSeiten([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
    expect(inSeiten([1, 2], null)).toEqual([[1, 2]]);
    expect(inSeiten([], 3)).toEqual([[]]);
  });
});

describe("Server-Ereignisse", () => {
  it("löst Muster mit * gegen die bekannten Namen auf", () => {
    expect(passtEreignis("start.*", "start.booked")).toBe(true);
    expect(passtEreignis("start.*", "starts.x")).toBe(false);
    const namen = ereignisseZumNachladen(
      ["display.changed", "heat.*", "neu.ereignis"],
      ["heat.created", "heat.deleted", "start.booked"],
    );
    expect(namen).toEqual(["display.changed", "heat.created", "heat.deleted", "neu.ereignis"]);
  });

  it("deckt die Liste des Backends ab", () => {
    const namen = ereignisseZumNachladen(beispielFeed().reload_on);
    expect(namen).toContain("result.finalized");
    expect(namen).toContain("start.status_changed");
    expect(namen).toContain("backup.status");
  });

  it("nimmt die genauen Namen aus dem Feed, auch unbekannte", () => {
    const namen = ereignisseZumNachladen(["start.called", "display.changed", "start.called"]);
    expect(namen).toEqual(["display.changed", "start.called"]);
  });

  it("fällt ohne `reload_on` auf die bekannte Liste zurück", () => {
    expect(ereignisseZumNachladen(undefined, ["b", "a"])).toEqual(["a", "b"]);
    expect(ereignisseZumNachladen(null)).toContain("result.finalized");
  });
});

describe("Standanzeige: laufende Serie und Fortschritt", () => {
  const stand = szenen.range.kind === "range" ? szenen.range.range : null;
  if (!stand) throw new Error("Testdaten ohne Stand");
  const [ablauf] = stand.procedures;
  if (!ablauf) throw new Error("Testdaten ohne Ablauf");
  const person = stand.lanes[1]?.start;
  if (!person) throw new Error("Testdaten ohne Person");
  const mitLauf = {
    ...ablauf,
    current: [
      { lane: 3, start_id: "x3", section_id: "praezision", series_number: 2 },
      { lane: 1, start_id: "x1", section_id: "praezision", series_number: 2 },
      { lane: 2, start_id: "x2", section_id: "praezision", series_number: 1 },
    ],
  };

  it("gruppiert laufende Serien je Abschnitt nach Bahnen und wählt die häufigste", () => {
    const laufend = laufendeSerien(mitLauf, "praezision");
    expect([...laufend]).toEqual([
      [1, [2]],
      [2, [1, 3]],
    ]);
    expect(hauptSerie(laufend)).toBe(2);
    expect(laufendeSerien(mitLauf, "parcours").size).toBe(0);
    expect(hauptSerie(new Map())).toBeNull();
    expect(laufendeSerien({ ...ablauf, current: [] }, "praezision").size).toBe(0);
  });

  it("zeigt je Bahn die laufende Serie aus `current`, sonst aus `progress`", () => {
    const start = { ...person, start_id: "x1", competition_id: ablauf.competition_id };
    const bahn = {
      lane: 1,
      start,
      progress: {
        section_id: "praezision",
        series_done: 1,
        series_total: 3,
        complete: false,
        section_number: 2,
        section_count: 2,
        series_done_overall: 3,
        series_total_overall: 5,
      },
    };
    expect(bahnFortschritt(bahn, [mitLauf])).toEqual({
      serie: 2,
      serien: 3,
      fertig: false,
      abschnitt: "Präzision",
      positionen: false,
    });
    // Ohne `current`: aus dem Erfassungsfortschritt
    expect(bahnFortschritt(bahn, [{ ...ablauf, current: [] }])).toMatchObject({ serie: 2 });
    // Positionen im Parcours
    const parcours = {
      ...bahn,
      progress: { ...bahn.progress, section_id: "parcours", series_done: 0, series_total: 2 },
    };
    expect(bahnFortschritt(parcours, [{ ...ablauf, current: [] }])).toMatchObject({
      serie: 1,
      serien: 2,
      positionen: true,
    });
    // Fertig erfasst
    const fertig = { ...bahn, progress: { ...bahn.progress, series_done: 3, complete: true } };
    expect(bahnFortschritt(fertig, [mitLauf])).toMatchObject({ fertig: true });
    // Ohne Fortschritt und ohne `current`: nichts, wie bisher
    expect(bahnFortschritt({ lane: 1, start, progress: null }, [ablauf])).toBeNull();
    expect(bahnFortschritt({ lane: 1, start: null }, [mitLauf])).toBeNull();
  });
});

describe("Zeiten aus dem Feed", () => {
  it("liest die Ortszeit aus `*_local`, ohne umzurechnen", () => {
    expect(uhrzeitLokal("2027-03-06T10:05:00+01:00", "de")).toBe("10:05");
    expect(uhrzeitLokal("2027-07-06T23:30:00-04:00", "de")).toBe("23:30");
    expect(uhrzeitLokal(null, "de")).toBeNull();
    expect(feedUhrzeit("2027-03-06T10:05:00+01:00", "2027-03-06T09:05:00Z", "de")).toBe("10:05");
    expect(feedUhrzeit(null, null, "de")).toBeNull();
  });

  it("stellt die Uhr in der Zone des Turniers, unbekannte Zone nach Geräteuhr", () => {
    const zeit = new Date("2026-11-22T12:42:00Z");
    expect(uhrzeitInZone(zeit, "Europe/Berlin", "de")).toBe("13:42");
    expect(uhrzeitInZone(zeit, "UTC", "de")).toBe("12:42");
    expect(uhrzeitInZone(zeit, "Mars/Olympus", "de")).toMatch(/^\d{2}:\d{2}$/);
  });
});

describe("Formatierung", () => {
  it("zeigt Ringe, sonst Zeit mit Zuschlag in Hundertsteln mit Dezimalkomma", () => {
    const basis = {
      section_id: "a",
      number: 1,
      struck: false,
      status: "normal",
      rings: null,
      time_cs: null,
      standing: null,
      total_cs: null,
    };
    expect(serienWert({ ...basis, rings: 95 }, "de")).toBe("95");
    expect(serienWert({ ...basis, time_cs: 1290, total_cs: 2290 }, "de")).toBe("22,90");
    expect(serienWert({ ...basis, time_cs: 1420 }, "de")).toBe("14,20");
    expect(serienWert(basis, "de")).toBe("–");
    expect(serienWert(undefined, "de")).toBe("–");
  });

  it("Zehntelwertung: Ringe als Text behalten ihre Nachkommastelle, mit Dezimalkomma", () => {
    const basis = {
      section_id: "a",
      number: 1,
      struck: false,
      status: "normal",
      rings: null,
      time_cs: null,
      standing: null,
      total_cs: null,
    };
    expect(serienWert({ ...basis, rings: "20.1" }, "de")).toBe("20,1");
    expect(serienWert({ ...basis, rings: "104.0" }, "de")).toBe("104,0");
    expect(serienWert({ ...basis, rings: "0.3" }, "de")).toBe("0,3");
    expect(serienWert({ ...basis, rings: "104.7" }, "en")).toBe("104.7");
  });
});

describe("Gleichstand (Stechen, von Hand)", () => {
  it("folgt den Angaben des Servers", () => {
    expect(gleichstandHinweis({ tied: true, needs_shootoff: true, tie_note: "x" })).toBe("stechen");
    expect(gleichstandHinweis({ tied: true, tie_reason: "shootoff" })).toBe("stechen");
    expect(gleichstandHinweis({ tied: true, tie_reason: "manual", tie_note: "x" })).toBe("manuell");
    expect(gleichstandHinweis({ tied: true, tie_reason: "missing_data" })).toBe("manuell");
    // Feed: kein `tie_reason`, nur der Hinweistext.
    expect(
      gleichstandHinweis({
        tied: true,
        needs_shootoff: false,
        tie_note: "Gleichstand nach Sportordnung manuell entscheiden",
      }),
    ).toBe("manuell");
  });

  it("liest das formelle Wort (tie_word) vorn aus dem Hinweis des Servers", () => {
    expect(gleichstandWort({ tie_note: "Ringgleichheit auf Platz 1: Stechen" })).toBe(
      "Ringgleichheit",
    );
    expect(
      gleichstandWort({
        tie_note:
          "Treffergleichheit: nach Sportordnung manuell entscheiden (nächstes Kriterium: x)",
      }),
    ).toBe("Treffergleichheit");
    expect(gleichstandWort({ tie_note: "gleiches Ergebnis nicht auflösbar: Angaben fehlen" })).toBe(
      "gleiches Ergebnis",
    );
    // Ein mitgeliefertes Wort (RankingOut.tie_word) hat Vorrang.
    expect(
      gleichstandWort({ tie_note: "Ringgleichheit auf Platz 1: Stechen" }, "Treffergleichheit"),
    ).toBe("Treffergleichheit");
    // Alter Text ohne erkennbares Wort, kein Hinweis: kein Wort
    expect(
      gleichstandWort({ tie_note: "Gleichstand nach Sportordnung manuell entscheiden (x: y)" }),
    ).toBeNull();
    expect(gleichstandWort({ tie_note: null })).toBeNull();
  });

  it("ein geteilter Platz ohne offene Frage (z. B. Fallscheibe) bleibt ohne Hinweis", () => {
    expect(gleichstandHinweis({ tied: true, needs_shootoff: false, tie_note: null })).toBeNull();
    expect(gleichstandHinweis({ tied: false, needs_shootoff: false })).toBeNull();
  });

  it("richtet die Serienspalten nach dem längsten Wert und lässt sie weg, wenn sie nicht passen", () => {
    expect(serienBreite(rangliste(), "de")).toBe(9);
    const zeit = rangliste();
    const serie = zeit.groups[0]?.rows[0]?.series[0];
    if (serie) Object.assign(serie, { rings: null, total_cs: 12345 });
    expect(serienBreite(zeit, "de")).toBe(12.3);
    expect(serienPassen(4, 12.3, false)).toBe(true);
    expect(serienPassen(4, 12.3, true)).toBe(false);
    expect(serienPassen(3, 9, true)).toBe(true);
  });

  it("trennt die Einheit vom Gesamtergebnis", () => {
    expect(gesamtTeile("183 Ringe", "Ringe")).toEqual({ wert: "183", einheit: "Ringe" });
    expect(gesamtTeile("147,15 s", "s")).toEqual({ wert: "147,15", einheit: "s" });
    expect(gesamtTeile("DNF", "s")).toEqual({ wert: "DNF", einheit: null });
    expect(gesamtTeile(null, "s")).toEqual({ wert: "–", einheit: null });
  });

  it("zählt Serienspalten und baut Einträge mit Klassenköpfen", () => {
    const liste = rangliste();
    expect(serienAnzahl(liste)).toBe(2);
    const eintraege = ranglistenEintraege(liste);
    expect(eintraege.map((e) => e.art)).toEqual([
      "klasse",
      "zeile",
      "zeile",
      "zeile",
      "mehr",
      "klasse",
      "zeile",
    ]);
  });

  it("lässt keinen Klassenkopf allein unten auf einer Seite", () => {
    const seiten = ranglistenSeiten(ranglistenEintraege(rangliste()), 5);
    expect(seiten.map((seite) => seite.map((e) => e.art))).toEqual([
      ["klasse", "zeile", "zeile", "zeile", "mehr"],
      ["klasse", "zeile"],
    ]);
    const enger = ranglistenSeiten(ranglistenEintraege(rangliste()), 6);
    expect(enger[0]?.at(-1)?.art).toBe("mehr");
    expect(enger[1]?.[0]?.art).toBe("klasse");
  });

  it("wiederholt den Klassenkopf, wenn eine Klasse auf der nächsten Seite weitergeht", () => {
    const seiten = ranglistenSeiten(ranglistenEintraege(rangliste()), 3);
    expect(seiten.map((seite) => seite.map((e) => e.art))).toEqual([
      ["klasse", "zeile", "zeile"],
      ["klasse", "zeile", "mehr"],
      ["klasse", "zeile"],
    ]);
    const weiter = seiten[1]?.[0];
    expect(weiter?.art === "klasse" && weiter.fortsetzung).toBe(true);
    expect(seiten[2]?.[0]?.art === "klasse" && seiten[2][0].fortsetzung).toBeFalsy();
    const schluessel = seiten.flat().map((e) => e.schluessel);
    expect(new Set(schluessel).size).toBe(schluessel.length);
  });

  it("Podesthöhe nach dem Platz: geteilte Erste stehen beide oben", () => {
    expect(podestStufe(1, 2)).toBe(1);
    expect(podestStufe(2, 3)).toBe(2);
    expect(podestStufe(5, 3)).toBe(3);
    expect(podestStufe(null, 2)).toBe(2);
  });

  it("verteilt eine kurze Startliste gleichmäßig auf die Spalten", () => {
    expect(startlistenZeilen(8, 2, 7)).toBe(4);
    expect(startlistenZeilen(8, 2, 30)).toBe(8);
    expect(startlistenZeilen(8, 1, 3)).toBe(3);
    expect(startlistenZeilen(null, 2, 7)).toBeNull();
  });

  it("ordnet das Podest 2 – 1 – 3", () => {
    expect(podestReihenfolge(["a", "b", "c"]).map((x) => x.eintrag)).toEqual(["b", "a", "c"]);
    expect(podestReihenfolge(["a"])).toEqual([{ eintrag: "a", rang: 1 }]);
  });

  it("wandelt Positionen des Feeds für den Positions-Ablauf", () => {
    expect(
      alsPosition({
        nr: 6,
        distance_m: 15,
        target: 2,
        text: "",
        stances: [{ haltung: "kniend", hand: "beidhaendig", text: "" }],
      }),
    ).toEqual({
      nr: 6,
      distanz_m: 15,
      scheibe: 2,
      anschlaege: [{ haltung: "kniend", hand: "beidhaendig" }],
    });
  });
});

describe("Entwurf der Verwaltung", () => {
  const konfig = {
    scenes: [],
    name_mode: "as_person" as const,
    show_club: "as_person" as const,
    show_provisional_note: true,
    theme: "dark" as const,
  };
  const server: Entwurf = { tournament_id: "t1", device_id: null, konfig };

  it("vergibt freie Szenen-IDs", () => {
    expect(neueSzenenId("startlist", [])).toBe("startliste");
    expect(neueSzenenId("startlist", ["startliste", "startliste-2"])).toBe("startliste-3");
    const stand = neueSzene("range", [], "r1", "Hinweis");
    expect(stand).toMatchObject({ id: "stand", kind: "range", range_id: "r1", next_count: 4 });
  });

  it("erkennt Änderungen normalisiert (leere Laufzeile = keine)", () => {
    expect(gleicherEntwurf(server, { ...server, konfig: { ...konfig, ticker: "  " } })).toBe(true);
    expect(gleicherEntwurf(server, { ...server, konfig: { ...konfig, theme: "light" } })).toBe(
      false,
    );
  });

  it("speichert Turnier und Inhalt in einer Anfrage, das Gerät danach", () => {
    const neu: Entwurf = {
      tournament_id: "t2",
      device_id: "g1",
      konfig: { ...konfig, ticker: "Hallo" },
    };
    expect(speicherSchritte(server, neu)).toEqual([
      {
        art: "anzeige",
        aenderung: {
          tournament_id: "t2",
          config: expect.objectContaining({ ticker: "Hallo", scenes: [] }),
        },
      },
      { art: "geraet", wert: "g1" },
    ]);
    expect(speicherSchritte(server, { ...server, tournament_id: null })).toEqual([
      { art: "anzeige", aenderung: { tournament_id: null } },
    ]);
    expect(speicherSchritte(server, { ...server, device_id: "g2" })).toEqual([
      { art: "geraet", wert: "g2" },
    ]);
    expect(speicherSchritte(server, server)).toEqual([]);
  });

  it("schickt für die Vorschau den normalisierten Entwurf mit Turnier", () => {
    const anfrage = vorschauAnfrage({ ...server, konfig: { ...konfig, ticker: "  " } });
    expect(anfrage.tournament_id).toBe("t1");
    expect(anfrage.config.ticker).toBeNull();
  });

  it("ordnet Feldfehler des Servers zu", () => {
    const felder = [
      { feld: "scenes.1.competition_ids.0", meldung: "Wettbewerb nicht gefunden" },
      { feld: "config.scenes.1.rows", meldung: "zu groß" },
      { feld: "irgendwas", meldung: "Allgemein" },
    ];
    expect(fehlerZu(felder, "scenes.1.competition_ids")).toBe("Wettbewerb nicht gefunden");
    expect(fehlerZu(felder, "scenes.1")).toBe("Wettbewerb nicht gefunden · zu groß");
    expect(fehlerZu(felder, "scenes.0")).toBeUndefined();
    expect(uebrigeFehler(felder, (f) => f.startsWith("scenes."))).toEqual(["Allgemein"]);
  });
});

describe("Export", () => {
  it("baut Pfade und erkennt leere CSV-Dateien", () => {
    expect(exportPfad("t 1", "winners", "pdf")).toBe("/tournaments/t%201/export/winners.pdf");
    expect(csvIstLeer("﻿Nr;Name\r\n")).toBe(true);
    expect(csvIstLeer("Nr;Name\n1;Anna\n")).toBe(false);
  });
});

describe("Abgebrochene Starts", () => {
  const ab = zeile({ start_id: "x", place: null, group: "unranked", abort_reason: "dns" });
  const eins = zeile({ start_id: "a", place: 1 });
  const zwei = zeile({ start_id: "b", place: 2 });
  const drei = zeile({ start_id: "c", place: 3 });
  const vier = zeile({ start_id: "d", place: 4 });

  it("QA G-8: stehen in der Live-Wertung als eigener Block „Ohne Platzierung“ hinter den Plätzen", () => {
    const liste = rangliste();
    const [erste, zweite] = liste.groups;
    if (!erste || !zweite) throw new Error("Testdaten");
    const mitOhne = {
      ...liste,
      groups: [{ ...erste, more: 0, unplaced: [ab] }, zweite],
    };
    const eintraege = ranglistenEintraege(mitOhne);
    expect(eintraege.map((e) => e.art)).toEqual([
      "klasse",
      "zeile",
      "zeile",
      "zeile",
      "ohne_kopf",
      "ohne",
      "klasse",
      "zeile",
    ]);
    // Der Kopf „Ohne Platzierung“ steht nie allein unten; geht der Block weiter, steht er wieder da.
    const seiten = ranglistenSeiten(eintraege, 5);
    expect(seiten[0]?.map((e) => e.art)).toEqual(["klasse", "zeile", "zeile", "zeile"]);
    expect(seiten[1]?.[0]).toMatchObject({ art: "ohne_kopf" });
  });

  it("kommen nie aufs Podest; weitere Plätze ab Platz 4", () => {
    const { podest, rest } = siegerAufteilung([eins, zwei, drei, vier]);
    expect(podest.map((z) => z.start_id)).toEqual(["a", "b", "c"]);
    expect(rest.map((z) => z.start_id)).toEqual(["d"]);
  });

  it("QA G-8: „nicht angetreten“ ohne Ergebniswert; Abgebrochene sind keine weiteren Plätze", () => {
    expect(mitErgebnis({ abort_reason: "dns", score_text: "0,00 s" })).toBe(false);
    expect(mitErgebnis({ abort_reason: "dnf", score_text: "30,00 s" })).toBe(true);
    expect(mitErgebnis({ abort_reason: "dnf", score_text: null })).toBe(false);
    expect(mitErgebnis({ abort_reason: null, score_text: "183 Ringe" })).toBe(true);
    expect(mitWeiterenPlaetzen([eins, zwei, ab])).toBe(false);
    expect(mitWeiterenPlaetzen([eins, zwei, drei, ab])).toBe(false);
    expect(mitWeiterenPlaetzen([eins, zwei, drei, vier])).toBe(true);
  });

  it("Abbruch nach „Feuer“ hat einen Platz: steht unter den Plätzen und kann aufs Podest", () => {
    const liste = abbruchRangliste();
    const gruppe = liste.groups[0];
    if (!gruppe) throw new Error("Testdaten");
    const platziert = gruppe.rows.find((z) => z.start_id === "f2");
    if (!platziert) throw new Error("Testdaten");
    expect(istPlatzierterAbbruch(platziert)).toBe(true);
    expect(istPlatzierterAbbruch(gruppe.unplaced[0] as typeof platziert)).toBe(false);
    expect(istPlatzierterAbbruch(zwei)).toBe(false);
    expect(siegerAufteilung(gruppe.rows).podest.map((z) => z.start_id)).toContain("f2");
    const arten = ranglistenEintraege(liste).map((e) =>
      e.art === "zeile" || e.art === "ohne" ? `${e.art}:${e.zeile.start_id}` : e.art,
    );
    expect(arten).toEqual([
      "zeile:f1",
      "zeile:f2",
      "zeile:f3",
      "zeile:f4",
      "ohne_kopf",
      "ohne:f5",
      "ohne:f6",
    ]);
  });

  it("Kennzeichen kommt vom Server (abort_label); eigener Text nur als Rückfall", () => {
    const rueckfall = (grund: string) => `fest:${grund}`;
    expect(abbruchText({ abort_reason: "dnf", abort_label: "Abbruch (AB)" }, rueckfall)).toBe(
      "Abbruch (AB)",
    );
    expect(abbruchText({ abort_reason: "dnf", abort_label: "aufgegeben" }, rueckfall)).toBe(
      "aufgegeben",
    );
    expect(abbruchText({ abort_reason: "dsq" }, rueckfall)).toBe("fest:dsq");
    expect(abbruchText({ abort_reason: "dns", abort_label: "  " }, rueckfall)).toBe("fest:dns");
    expect(abbruchText({ abort_reason: null, abort_label: null }, rueckfall)).toBeNull();
  });

  it("QA G-8: das längste Wort bestimmt die Schrift auf dem Podest („Startnummer 5“)", () => {
    expect(laengstesWort("Startnummer 5")).toBe(11);
    expect(laengstesWort("Ilse Bergmann")).toBe(8);
    expect(laengstesWort("")).toBe(0);
  });
});

describe("Als Nächstes (Standanzeige)", () => {
  it("QA G-7: je Wettbewerb ein Kopf, Zeitplan mit Bahn, Reihenfolge mit Platz", () => {
    const stand = (szenen.range as SzeneVon<"range">).range;
    const eintraege = naechsteEintraege(stand.upcoming);
    expect(eintraege.map((e) => e.art)).toEqual(["kopf", "person", "kopf", "person", "mehr"]);
    const zahlen = eintraege.flatMap((e) =>
      e.art === "person"
        ? [[e.block.kind, "lane" in e.eintrag ? e.eintrag.lane : e.eintrag.position]]
        : [],
    );
    expect(zahlen).toEqual([
      ["schedule", 3],
      ["queue", 1],
    ]);
    // Ein Kopf steht nie allein unten auf einer Seite.
    const seiten = naechsteSeiten(eintraege, 3);
    expect(seiten[0]?.map((e) => e.art)).toEqual(["kopf", "person"]);
    expect(seiten[1]?.[0]).toMatchObject({ art: "kopf" });
  });
});
