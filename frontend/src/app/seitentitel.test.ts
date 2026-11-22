import { describe, expect, it } from "vitest";
import type { ModulManifest } from "./modul";
import { modulZuPfad, seitentitel, turnierIdAusPfad } from "./seitentitel";

const modul = (id: string, pfad: string): ModulManifest =>
  ({ id, namensraum: id, navigation: { pfad }, berechtigung: null, routen: [] }) as never;

describe("seitentitel", () => {
  it("setzt Seite, Turnier und Marke zusammen und lässt leere Teile weg", () => {
    expect(seitentitel(["Anmeldung", "Nachttest Fallscheibe"], "Schiesshub")).toBe(
      "Anmeldung – Nachttest Fallscheibe – Schiesshub",
    );
    expect(seitentitel(["Anmeldung", undefined, " "], "Schiesshub")).toBe("Anmeldung – Schiesshub");
    expect(seitentitel([], "Schiesshub")).toBe("Schiesshub");
  });
});

describe("modulZuPfad", () => {
  const module = [modul("turnier", "/turnier"), modul("katalog", "/turnier/katalog")];

  it("nimmt das Modul mit dem längsten passenden Pfad", () => {
    expect(modulZuPfad(module, "/turnier/katalog/bds/1001")?.id).toBe("katalog");
    expect(modulZuPfad(module, "/turnier/abc")?.id).toBe("turnier");
    expect(modulZuPfad(module, "/turniere")).toBeUndefined();
  });
});

describe("turnierIdAusPfad", () => {
  it("liest die ID direkt hinter dem Modulpfad", () => {
    const turnier = modul("turnier", "/turnier");
    expect(turnierIdAusPfad(turnier, "/turnier/abc-123")).toBe("abc-123");
    expect(turnierIdAusPfad(turnier, "/turnier/abc-123/druck")).toBe("abc-123");
    expect(turnierIdAusPfad(turnier, "/turnier")).toBeNull();
  });
});
