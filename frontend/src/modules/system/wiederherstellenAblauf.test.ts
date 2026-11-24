import { describe, expect, it } from "vitest";
import { ApiFehler } from "../../api/client";
import system from "../../locales/de/system.json";
import {
  ausfuehrenAnfrage,
  datenUnveraendert,
  ergebnisHinweise,
  fehlendeBestaetigungen,
  fehltInSicherung,
  GRUND_CODES,
  grundText,
  istKurzeUnterbrechung,
  istZugangWeg,
  kopieOhnePasswort,
  MELDUNG_CODES,
  meldungTexte,
  nachDerWahl,
  orteDerQuelle,
  quellenZusammenfassen,
  startAnsicht,
  type UebersprungenerStart,
  uebersprungeneStarts,
  verloreneEingaben,
  weiterFragen,
} from "./wiederherstellenAblauf";
import {
  ausgesperrt,
  lauf,
  QUELLE_ALT,
  QUELLE_SERVER,
  QUELLE_STICK,
  vorschau,
} from "./wiederherstellenTestdaten";

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

  it("zeigt jede Sicherung einmal, mit allen Orten", () => {
    expect(quellenZusammenfassen([QUELLE_STICK, QUELLE_SERVER, QUELLE_ALT])).toEqual([
      QUELLE_STICK,
      QUELLE_ALT,
    ]);
    expect(orteDerQuelle(QUELLE_STICK)).toEqual(["usb", "local"]);
    expect(orteDerQuelle({ ...QUELLE_STICK, locations: undefined })).toEqual(["usb"]);
    expect(
      orteDerQuelle({ ...QUELLE_SERVER, locations: ["pre_restore", "local", "local"] }),
    ).toEqual(["local", "pre_restore"]);
  });

  it("findet die Kopie ohne Passwort auf dem Server", () => {
    expect(kopieOhnePasswort(QUELLE_STICK)).toMatchObject({
      id: QUELLE_SERVER.id,
      location: "local",
      needs_passphrase: false,
      contains_keys: false,
    });
    expect(kopieOhnePasswort(QUELLE_SERVER)).toBeNull();
    expect(kopieOhnePasswort({ ...QUELLE_STICK, other_ids: [] })).toBeNull();
  });

  it("nimmt für bekannte Kennungen eigene Texte, sonst den des Servers", () => {
    const t = (schluessel: string, werte?: Record<string, unknown>) =>
      `[${schluessel}${werte?.was ? `|${werte.was}` : ""}]`;
    expect(
      meldungTexte(
        [
          { code: "schema_newer", message_de: "Server: neuer" },
          { code: "lockout", message_de: "Server: fehlt" },
          { code: "unbekannt_neu", message_de: "Server: etwas Neues" },
          { code: "module_restart_failed", message_de: "Modul A" },
          { code: "module_restart_failed", message_de: "Modul B" },
        ],
        t,
        { was: "dieses Gerät" },
      ),
    ).toEqual([
      "[wiederherstellen.meldung.schema_newer|dieses Gerät]",
      "[wiederherstellen.meldung.lockout|dieses Gerät]",
      "Server: etwas Neues",
      "[wiederherstellen.meldung.module_restart_failed|dieses Gerät]",
    ]);
    expect(meldungTexte(undefined, t)).toEqual([]);
  });

  it("hat für jede bekannte Kennung und jeden Grund einen Text", () => {
    const texte = system.wiederherstellen as {
      meldung: Record<string, string>;
      nachtragen_grund: Record<string, string>;
    };
    for (const code of MELDUNG_CODES) expect(texte.meldung[code], code).toBeTruthy();
    for (const code of GRUND_CODES) expect(texte.nachtragen_grund[code], code).toBeTruthy();
    // Einfache Sprache: keine Technikwörter in den eigenen Texten
    const alle = [...Object.values(texte.meldung), ...Object.values(texte.nachtragen_grund)];
    for (const text of alle) expect(text).not.toMatch(/Mitschrift|Abzug|Berechtigungsprüfung/);
  });

  it("sagt, was in der Sicherung fehlt", () => {
    expect(fehltInSicherung(ausgesperrt())).toEqual(["konto", "geraet"]);
    expect(
      fehltInSicherung({ ...ausgesperrt(), account_in_backup: true, device_in_backup: true }),
    ).toEqual(["rolle"]);
    expect(fehltInSicherung(vorschau().access)).toEqual([]);
  });

  it("listet übersprungene Starts sortiert, mit Grund in Klartext", () => {
    const start = (teil: Partial<UebersprungenerStart>): UebersprungenerStart => ({
      competition_name: "Luftgewehr",
      competition_code: "1.10",
      start_number: 10,
      attempt: 1,
      reason_code: "start_not_in_backup",
      message_de: "Server",
      ...teil,
    });
    const status = lauf({
      state: "succeeded",
      result: {
        database: "a",
        previous_database: "b",
        pre_restore_backup: null,
        schema_upgraded: false,
        journal: null,
        keys_installed: [],
        keys_set_aside: [],
        after_backup_ok: false,
        notes: [],
        note_items: [
          { code: "after_backup_failed", message_de: "x" },
          { code: "module_restart_failed", message_de: "y" },
        ],
        skipped_starts: [
          start({ start_number: 12 }),
          start({ competition_name: "Kleinkaliber", start_number: 40 }),
          start({ start_number: 10, attempt: 2 }),
          start({ start_number: null }),
          start({ start_number: 10, attempt: 1 }),
        ],
      },
    });
    expect(
      uebersprungeneStarts(status).map((s) => [s.competition_name, s.start_number, s.attempt]),
    ).toEqual([
      ["Kleinkaliber", 40, 1],
      ["Luftgewehr", 10, 1],
      ["Luftgewehr", 10, 2],
      ["Luftgewehr", 12, 1],
      ["Luftgewehr", null, 1],
    ]);
    // „Sicherung danach fehlgeschlagen“ steht schon in der Zusammenfassung
    expect(ergebnisHinweise(status).map((m) => m.code)).toEqual(["module_restart_failed"]);

    const t = (schluessel: string) => `[${schluessel}]`;
    expect(grundText(start({}), t)).toBe("[wiederherstellen.nachtragen_grund.start_not_in_backup]");
    const unbekannt = start({ message_de: "Neuer Grund vom Server" });
    (unbekannt as { reason_code: string }).reason_code = "kuenftig";
    expect(grundText(unbekannt, t)).toBe("Neuer Grund vom Server");
  });

  it("nimmt die Liste aus dem Bericht, wenn das Ergebnis selbst keine hat", () => {
    const status = lauf({
      state: "succeeded",
      result: {
        database: "a",
        previous_database: "b",
        pre_restore_backup: null,
        schema_upgraded: false,
        journal: {
          applied: 0,
          present: 0,
          missing_events: 1,
          conflicts: 0,
          status_changes: 0,
          recomputed_competitions: 0,
          lines: [],
          skipped_starts: [
            {
              competition_name: "Luftpistole",
              competition_code: "2.10",
              start_number: 5,
              attempt: 1,
              reason_code: "does_not_match",
              message_de: "x",
            },
          ],
        },
        keys_installed: [],
        keys_set_aside: [],
        after_backup_ok: true,
        notes: [],
      },
    });
    expect(uebersprungeneStarts(status)).toHaveLength(1);
    expect(uebersprungeneStarts(lauf())).toEqual([]);
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
