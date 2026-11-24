import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BEGRIFFE_RUECKFALL,
  type Begriffe,
  type Begriffssaetze,
  begriffeFuer,
  useBegriffe,
} from "./begriffe";

const standard: Begriffe = { ...BEGRIFFE_RUECKFALL, startzeit: "Starttermin" };
const saetze: Begriffssaetze = {
  default: standard,
  federations: {
    bds: { ...standard },
    dsb: {
      ...standard,
      startzeit: "Startzeit",
      ergebnisgleichheit: "Ergebnisgleichheit",
      abbruch: "aufgegeben",
      kennziffer: "Kennzahl",
    },
  },
};

describe("begriffeFuer", () => {
  it("nimmt den Satz des Verbands, Groß-/Kleinschreibung egal", () => {
    expect(begriffeFuer(saetze, "DSB").kennziffer).toBe("Kennzahl");
    expect(begriffeFuer(saetze, "dsb").startzeit).toBe("Startzeit");
    expect(begriffeFuer(saetze, "BDS").kennziffer).toBe("Kennziffer");
  });

  it("fällt ohne oder bei unbekanntem Verband auf den Standardsatz zurück", () => {
    const eigen = { ...saetze, default: { ...standard, ergebnisliste: "Ergebnisse" } };
    expect(begriffeFuer(eigen, null).ergebnisliste).toBe("Ergebnisse");
    expect(begriffeFuer(eigen, "issf").ergebnisliste).toBe("Ergebnisse");
  });

  it("füllt fehlende oder leere Wörter je Begriff auf: Verband, Standard, fester Text", () => {
    const luecken = {
      default: { ...standard, schuetzenstand: "" },
      federations: { dsb: { kennziffer: "Kennzahl" } as Begriffe },
    } satisfies Begriffssaetze;
    const dsb = begriffeFuer(luecken, "dsb");
    expect(dsb.kennziffer).toBe("Kennzahl");
    expect(dsb.startzeit).toBe("Starttermin");
    expect(dsb.schuetzenstand).toBe("Schützenstand");
  });

  it("liefert ohne Daten vom Server die festen Wörter", () => {
    expect(begriffeFuer(null, "bds")).toEqual(BEGRIFFE_RUECKFALL);
    expect(begriffeFuer(undefined)).toEqual(BEGRIFFE_RUECKFALL);
  });

  it("hat im Rückfall die Mehrzahlen und Serienwörter (Standardsatz des Servers)", () => {
    expect(BEGRIFFE_RUECKFALL).toMatchObject({
      ergebnislisten: "Ergebnislisten",
      durchgaenge: "Durchgänge",
      serie: "Serie",
      serien: "Serien",
      wertungsserien: "Wertungsserien",
      klassen: "Wettbewerbsklassen",
    });
    // Leere Wörter im Satz des Verbands füllt der Rückfall je Begriff auf
    const ohneSerie = { default: standard, federations: { dsb: { serien: "" } as Begriffe } };
    expect(begriffeFuer(ohneSerie, "dsb").serien).toBe("Serien");
  });

  it("verändert den Rückfall nicht", () => {
    begriffeFuer(saetze, "dsb");
    expect(BEGRIFFE_RUECKFALL.kennziffer).toBe("Kennziffer");
  });
});

describe("useBegriffe", () => {
  afterEach(() => vi.unstubAllGlobals());

  function mitClient() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  }

  it("lädt /terms einmal und gibt die Sätze zurück", async () => {
    const abruf = vi.fn<typeof fetch>(
      async () =>
        new Response(JSON.stringify(saetze), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", abruf);
    const { result } = renderHook(() => useBegriffe(), { wrapper: mitClient() });
    expect(result.current).toBeNull();
    await waitFor(() => expect(result.current).not.toBeNull());
    expect(begriffeFuer(result.current, "dsb").kennziffer).toBe("Kennzahl");
    expect(String(abruf.mock.calls[0]?.[0])).toBe("/api/v1/terms");
  });

  it("bleibt bei einem Fehler des Servers still beim Rückfall", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(async () => new Response("{}", { status: 404 })),
    );
    const { result } = renderHook(() => begriffeFuer(useBegriffe(), "bds"), {
      wrapper: mitClient(),
    });
    await new Promise((fertig) => setTimeout(fertig, 20));
    expect(result.current).toEqual(BEGRIFFE_RUECKFALL);
  });
});
