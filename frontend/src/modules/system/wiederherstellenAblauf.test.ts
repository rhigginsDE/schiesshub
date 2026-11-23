import { describe, expect, it } from "vitest";
import { ApiFehler } from "../../api/client";
import {
  ausfuehrenAnfrage,
  datenUnveraendert,
  fehlendeBestaetigungen,
  istKurzeUnterbrechung,
  istZugangWeg,
  nachDerWahl,
  startAnsicht,
  verloreneEingaben,
  weiterFragen,
} from "./wiederherstellenAblauf";
import { lauf, QUELLE_SERVER, QUELLE_STICK, vorschau } from "./wiederherstellenTestdaten";

const wartung = new ApiFehler(
  "netzwerk",
  "/backup/restore/status",
  503,
  "Die Sicherung wird gerade wiederhergestellt.",
  10,
  [],
  { code: "maintenance" },
  "maintenance",
);

describe("Ablauf der Wiederherstellung", () => {
  it("beginnt mit der Auswahl, außer es läuft schon eine", () => {
    expect(startAnsicht(undefined)).toBe("waehlen");
    expect(startAnsicht(lauf({ state: "idle" }))).toBe("waehlen");
    expect(startAnsicht(lauf({ state: "succeeded" }))).toBe("waehlen");
    expect(startAnsicht(lauf())).toBe("fortschritt");
  });

  it("fragt das Passwort nur für verschlüsselte Sicherungen", () => {
    expect(nachDerWahl(QUELLE_STICK)).toBe("passwort");
    expect(nachDerWahl(QUELLE_SERVER)).toBe("vorschau");
  });

  it("sendet die Kennung der Sicherung als Bestätigung, Passwort nur wenn nötig", () => {
    expect(ausfuehrenAnfrage(vorschau(), "geheim geheim", true, false)).toEqual({
      source_id: QUELLE_STICK.id,
      passphrase: "geheim geheim",
      confirm: QUELLE_STICK.id,
      apply_journal: true,
      accept_lockout: false,
    });
    const server = vorschau({ source: QUELLE_SERVER, confirm: QUELLE_SERVER.id });
    expect(ausfuehrenAnfrage(server, "egal", false, false)).toMatchObject({
      passphrase: null,
      confirm: QUELLE_SERVER.id,
      apply_journal: false,
    });
  });

  it("nimmt das Aussperren nur an, wenn es droht und bestätigt ist", () => {
    const droht = vorschau({ access: { ...vorschau().access, lockout_risk: true } });
    expect(ausfuehrenAnfrage(droht, "x", true, true).accept_lockout).toBe(true);
    expect(ausfuehrenAnfrage(vorschau(), "x", true, true).accept_lockout).toBe(false);
    expect(fehlendeBestaetigungen(droht, { ersetzen: true, aussperren: false })).toEqual([
      "aussperren",
    ]);
    expect(fehlendeBestaetigungen(droht, { ersetzen: false, aussperren: true })).toEqual([
      "ersetzen",
    ]);
    expect(fehlendeBestaetigungen(vorschau(), { ersetzen: true, aussperren: false })).toEqual([]);
  });

  it("zählt ohne Nachtragen alle Eingaben seit der Sicherung als verloren", () => {
    expect(verloreneEingaben(vorschau(), true)).toBe(2);
    expect(verloreneEingaben(vorschau(), false)).toBe(9);
  });

  it("behandelt Wartung und kurze Funkstille als Teil des Ablaufs, nicht als Fehler", () => {
    expect(istKurzeUnterbrechung(wartung)).toBe(true);
    expect(istKurzeUnterbrechung(new ApiFehler("netzwerk", "/backup/restore/status"))).toBe(true);
    expect(istKurzeUnterbrechung(new ApiFehler("server", "/backup/restore/status", 500))).toBe(
      false,
    );
    expect(weiterFragen(lauf(), null)).toBe(true);
    expect(weiterFragen(lauf({ step: "swap" }), wartung)).toBe(true);
    expect(weiterFragen(lauf({ state: "succeeded" }), null)).toBe(false);
  });

  it("hört auf zu fragen, wenn der Zugang nach dem Tausch weg ist", () => {
    const weg = new ApiFehler("nicht_angemeldet", "/backup/restore/status", 401);
    expect(istZugangWeg(weg)).toBe(true);
    expect(weiterFragen(lauf(), weg)).toBe(false);
  });

  it("sagt nach einem Fehler vor dem Tausch, dass die Daten unverändert sind", () => {
    const vorher = lauf({
      state: "failed",
      step: "load",
      steps: lauf().steps.map((s) => (s.key === "load" ? { ...s, state: "failed" } : s)),
    });
    expect(datenUnveraendert(vorher)).toBe(true);
    const danach = lauf({
      state: "failed",
      step: "finish",
      steps: lauf().steps.map((s) => (s.key === "finish" ? { ...s, state: "failed" } : s)),
    });
    expect(datenUnveraendert(danach)).toBe(false);
    expect(datenUnveraendert(lauf())).toBe(false);
  });
});
