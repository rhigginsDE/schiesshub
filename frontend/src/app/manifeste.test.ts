import { describe, expect, it } from "vitest";
import { artAusStatus } from "../api/client";
import allgemein from "../locales/de/allgemein.json";
import system from "../locales/de/system.json";
import { module } from "../modules";
import { BEREICHE } from "../modules/system/bereiche";
import { textSchluessel } from "../modules/system/rollenMatrix";
import { type Anforderung, darfMit, type Rechte } from "./berechtigungen";
import { stationenAus } from "./modul";

/**
 * Die echten Berechtigungen sind die, für die die Rechte-Matrix einen Namen hat
 * (`system.json` → `berechtigungen`, gepflegt nach `backend/app/modules/*` → `permissions`).
 * Eine erfundene Berechtigung im Frontend sperrt die Seite für jede Rolle außer dem Administrator.
 */
const ECHTE = new Set(Object.keys(system.berechtigungen));

function rechteAus(anforderung: Anforderung): string[] {
  if (anforderung === null) return [];
  return typeof anforderung === "string" ? [anforderung] : [...anforderung];
}

/** Quelltexte aller Dateien, um Berechtigungen in `useDarf(…)` und `darfMit(…, …)` zu finden. */
const quellen = import.meta.glob<string>(["../**/*.ts", "../**/*.tsx", "!../**/*.test.*"], {
  eager: true,
  query: "?raw",
  import: "default",
});

const AUFRUF = /(?:useDarf\(|darfMit\(\s*\w+,)\s*("[^"]*"|\[[^\]]*\])/g;

describe("Berechtigungen im Frontend", () => {
  it("jedes Manifest nennt nur echte Berechtigungen", () => {
    const falsch = module.flatMap((modul) =>
      rechteAus(modul.berechtigung)
        .filter((recht) => !ECHTE.has(textSchluessel(recht)))
        .map((recht) => `${modul.id}: ${recht}`),
    );
    expect(falsch).toEqual([]);
  });

  it("die Bereiche der Station System nennen nur echte Berechtigungen", () => {
    const falsch = BEREICHE.flatMap((bereich) =>
      rechteAus(bereich.berechtigung).filter((recht) => !ECHTE.has(textSchluessel(recht))),
    );
    expect(falsch).toEqual([]);
  });

  it("useDarf und darfMit fragen nur echte Berechtigungen ab", () => {
    const falsch: string[] = [];
    for (const [datei, text] of Object.entries(quellen)) {
      for (const treffer of text.matchAll(AUFRUF)) {
        for (const [, recht] of (treffer[1] ?? "").matchAll(/"([^"]+)"/g)) {
          if (recht && !ECHTE.has(textSchluessel(recht))) falsch.push(`${datei}: ${recht}`);
        }
      }
    }
    expect(falsch).toEqual([]);
  });
});

describe("Texte der App-Shell", () => {
  const dateien = import.meta.glob<Record<string, unknown>>("../locales/de/*.json", {
    eager: true,
    import: "default",
  });
  const namensraum = (name: string) => dateien[`../locales/de/${name}.json`];

  it("jedes Modul hat Titel und Zweck in seiner Sprachdatei", () => {
    const fehlt = module.flatMap((modul) => {
      const texte = namensraum(modul.namensraum);
      return ["titel", "zweck"]
        .filter((schluessel) => typeof texte?.[schluessel] !== "string")
        .map((schluessel) => `${modul.namensraum}:${schluessel}`);
    });
    expect(fehlt).toEqual([]);
  });

  it("jede Fehlerart hat Titel und Text für den Fehlerzustand", () => {
    // Alle Arten, die `artAusStatus` liefern kann, dazu „format“ und „unbekannt“.
    const arten = new Set([
      ...[400, 401, 403, 404, 409, 422, 429, 500, 502].map(artAusStatus),
      "format",
      "unbekannt",
    ]);
    const fehler = allgemein.fehler as Record<string, unknown>;
    const fehlt = [...arten].filter((art) => {
      const eintrag = fehler[art] as { titel?: unknown; text?: unknown } | undefined;
      return typeof eintrag?.titel !== "string" || typeof eintrag?.text !== "string";
    });
    expect(fehlt).toEqual([]);
  });
});

describe("Stationen", () => {
  const sichtbar = (erlaubt: string[]) => {
    const rechte: Rechte = { offen: false, erlaubt };
    return module.filter((modul) => darfMit(rechte, modul.berechtigung));
  };
  const ids = (erlaubt: string[]) => stationenAus(module, sichtbar(erlaubt)).map((m) => m.id);

  it("der Stand wird zur Station, wenn die Erfassung fehlt", () => {
    expect(ids(["start.call", "start.read", "tournament.read"])).toEqual(["turnier", "stand"]);
    expect(ids(["result.capture", "start.call", "start.read"])).toEqual(["erfassung"]);
  });

  it("die Kasse sieht die Anmeldung", () => {
    expect(ids(["entry.read", "entry.edit", "person.read", "tournament.read"])).toEqual([
      "turnier",
      "anmeldung",
    ]);
  });
});
