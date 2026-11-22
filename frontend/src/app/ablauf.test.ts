import { describe, expect, it } from "vitest";
import type { Turnier } from "../modules/turnier/typen";
import {
  type AblaufEingaben,
  ablauf,
  type SchrittId,
  type SchrittStand,
  turnierFuerAblauf,
  zaehleStarts,
} from "./ablauf";

const entwurf = { name: "Vereinsmeisterschaft", status: "draft" } as const;
const laeuft = { name: "Vereinsmeisterschaft", status: "active" } as const;
const ok = { art: "ok", zeit: "14:05" } as const;

function staende(eingaben: AblaufEingaben): Record<SchrittId, SchrittStand> {
  return Object.fromEntries(ablauf(eingaben).schritte.map((s) => [s.id, s.stand])) as Record<
    SchrittId,
    SchrittStand
  >;
}

describe("Ablauf der Startseite", () => {
  it("kein Turnier: Turnier anlegen, alles Weitere wartet auf den Start", () => {
    const a = ablauf({ turnier: null, sicherung: ok });
    expect(a.naechster).toBe("turnier");
    expect(a.aktion).toBe("turnier_anlegen");
    expect(a.schritte[0]?.text).toBe("turnier_keins");
    expect(staende({ turnier: null, sicherung: ok })).toEqual({
      turnier: "offen",
      anmeldung: "wartet",
      erfassung: "wartet",
      anzeige: "wartet",
      sicherung: "ok",
    });
    expect(a.schritte[1]?.text).toBe("wartet_auf_start");
  });

  it("Entwurf unvollständig: weiter einrichten, der erste offene Punkt steht dabei", () => {
    const a = ablauf({
      turnier: entwurf,
      offenePunkte: [
        { bereich: "staende", schluessel: "kein_stand" },
        { bereich: "klassen", schluessel: "keine_klasse" },
      ],
    });
    expect(a.naechster).toBe("turnier");
    expect(a.aktion).toBe("turnier_einrichten");
    expect(a.schritte[0]).toMatchObject({
      text: "turnier_entwurf_offen",
      punkt: { schluessel: "kein_stand" },
      werte: { name: "Vereinsmeisterschaft", count: 1 },
    });
  });

  it("Entwurf fertig: Turnier starten", () => {
    const a = ablauf({ turnier: entwurf, offenePunkte: [] });
    expect(a.aktion).toBe("turnier_starten");
    expect(a.schritte[0]?.text).toBe("turnier_entwurf_fertig");
  });

  it("läuft ohne Anmeldungen: zur Anmeldung, die Erfassung wartet auf Starts", () => {
    const eingaben: AblaufEingaben = {
      turnier: laeuft,
      wettbewerbe: 3,
      starts: zaehleStarts([]),
      sicherung: ok,
    };
    const a = ablauf(eingaben);
    expect(a.naechster).toBe("anmeldung");
    expect(a.aktion).toBe("zur_anmeldung");
    expect(staende(eingaben)).toMatchObject({
      turnier: "erledigt",
      anmeldung: "offen",
      erfassung: "wartet",
      anzeige: "offen",
    });
    expect(a.schritte[2]?.text).toBe("wartet_auf_starts");
  });

  it("läuft mit offenen Starts: Ergebnisse erfassen, nichts ist gesperrt", () => {
    const starts = zaehleStarts([
      { entry_id: "a", status: "final" },
      { entry_id: "a", status: "registered" },
      { entry_id: "b", status: "called" },
      { entry_id: "c", status: "aborted" },
    ]);
    expect(starts).toEqual({ schuetzen: 3, starts: 4, offen: 2, abgeschlossen: 2, ergebnisse: 1 });
    const eingaben: AblaufEingaben = { turnier: laeuft, starts, sicherung: ok };
    const a = ablauf(eingaben);
    expect(a.naechster).toBe("erfassung");
    expect(a.aktion).toBe("ergebnisse_erfassen");
    expect(Object.values(staende(eingaben))).not.toContain("wartet");
    expect(a.schritte[2]?.werte).toEqual({ count: 2, abgeschlossen: 2 });
  });

  it("alles abgeschlossen: Siegerliste zeigen", () => {
    const starts = zaehleStarts([
      { entry_id: "a", status: "final" },
      { entry_id: "b", status: "aborted" },
    ]);
    const a = ablauf({ turnier: laeuft, starts, sicherung: ok });
    expect(a.naechster).toBe("anzeige");
    expect(a.aktion).toBe("siegerliste");
    expect(a.schritte[2]?.stand).toBe("erledigt");
  });

  it("Sicherung gestört: verdrängt die Anmeldung nicht, zeigt aber Zustand und eigene Aktion", () => {
    const warnung = {
      art: "warnung",
      code: "passphrase_missing",
      behebbar: true,
      nieGesichert: true,
    } as const;
    const amTag = ablauf({ turnier: laeuft, starts: zaehleStarts([]), sicherung: warnung });
    expect(amTag.naechster).toBe("anmeldung");
    expect(amTag.aktion).toBe("zur_anmeldung");
    expect(amTag.sicherungAktion).toBe("passwort_festlegen");
    expect(amTag.schritte[4]).toMatchObject({
      stand: "gestoert",
      werte: { code: "passphrase_missing" },
    });

    // Starts gebucht, aber noch kein Ergebnis: weiter erfassen.
    const gebucht = ablauf({
      turnier: laeuft,
      starts: zaehleStarts([{ entry_id: "a", status: "registered" }]),
      sicherung: warnung,
    });
    expect(gebucht.naechster).toBe("erfassung");
    expect(gebucht.sicherungAktion).toBe("passwort_festlegen");

    const beimEinrichten = ablauf({ turnier: null, sicherung: warnung });
    expect(beimEinrichten.naechster).toBe("turnier");
    expect(beimEinrichten.schritte[4]?.stand).toBe("gestoert");
  });

  it("Sicherung gestört: nächster Schritt, wenn Ergebnisse ungesichert sind", () => {
    const warnung = {
      art: "warnung",
      code: "passphrase_missing",
      behebbar: true,
      nieGesichert: true,
    } as const;
    const starts = zaehleStarts([
      { entry_id: "a", status: "final" },
      { entry_id: "b", status: "registered" },
    ]);
    const a = ablauf({ turnier: laeuft, starts, sicherung: warnung });
    expect(a.naechster).toBe("sicherung");
    expect(a.aktion).toBe("passwort_festlegen");
    expect(a.sicherungAktion).toBeUndefined();

    // Schon einmal gesichert (z. B. nur der Stick fehlt): die Erfassung bleibt dran.
    const frueher = ablauf({
      turnier: laeuft,
      starts,
      sicherung: { art: "warnung", code: "usb_missing", behebbar: true, nieGesichert: false },
    });
    expect(frueher.naechster).toBe("erfassung");
    expect(frueher.sicherungAktion).toBe("zur_sicherung");
  });

  it("Sicherung gestört: nächster Schritt, wenn sonst nichts mehr ansteht", () => {
    const stick = { art: "warnung", code: "usb_missing", behebbar: true } as const;
    const fertig = zaehleStarts([{ entry_id: "a", status: "final" }]);
    const a = ablauf({ turnier: laeuft, starts: fertig, sicherung: stick });
    expect(a.naechster).toBe("sicherung");
    expect(a.aktion).toBe("zur_sicherung");

    const zu = ablauf({ turnier: { name: "Alt", status: "closed" }, sicherung: stick });
    expect(zu.naechster).toBe("sicherung");

    // Wer die Sicherung nicht einstellen darf, sieht den Zustand, bekommt aber den nächsten Schritt.
    const ohneRecht = ablauf({
      turnier: laeuft,
      starts: fertig,
      sicherung: { ...stick, behebbar: false },
    });
    expect(ohneRecht.naechster).toBe("anzeige");
    expect(ohneRecht.sicherungAktion).toBeUndefined();
  });

  it("ohne Zahlen (keine Berechtigung) bleibt der Ablauf benutzbar", () => {
    const a = ablauf({ turnier: laeuft });
    expect(a.naechster).toBe("anmeldung");
    expect(a.schritte[2]?.stand).toBe("unbekannt");
    expect(a.schritte[4]?.stand).toBe("unbekannt");
  });

  it("abgeschlossenes Turnier: alles erledigt, Siegerliste", () => {
    const a = ablauf({
      turnier: { name: "Alt", status: "closed" },
      starts: zaehleStarts([{ entry_id: "a", status: "final" }]),
      sicherung: ok,
    });
    expect(a.naechster).toBe("anzeige");
    expect(a.schritte.slice(0, 3).map((s) => s.stand)).toEqual([
      "erledigt",
      "erledigt",
      "erledigt",
    ]);
  });
});

describe("Turnier des Ablaufs", () => {
  const turnier = (id: string, status: Turnier["status"], updated_at: string) =>
    ({
      id,
      name: id,
      status,
      date_from: "2026-12-05",
      date_to: "2026-12-05",
      updated_at,
    }) as Turnier;

  it("nimmt das Turnier der Stationen, sonst das zuletzt bearbeitete aktive, dann Entwürfe", () => {
    const a = turnier("a", "active", "2026-11-20T10:00:00Z");
    const b = turnier("b", "active", "2026-11-21T10:00:00Z");
    const e = turnier("e", "draft", "2026-11-22T10:00:00Z");
    const z = turnier("z", "closed", "2026-11-23T10:00:00Z");
    expect(turnierFuerAblauf(a, [a, b, e])).toBe(a);
    expect(turnierFuerAblauf(null, [a, b, e])).toBe(b);
    expect(turnierFuerAblauf(null, [e, z])).toBe(e);
    expect(turnierFuerAblauf(null, [z])).toBe(z);
    expect(turnierFuerAblauf(null, [])).toBeNull();
  });
});
