import { describe, expect, it } from "vitest";
import i18n from "../../i18n";
import {
  abschnittAufgelegt,
  abschnittsHinweise,
  feldBereich,
  notizen,
  ringEinheit,
  serienAnzeige,
  serienHinweise,
  vorgaben,
} from "./anzeige";
import type { AbschnittForm, FeldBeschreibung, Formular, SerieForm, SerienWertung } from "./api";
import { FALLSCHEIBE } from "./testdaten";

const t = i18n.getFixedT("de", "erfassung");

const basis = FALLSCHEIBE.sections[0] as AbschnittForm;

function abschnitt(id: string, teil: Partial<AbschnittForm> = {}): AbschnittForm {
  return { ...basis, id, name: id, hints: [], hint_items: [], aufgelegt: false, ...teil };
}

function form(sections: AbschnittForm[], teil: Partial<Formular> = {}): Formular {
  return { ...FALLSCHEIBE, sections, ...teil };
}

/** Luftgewehr (DSB 1.10): Wettkampfzeit, Vorbereitung und Probe, Probeschüsse unbegrenzt. */
const LUFTGEWEHR = abschnitt("wertung", {
  hint_items: [
    { kind: "competition_time", text: "Wettkampfzeit 50 min" },
    { kind: "preparation_time", text: "Vorbereitung und Probe 15 min" },
    { kind: "sighters", text: "Probeschüsse unbegrenzt" },
  ],
  hints: ["Wettkampfzeit 50 min", "Vorbereitung und Probe 15 min", "Probeschüsse unbegrenzt"],
});

describe("Vorgaben im Kopf (Hinweise nach Art)", () => {
  it("ein Abschnitt: Probeschüsse, Vorbereitung, Wettkampfzeit im Kopf, Text des Servers", () => {
    const liste = vorgaben(form([LUFTGEWEHR]));
    expect(liste).toEqual([
      { art: "hinweis", kind: "sighters", text: "Probeschüsse unbegrenzt" },
      { art: "hinweis", kind: "preparation_time", text: "Vorbereitung und Probe 15 min" },
      { art: "hinweis", kind: "competition_time", text: "Wettkampfzeit 50 min" },
    ]);
  });

  it("ein Abschnitt: die Abschnittszeile wiederholt die Vorgaben aus dem Kopf nicht", () => {
    const mitSoll = abschnitt("a", {
      hint_items: [...LUFTGEWEHR.hint_items, { kind: "target_time", text: "Sollzeit 10 s" }],
    });
    expect(abschnittsHinweise(form([mitSoll]), "a")).toEqual(["Sollzeit 10 s"]);
  });

  it("erkennt an der Art, nicht am Wortlaut", () => {
    const anders = abschnitt("a", {
      hint_items: [{ kind: "sighters", text: "Probe: beliebig viele" }],
    });
    expect(abschnittsHinweise(form([anders]), "a")).toEqual([]);
    expect(vorgaben(form([anders]))).toEqual([
      { art: "hinweis", kind: "sighters", text: "Probe: beliebig viele" },
    ]);
  });

  it("mehrere Abschnitte: alles bleibt am Abschnitt, nichts im Kopf", () => {
    const f = form([LUFTGEWEHR, abschnitt("b")]);
    expect(vorgaben(f)).toEqual([]);
    expect(abschnittsHinweise(f, "wertung")).toEqual(LUFTGEWEHR.hints);
  });

  it("„aufgelegt“ kommt vom Abschnitt: alle aufgelegt → im Kopf, sonst am Abschnitt", () => {
    const alle = form([abschnitt("a", { aufgelegt: true })]);
    expect(vorgaben(alle)).toEqual([{ art: "aufgelegt" }]);
    expect(abschnittAufgelegt(alle, "a")).toBe(false);

    const teils = form([abschnitt("a", { aufgelegt: true }), abschnitt("b")]);
    expect(vorgaben(teils)).toEqual([]);
    expect(abschnittAufgelegt(teils, "a")).toBe(true);
    expect(abschnittAufgelegt(teils, "b")).toBe(false);

    expect(vorgaben(form([abschnitt("a")]))).toEqual([]);
  });
});

describe("Hinweise der Serie", () => {
  const serie = (teil: Partial<SerieForm>): SerieForm =>
    ({ ...basis.series[0], ...teil }) as SerieForm;

  it("lässt „gestrichen“, Position und „danach Trefferaufnahme“ weg (zeigt die Maske selbst)", () => {
    const s = serie({
      struck: true,
      scoring_break_after: true,
      hint_items: [
        { kind: "struck", text: "gestrichen (nicht gewertet)" },
        { kind: "position", text: "Position 1: stehend, aufgelegt" },
        { kind: "targets", text: "5 Scheiben" },
        { kind: "max_time", text: "Zeitlimit 60 s" },
        { kind: "scoring_break", text: "danach Trefferaufnahme" },
      ],
    });
    expect(serienHinweise(s)).toEqual(["5 Scheiben", "Zeitlimit 60 s"]);
  });
});

describe("Einheit der Ringwerte", () => {
  const dreiundzwanzig: SerienWertung = {
    number: 1,
    struck: false,
    status: "normal",
    captured: true,
    complete: true,
    shots_entered: 25,
    shots_expected: 25,
    rings: 23,
    tens: null,
    inner_tens: null,
    measured_time_cs: null,
    time_cs: null,
    penalty_cs: null,
    total_cs: null,
  } as SerienWertung;

  it("„Treffer“ kommt als Einheit vom Server, sonst „Ringe“ (auch bei „Punkte“)", () => {
    expect(ringEinheit("Treffer", t)).toBe("Treffer");
    expect(ringEinheit("Ringe", t)).toBe("Ringe");
    expect(ringEinheit("Punkte", t)).toBe("Ringe");
    expect(serienAnzeige(dreiundzwanzig, t, "Treffer")).toMatchObject({
      wert: "23",
      einheit: "Treffer",
    });
    expect(serienAnzeige(dreiundzwanzig, t, "Ringe")).toMatchObject({
      wert: "23",
      einheit: "Ringe",
    });
  });
});

describe("Bereich der Zehntel-Seriensumme kommt aus der Formularbeschreibung", () => {
  it("value_min 1.0, value_max, zero_allowed → „0 oder 1,0 bis …“", () => {
    const summe: FeldBeschreibung = {
      key: "sum",
      label: "Seriensumme",
      kind: "decimal",
      required: true,
      decimals: 1,
      step: "0.1",
      value_min: "1.0",
      value_max: "109.0",
      zero_allowed: true,
    };
    expect(feldBereich(summe, t)).toBe("0 oder 1,0 bis 109,0");
    expect(feldBereich({ ...summe, value_min: "0.0" }, t)).toBe("0,0 bis 109,0");
    expect(feldBereich({ ...summe, zero_allowed: false }, t)).toBe("1,0 bis 109,0");
  });
});

describe("Notizen der Maske nach Art (note_items)", () => {
  const mitNotizen = form([abschnitt("a"), abschnitt("b")], {
    note_items: [
      { kind: "tenths", text: "Zehntelwertung" },
      { kind: "competition_time_total", text: "Wettkampfzeit gesamt 75 min" },
      { kind: "shootoff", text: "Gleichstand bis Platz 3 entscheidet ein Stechen." },
      { kind: "tens_optional", text: "Zehner freiwillig" },
      { kind: "max_score", text: "Höchstergebnis: gleicher Platz" },
    ],
  });

  it("gemeinsame Wettkampfzeit steht bei den Vorgaben im Kopf, auch bei mehreren Abschnitten", () => {
    expect(vorgaben(mitNotizen)).toEqual([
      {
        art: "hinweis",
        kind: "competition_time_total",
        text: "Wettkampfzeit gesamt 75 min",
      },
    ]);
  });

  it("Erfassung und Gleichstand bekommen je ihre Notizen, nichts doppelt", () => {
    expect(notizen(mitNotizen, "erfassung").map((n) => n.kind)).toEqual([
      "tenths",
      "tens_optional",
    ]);
    expect(notizen(mitNotizen, "gleichstand").map((n) => n.kind)).toEqual([
      "shootoff",
      "max_score",
    ]);
  });

  it("neue Arten zum Gleichstand beim Gesamtstand, unbekannte Arten mit ihrem Text bei der Erfassung", () => {
    const neu = form([abschnitt("a")], {
      tie_breakers_until_place: 3,
      tie_breakers_after: ["zehner"],
      tie_breakers_after_evaluated: ["zehner"],
      tie_breakers_after_manual_from: null,
      shootoff_at_max_score: true,
      note_items: [
        { kind: "shootoff", text: "Höchstergebnis auf Platz 1: Stechen" },
        { kind: "tie_break_manual", text: "Ab dem Kriterium Innenzehner entscheidest du." },
        // Art, die diese Version nicht kennt: bleibt mit ihrem Text stehen
        { kind: "neue_art" as never, text: "Neuer Hinweis des Servers" },
      ],
    });
    expect(notizen(neu, "gleichstand").map((n) => n.text)).toEqual([
      "Höchstergebnis auf Platz 1: Stechen",
      "Ab dem Kriterium Innenzehner entscheidest du.",
    ]);
    expect(notizen(neu, "erfassung").map((n) => n.text)).toEqual(["Neuer Hinweis des Servers"]);
  });
});
