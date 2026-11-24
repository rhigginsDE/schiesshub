import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiFehler, istWartungsFehler } from "../api/client";
import { apiAttrappe } from "../test/app";
import { KEINE_WARTUNG, useWartung, WARTUNG_SCHLUESSEL, wartungAus } from "./wartung";

describe("Wartung während einer Wiederherstellung", () => {
  it("liest den Zustand vom Server", () => {
    expect(
      wartungAus({
        active: true,
        exclusive: false,
        message_de: "Die Sicherung wird gerade wiederhergestellt.",
        since: "2026-11-23T21:10:00Z",
      }),
    ).toEqual({
      active: true,
      exclusive: false,
      message_de: "Die Sicherung wird gerade wiederhergestellt.",
      since: "2026-11-23T21:10:00Z",
    });
    expect(wartungAus({ active: false, exclusive: false, message_de: null, since: null })).toEqual(
      KEINE_WARTUNG,
    );
  });

  it("versteht 503 mit code maintenance als Tausch der Datenbank", () => {
    expect(
      wartungAus({ detail: "Die Datenbank wird gerade getauscht.", code: "maintenance" }),
    ).toEqual({
      active: true,
      exclusive: true,
      message_de: "Die Datenbank wird gerade getauscht.",
      since: null,
    });
  });

  it("unbekannte Antworten heißen: keine Wartung", () => {
    expect(wartungAus(null)).toEqual(KEINE_WARTUNG);
    expect(wartungAus({ detail: "Nicht gefunden" })).toEqual(KEINE_WARTUNG);
  });

  it("erkennt Wartungsfehler an Status und code", () => {
    const wartung = new ApiFehler("netzwerk", "/x", 503, "…", 10, [], {}, "maintenance");
    expect(istWartungsFehler(wartung)).toBe(true);
    expect(istWartungsFehler(new ApiFehler("netzwerk", "/x", 503))).toBe(false);
    expect(istWartungsFehler(new Error("x"))).toBe(false);
  });
});

describe("Ende der Wartung", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lädt die Daten genau einmal neu, wenn die Wartung endet", async () => {
    // Der Server meldet das Ende erst, wenn die neue Datenbank antwortet: Neu laden darf sofort.
    let aktiv = true;
    apiAttrappe({
      "/backup/maintenance": () =>
        new Response(
          JSON.stringify({ active: aktiv, exclusive: false, message_de: null, since: null }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    });
    const daten = vi.fn(async () => "Stand");
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);
    const { result } = renderHook(
      () => {
        useQuery({ queryKey: ["daten"], queryFn: daten });
        return useWartung();
      },
      { wrapper },
    );
    await waitFor(() => expect(result.current.active).toBe(true));
    expect(daten).toHaveBeenCalledTimes(1);

    // Ereignis `backup.maintenance` mit `active: false`, auf manchen Geräten doppelt (Ereignis
    // und regelmäßiges Nachfragen): trotzdem nur ein Neuladen.
    aktiv = false;
    await act(() => queryClient.refetchQueries({ queryKey: WARTUNG_SCHLUESSEL }));
    await waitFor(() => expect(result.current.active).toBe(false));
    await waitFor(() => expect(daten).toHaveBeenCalledTimes(2));
    await act(() => queryClient.refetchQueries({ queryKey: WARTUNG_SCHLUESSEL }));
    await act(() => queryClient.invalidateQueries({ queryKey: WARTUNG_SCHLUESSEL }));
    expect(daten).toHaveBeenCalledTimes(2);
    queryClient.clear();
  });
});
