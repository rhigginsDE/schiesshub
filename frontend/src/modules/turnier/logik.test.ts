import { describe, expect, it } from "vitest";
import type { Abschnitt, Variante } from "../../api/typen";
import { formatBetrag, formatGeld, leseBetrag } from "../../components/geld";
import { verschiebe } from "../../components/Reihenfolge";
import { druckModell, istLeer } from "./ausschreibung/dokument";
import type { AusschreibungDokument } from "./ausschreibung/typen";
import {
  type EinstellungsWerte,
  einstellungsAenderung,
  zeitzonenAuswahl,
} from "./bereiche/Einstellungen";
import { kennungAus, klasseAusWerten } from "./bereiche/Klassen";
import { stammdatenAenderung } from "./bereiche/Stammdaten";
import { ablaufKurz, planungKurz, startsKurz, zeitraum } from "./klartext";
import { planungBegruendung, planungVorschlag } from "./planung";
import { moeglicheWechsel } from "./Status";
import { EingabeFehler, feldFehlerFuer, leseFehlerInhalt } from "./senden";
import { anlageAusFormular } from "./TurnierAnlegen";
import { beispielTurnier, beispielWettbewerb } from "./testdaten";
import { BEREICHE, ersterOffenerSchritt, offenePunkte, schrittZustaende } from "./vollstaendigkeit";
import {
  abweichungen,
  aenderungen,
  ausWettbewerb,
  pruefeFormular,
  schalteTrefferaufnahme,
  setzeSerien,
  wertungGeaendert,
} from "./wettbewerbFormular";

describe("Geld: Euro in der Oberfläche, Cent in der API", () => {
  it("liest Eingaben mit Komma, Punkt und Tausendertrennern", () => {
    expect(leseBetrag("6")).toBe(600);
    expect(leseBetrag("6,5")).toBe(650);
    expect(leseBetrag("6,50 €")).toBe(650);
    expect(leseBetrag("6.50")).toBe(650);
    expect(leseBetrag("1.234,56")).toBe(123456);
    expect(leseBetrag("1.000")).toBe(100000);
    expect(leseBetrag("")).toBeNull();
    expect(leseBetrag("6,555")).toBeUndefined();
    expect(leseBetrag("abc")).toBeUndefined();
    expect(leseBetrag("-3")).toBeUndefined();
  });

  it("zeigt Beträge mit Dezimalkomma und €", () => {
    expect(formatBetrag(600, "de")).toBe("6,00");
    expect(formatGeld(850, "EUR", "de").replace(/\s/g, " ")).toBe("8,50 €");
  });
});

describe("Wettbewerb: Formular ↔ API", () => {
  const wettbewerb = beispielWettbewerb();

  it("schickt nur geänderte Felder, Geld in Cent", () => {
    const formular = { ...ausWettbewerb(wettbewerb), fee_first_cents: 800, name: " Neu " };
    expect(aenderungen(formular, wettbewerb)).toEqual({ name: "Neu", fee_first_cents: 800 });
  });

  it("schickt beim Abschalten des Mehrfachstarts genau einen Start", () => {
    const formular = { ...ausWettbewerb(wettbewerb), multi_start: false };
    expect(aenderungen(formular, wettbewerb)).toEqual({ multi_start: false, max_starts: 1 });
    expect(wertungGeaendert(formular, wettbewerb)).toBe(true);
  });

  it("schickt den geänderten Ablauf als Definition ohne Herkunft", () => {
    const formular = ausWettbewerb(wettbewerb);
    formular.abschnitte = [{ ...(formular.abschnitte[0] as Abschnitt), serien_gewertet: 3 }];
    const neu = aenderungen(formular, wettbewerb);
    expect(neu.definition?.source).toBeUndefined();
    expect(neu.definition?.variant.abschnitte[0]?.serien_gewertet).toBe(3);
    expect(neu.definition?.scoring).toEqual(wettbewerb.definition.scoring);
  });

  it("Startgeld ändern ist keine Wertungsänderung (kein Grund nötig)", () => {
    const formular = { ...ausWettbewerb(wettbewerb), fee_first_cents: 1000 };
    expect(wertungGeaendert(formular, wettbewerb)).toBe(false);
  });

  it("passt Listen je Serie an eine neue Serienzahl an", () => {
    const abschnitt: Abschnitt = {
      id: "a",
      name: "A",
      serien: 3,
      zeiten_s: [150, 20, 10],
      serien_gewertet: 3,
      trefferaufnahme_nach: [1, 3],
    };
    expect(setzeSerien(abschnitt, 2)).toMatchObject({
      serien: 2,
      zeiten_s: [150, 20],
      serien_gewertet: 2,
      trefferaufnahme_nach: [1],
    });
    expect(setzeSerien(abschnitt, 4).zeiten_s).toEqual([150, 20, 10, 10]);
  });

  it("schaltet die Trefferaufnahme um und hält die Liste aufsteigend", () => {
    const abschnitt: Abschnitt = { id: "a", name: "A", serien: 4, trefferaufnahme_nach: [4] };
    expect(schalteTrefferaufnahme(abschnitt, 2).trefferaufnahme_nach).toEqual([2, 4]);
    expect(schalteTrefferaufnahme(abschnitt, 4).trefferaufnahme_nach).toBeNull();
  });

  it("prüft gewertete Serien, Dauer bei Zeitplan und Beträge", () => {
    const formular = ausWettbewerb(wettbewerb);
    formular.abschnitte = [{ ...(formular.abschnitte[0] as Abschnitt), serien_gewertet: 9 }];
    formular.planning = "schedule";
    formular.heat_minutes = null;
    formular.fee_first_cents = null;
    const fehler = pruefeFormular(formular);
    expect(fehler["definition.variant.abschnitte.0.serien_gewertet"]).toMatch(/1 und 4/);
    expect(fehler.heat_minutes).toBeDefined();
    expect(fehler.fee_first_cents).toBeDefined();
  });

  it("findet Abweichungen vom Katalog je Feld", () => {
    const katalog = wettbewerb.definition.variant;
    const geaendert = [{ ...(katalog.abschnitte[0] as Abschnitt), max_zeit_je_serie_s: 90 }];
    expect(abweichungen(geaendert, katalog)).toEqual([
      { abschnitt: "fallscheibe", feld: "max_zeit_je_serie_s", katalog: 60, turnier: 90 },
    ]);
    expect(abweichungen(katalog.abschnitte, katalog)).toEqual([]);
    expect(abweichungen(katalog.abschnitte, undefined)).toBeNull();
  });
});

describe("Planung und Klartext", () => {
  const praezision: Variante = {
    id: "standard",
    name: "Standard",
    abschnitte: [
      { id: "p", name: "Präzision", serien: 2, schuss_je_serie: 10, zeit_je_serie_s: 300 },
    ],
  };

  it("schlägt bei fester Zeit den Zeitplan vor, mit Begründung", () => {
    const vorschlag = planungVorschlag(praezision, 5);
    expect(vorschlag).toMatchObject({ planung: "schedule", durchgangMinuten: 15 });
    expect(planungBegruendung(vorschlag, 5, "de")).toBe(
      "Alle Serien haben eine feste Zeit: 10 Min. Schießzeit plus 5 Min. Wechselzeit ergeben 15 Min.",
    );
  });

  it("schlägt ohne feste Zeit die Reihenfolge vor und nennt den Abschnitt", () => {
    const variante = beispielWettbewerb().definition.variant;
    const vorschlag = planungVorschlag(variante, 5);
    expect(vorschlag.planung).toBe("queue");
    expect(planungBegruendung(vorschlag, 5, "de")).toMatch(/Bei „Fallscheibe“/);
  });

  it("beschreibt Ablauf, Planung und Starts kurz", () => {
    const w = beispielWettbewerb();
    expect(ablaufKurz(w.definition.variant, "de")).toBe(
      "4 Serien · max. 6 Schuss · 5 Ziele · max. 1 Min.",
    );
    expect(planungKurz({ ...w, planning: "schedule", heat_minutes: 12 }, "de")).toBe(
      "Zeitplan, 12 Min.",
    );
    expect(planungKurz(w, "de")).toBe("Aufruf der Reihe nach");
    expect(startsKurz(w, "de")).toBe("bis 3 Starts, bestes zählt");
    expect(zeitraum({ date_from: "2026-12-05", date_to: "2026-12-06" }, "de")).toBe(
      "05.12.2026 – 06.12.2026",
    );
  });
});

describe("Formulare des Turniers", () => {
  it("legt ein eintägiges Turnier ohne leere Felder an", () => {
    expect(
      anlageAusFormular({
        name: " Herbstpokal ",
        organizer: "",
        date_from: "2026-12-05",
        date_to: "2026-12-05",
        template: "open",
      }),
    ).toEqual({ name: "Herbstpokal", date_from: "2026-12-05", template: "open" });
  });

  it("schickt bei den Stammdaten nur Änderungen; leerer Veranstalter wird null", () => {
    const basis = { name: "A", organizer: "SV", date_from: "2026-12-05", date_to: "2026-12-05" };
    expect(stammdatenAenderung({ ...basis, organizer: " " }, basis)).toEqual({ organizer: null });
  });

  it("schickt bei den Einstellungen nur Änderungen; ohne Mehrfachstart 1 Start", () => {
    const basis = beispielTurnier().settings as EinstellungsWerte;
    expect(
      einstellungsAenderung({ ...basis, default_multi_start: false, protest_minutes: 30 }, basis),
    ).toEqual({ default_multi_start: false, default_max_starts: 1, protest_minutes: 30 });
  });

  it("schickt Zeitzone und Neubeginn der Einspruchsfrist nur, wenn geändert", () => {
    const basis = {
      ...(beispielTurnier().settings as EinstellungsWerte),
      timezone: "Europe/Berlin",
      protest_restart_on_correction: true,
    };
    expect(einstellungsAenderung(basis, basis)).toEqual({});
    expect(
      einstellungsAenderung(
        { ...basis, timezone: "Europe/Vienna", protest_restart_on_correction: false },
        basis,
      ),
    ).toEqual({ timezone: "Europe/Vienna", protest_restart_on_correction: false });
  });

  it("bietet übliche Zeitzonen an und behält einen gespeicherten Wert außerhalb der Liste", () => {
    const t = (schluessel: string) => schluessel;
    const ueblich = zeitzonenAuswahl("Europe/Berlin", t);
    expect(ueblich[0]).toEqual({ value: "Europe/Berlin", label: "zeitzone.Europe_Berlin" });
    expect(ueblich.some((z) => z.value === "America/New_York")).toBe(false);
    const fremd = zeitzonenAuswahl("America/New_York", t);
    expect(fremd.at(-1)).toEqual({ value: "America/New_York", label: "America/New York" });
    expect(fremd.filter((z) => z.value === "Europe/Berlin")).toHaveLength(1);
  });

  it("bildet die Kennung einer Klasse aus dem Kurznamen", () => {
    expect(kennungAus("Sen Ü 60")).toBe("sen-u-60");
    expect(
      klasseAusWerten({ code: "", name: "Senioren", short: "Sen", merge_into_id: null }),
    ).toEqual({ code: "sen", name: "Senioren", short: "Sen" });
  });

  it("erlaubt Statuswechsel nur schrittweise, zurück nur mit Recht", () => {
    expect(moeglicheWechsel("draft", false).map((w) => w.ziel)).toEqual(["active"]);
    expect(moeglicheWechsel("active", false).map((w) => w.ziel)).toEqual(["closed"]);
    expect(moeglicheWechsel("active", true).map((w) => w.ziel)).toEqual(["closed", "draft"]);
    expect(moeglicheWechsel("closed", false)).toEqual([]);
  });

  it("verschiebt Einträge einer Liste", () => {
    expect(verschiebe(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
    expect(verschiebe(["a", "b"], 0, -1)).toEqual(["a", "b"]);
  });

  it("listet offene Punkte vor dem Start", () => {
    const turnier = beispielTurnier();
    expect(offenePunkte({ ...turnier, ranges: [], classes: [] }).map((p) => p.schluessel)).toEqual([
      "kein_stand",
      "keine_klasse",
      "ohne_stand",
      "ohne_stand",
    ]);
    expect(offenePunkte(turnier)).toEqual([]);
  });

  it("zeigt je Schritt erledigt, fehlt noch oder optional und führt zum ersten offenen", () => {
    const turnier = beispielTurnier();
    const leer = { ...turnier, ranges: [], classes: [] };
    const zustaende = schrittZustaende(leer, offenePunkte(leer));
    expect(zustaende.stammdaten).toEqual({ art: "erledigt" });
    expect(zustaende.staende).toEqual({ art: "fehlt", schluessel: "kein_stand", anzahl: 1 });
    expect(zustaende.wettbewerbe).toMatchObject({ art: "fehlt", schluessel: "ohne_stand" });
    expect(zustaende.ausschreibung).toEqual({ art: "optional" });
    expect(ersterOffenerSchritt(zustaende)).toBe("staende");
    // Die Vorgaben stehen vor den Wettbewerben, damit sie für neue Wettbewerbe gelten.
    expect(BEREICHE.indexOf("einstellungen")).toBeLessThan(BEREICHE.indexOf("wettbewerbe"));
    expect(ersterOffenerSchritt(schrittZustaende(turnier, offenePunkte(turnier)))).toBe(
      "zusammenfassung",
    );
  });
});

describe("Fehler des Servers am Feld", () => {
  it("liest deutsche Feldfehler und wandelt [n] in Punkte", () => {
    const inhalt = leseFehlerInhalt({
      detail: "Feld ‚lane_count‘: muss mindestens 1 sein.",
      errors: [
        { field: "lane_count", message: "muss mindestens 1 sein" },
        { field: "definition.variant.abschnitte[0].serien", message: "zu klein" },
      ],
    });
    expect(inhalt.felder).toEqual([
      { feld: "lane_count", meldung: "muss mindestens 1 sein" },
      { feld: "definition.variant.abschnitte.0.serien", meldung: "zu klein" },
    ]);
  });

  it("ordnet Fehler bekannten Feldern zu, den Rest als allgemeine Meldung", () => {
    const fehler = new EingabeFehler("anfrage", "/x", 422, "Zusammenfassung", [
      { feld: "settings.currency", meldung: "Format" },
      { feld: "", meldung: "Ganz allgemein" },
    ]);
    expect(feldFehlerFuer(fehler, ["currency"], "settings")).toEqual({
      currency: "Format",
      "": "Ganz allgemein",
    });
  });

  it("nimmt bei reinem detail-Text diesen als allgemeine Meldung", () => {
    const fehler = new EingabeFehler("konflikt", "/x", 409, "Turnier ist abgeschlossen.", []);
    expect(feldFehlerFuer(fehler, ["name"])).toEqual({ "": "Turnier ist abgeschlossen." });
  });
});

describe("Ausschreibung: Dokument → Druckansicht", () => {
  const dokument: AusschreibungDokument = {
    title: "Ausschreibung Herbstpokal",
    tournament: {
      id: "t1",
      name: "Herbstpokal",
      organizer: "SV Musterstadt",
      date_from: "2026-12-05",
      date_to: "2026-12-05",
      status: "draft",
      currency: "EUR",
    },
    facts: { venue: "Schützenhaus", registration_deadline: "2026-11-30", contact_name: "" },
    blocks: [
      { id: "begruessung", kind: "text", heading: "Begrüßung", body: "Hallo.\n\nBis bald." },
      { id: "leer", kind: "text", heading: "Anmeldung", body: "   " },
      {
        id: "wettbewerbe",
        kind: "competitions",
        heading: "Wettbewerbe",
        body: "",
        competitions: [
          {
            id: "w1",
            name: "Selbstladeflinte",
            catalog_federation: "bds",
            catalog_code: "4401",
            group: "flinte",
            range_name: "15-m-Stand",
            procedure: null,
            sections: [
              {
                name: "Fallscheibe",
                serien: 4,
                schuss_je_serie: null,
                serien_gewertet: 3,
                summary: "Fallscheibe: 4 Serien",
              },
            ],
            multi_start: true,
            max_starts: 3,
            multi_start_rule: "best",
            multi_start_text: "Bestes Ergebnis zählt",
            deviates_from_catalog: true,
            deviations: ["3 von 4 Serien gewertet"],
          },
        ],
      },
      { id: "klassen", kind: "classes", heading: "Klassen", body: "", classes: [] },
      {
        id: "startgeld",
        kind: "fees",
        heading: "Startgeld",
        body: "",
        fees: {
          currency: "EUR",
          items: [
            {
              competition_id: "w1",
              name: "Selbstladeflinte",
              fee_first_cents: 800,
              fee_repeat_cents: 500,
            },
          ],
        },
      },
    ],
  };

  it("lässt leere Bausteine weg und formatiert Geld und Datum", () => {
    const modell = druckModell(dokument, "de");
    expect(modell.bausteine.map((b) => b.id)).toEqual(["begruessung", "wettbewerbe", "startgeld"]);
    expect(modell.bausteine[0]?.absaetze).toEqual(["Hallo.", "Bis bald."]);
    const wettbewerbe = modell.bausteine[1];
    expect(wettbewerbe?.art).toBe("wettbewerbe");
    if (wettbewerbe?.art === "wettbewerbe") {
      expect(wettbewerbe.wettbewerbe[0]?.startgeld?.replace(/\s/g, " ")).toBe("8,00 € / 5,00 €");
      expect(wettbewerbe.wettbewerbe[0]?.abweichend).toBe(true);
    }
    expect(modell.eckdaten).toEqual([
      { bezeichnung: "Ort", text: "Schützenhaus" },
      { bezeichnung: "Meldeschluss", text: "30.11.2026" },
    ]);
    expect(modell.zeitraum).toBe("05.12.2026");
  });

  it("erkennt leere Text-Bausteine", () => {
    expect(istLeer({ kind: "text", body: " \n " })).toBe(true);
    expect(istLeer({ kind: "fees", body: "" })).toBe(false);
  });
});
