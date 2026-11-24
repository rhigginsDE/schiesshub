/** Anbindung der neuen Serverfelder: gelöschtes Turnier, Katalogstand, fehlende Abschnitte, Vorlagen-Lücken. */
import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiFehler } from "../../api/client";
import { ereignisAnwenden } from "../../api/ereignisse";
import { TURNIER_SPEICHER } from "../../components/useAktivesTurnier";
import { turnierSchluessel } from "./abfragen";
import { abschnittEinfuegen, fehlendeAbschnitte } from "./ausschreibung/Ausschreibung";
import { dokumentAusEntwurf } from "./ausschreibung/dokument";
import type { AusschreibungDokument, Baustein } from "./ausschreibung/typen";
import {
  geloeschteVergessen,
  istGeloescht,
  schluesselEnthaelt,
  turnierGeloescht,
} from "./geloescht";
import { abschnittKurz } from "./klartext";
import { vorlagenLuecken } from "./senden";
import { beispielTurnier, beispielWettbewerb, STAND_ID, TURNIER_ID } from "./testdaten";
import type { Turnier } from "./typen";
import { disziplinFehlt, katalogStandText } from "./wettbewerbe/KatalogStand";

afterEach(() => {
  geloeschteVergessen();
  window.localStorage.clear();
});

describe("tournament.deleted", () => {
  it("nimmt das Turnier aus Liste und Cache, vergisst die Wahl und lädt es nicht neu", () => {
    const client = new QueryClient();
    const anderes = "99999999-9999-4999-8999-999999999999";
    client.setQueryData(turnierSchluessel.liste(), [
      { ...beispielTurnier(), id: TURNIER_ID },
      { ...beispielTurnier(), id: anderes },
    ] as Turnier[]);
    client.setQueryData(turnierSchluessel.uebersicht(TURNIER_ID), beispielTurnier());
    client.setQueryData(["anzeige", { turnier: TURNIER_ID }], 1);
    client.setQueryData(turnierSchluessel.uebersicht(anderes), beispielTurnier());
    window.localStorage.setItem(TURNIER_SPEICHER, JSON.stringify(TURNIER_ID));
    const neuLaden = vi.spyOn(client, "invalidateQueries");
    const reihenfolge: string[] = [];
    const vorher = (() => reihenfolge.push("behandlung")) as Parameters<
      typeof ereignisAnwenden
    >[0][number];
    neuLaden.mockImplementation(async () => {
      reihenfolge.push("neu laden");
    });

    ereignisAnwenden(
      [turnierSchluessel.alle, turnierGeloescht, vorher],
      { tournament_id: TURNIER_ID },
      client,
    );

    expect(reihenfolge).toEqual(["behandlung", "neu laden"]);
    expect(istGeloescht(TURNIER_ID)).toBe(true);
    expect(client.getQueryData<Turnier[]>(turnierSchluessel.liste())?.map((t) => t.id)).toEqual([
      anderes,
    ]);
    expect(client.getQueryData(turnierSchluessel.uebersicht(TURNIER_ID))).toBeUndefined();
    expect(client.getQueryData(["anzeige", { turnier: TURNIER_ID }])).toBeUndefined();
    expect(client.getQueryData(turnierSchluessel.uebersicht(anderes))).toBeDefined();
    expect(window.localStorage.getItem(TURNIER_SPEICHER)).toBeNull();
  });

  it("lässt die Wahl eines anderen Turniers stehen und übersieht Ereignisse ohne ID", () => {
    const client = new QueryClient();
    window.localStorage.setItem(TURNIER_SPEICHER, JSON.stringify("anderes"));
    turnierGeloescht({ tournament_id: TURNIER_ID }, client);
    turnierGeloescht(undefined, client);
    expect(window.localStorage.getItem(TURNIER_SPEICHER)).toBe(JSON.stringify("anderes"));
    expect(schluesselEnthaelt(["turnier", "x", { a: [TURNIER_ID] }], TURNIER_ID)).toBe(true);
    expect(schluesselEnthaelt(["turnier", "x"], TURNIER_ID)).toBe(false);
  });
});

describe("Katalogstand damals → heute", () => {
  it("nennt beide Stände, eine Korrektur ohne neuen Stand und eine fehlende Disziplin", () => {
    expect(
      katalogStandText({ catalog_stand_then: "2025-06-30", catalog_stand_now: "2026-06-30" }, "de"),
    ).toBe("Katalogstand damals 30.06.2025, heute 30.06.2026");
    expect(
      katalogStandText({ catalog_stand_then: "2026-06-30", catalog_stand_now: "2026-06-30" }, "de"),
    ).toBe("Katalogstand 30.06.2026, seitdem im Katalog korrigiert");
    const fehlt = { catalog_stand_then: "2025-06-30", catalog_stand_now: null };
    expect(katalogStandText(fehlt, "de")).toBe(
      "Übernommen mit Katalogstand 30.06.2025; die Disziplin fehlt jetzt im Katalog",
    );
    expect(disziplinFehlt(fehlt)).toBe(true);
  });
});

describe("Vorlage passt nicht zum Katalog", () => {
  it("liest die Lücken aus 409 template_unavailable, sonst null", () => {
    const inhalt = {
      detail: "…",
      code: "template_unavailable",
      template_id: "uebung",
      missing: [
        {
          kind: "competition",
          federation: "bds",
          code: "4403",
          message_de: "Kennziffer 4403 (BDS)",
        },
        { kind: "classes", federation: "bds" },
      ],
    };
    const fehler = new ApiFehler("konflikt", "/x", 409, "…", undefined, [], inhalt, inhalt.code);
    expect(vorlagenLuecken(fehler)).toEqual([
      {
        kind: "competition",
        federation: "bds",
        code: "4403",
        variant_id: null,
        message_de: "Kennziffer 4403 (BDS)",
      },
    ]);
    expect(vorlagenLuecken(new ApiFehler("konflikt", "/x", 409, "…"))).toBeNull();
    expect(vorlagenLuecken(new Error("x"))).toBeNull();
  });
});

describe("Ausschreibung: fehlende Abschnitte und Begriffe", () => {
  const block = (id: string, kind: Baustein["kind"] = "text"): Baustein => ({
    id,
    kind,
    heading: id,
    body: "",
    visible: true,
  });

  it("bietet nur an, was noch fehlt, und fügt an sinnvoller Stelle ein", () => {
    const alt = [block("begruessung"), block("wb", "competitions"), block("k", "classes")];
    const staende = block("schiessstaende", "ranges");
    expect(fehlendeAbschnitte([staende], alt)).toEqual([staende]);
    const neu = abschnittEinfuegen(alt, staende);
    // Hinter „Wettbewerbe“, vor „Klassen“ – wie in der Standardgliederung.
    expect(neu.map((b) => b.id)).toEqual(["begruessung", "wb", "schiessstaende", "k"]);
    expect(fehlendeAbschnitte([staende], neu)).toEqual([]);
    // Ohne passenden Nachbarn: vor den nächsten Nachfolger, sonst ans Ende.
    expect(abschnittEinfuegen([block("kontakt")], block("begruessung")).map((b) => b.id)).toEqual([
      "begruessung",
      "kontakt",
    ]);
    expect(abschnittEinfuegen([block("eigen")], block("x-unbekannt")).map((b) => b.id)).toEqual([
      "eigen",
      "x-unbekannt",
    ]);
  });

  it("ordnet lanes_text über range_id zu und nennt „Serie“ nach dem Verband", () => {
    const turnier = {
      ...beispielTurnier(),
      ranges: [
        { id: STAND_ID, tournament_id: TURNIER_ID, name: "Flintenstand", lane_count: 4, sort: 0 },
      ],
      competitions: [beispielWettbewerb()],
    } as Parameters<typeof dokumentAusEntwurf>[1];
    const server = {
      title: "x",
      tournament: { ...beispielTurnier(), currency: "EUR" },
      facts: {},
      terms: null,
      blocks: [
        {
          id: "schiessstaende",
          kind: "ranges",
          heading: "Schießstände",
          body: "",
          ranges: [
            { range_id: STAND_ID, name: "Umbenannt", lane_count: 4, lanes_text: "4 Stände" },
          ],
        },
      ],
    } as unknown as AusschreibungDokument;
    const dokument = dokumentAusEntwurf(
      { facts: {}, blocks: [block("schiessstaende", "ranges")] },
      turnier,
      server,
      "de",
    );
    expect(dokument.blocks[0]?.ranges?.[0]).toMatchObject({
      range_id: STAND_ID,
      name: "Flintenstand",
      lanes_text: "4 Stände",
    });

    const abschnitt = beispielWettbewerb().definition.variant.abschnitte[0];
    if (!abschnitt) throw new Error("Testdaten ohne Abschnitt");
    expect(abschnittKurz(abschnitt, "de")).toMatch(/^4 Serien/);
    expect(
      abschnittKurz(abschnitt, "de", {
        serie: "Durchgang",
        serien: "Durchgänge",
        trefferaufnahme: "T",
      }),
    ).toMatch(/^4 Durchgänge/);
  });
});
