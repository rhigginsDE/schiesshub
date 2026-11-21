import { createMemoryHistory } from "@tanstack/react-router";
import { render } from "@testing-library/react";
import { vi } from "vitest";
import { App } from "../App";
import { erstelleQueryClient } from "../app/queryClient";
import { erstelleRouter } from "../app/router";
import { module } from "../modules";

/** Antwort je API-Pfad (ohne `/api/v1`, mit Query-Teil). Funktion = berechnete Antwort. */
export type ApiAttrappe = Record<string, unknown | (() => Response)>;

/**
 * Ersetzt `fetch` durch feste Antworten. Unbekannte Pfade antworten mit 404,
 * damit ein Test nicht unbemerkt ins Leere fragt.
 */
export function apiAttrappe(antworten: ApiAttrappe) {
  const attrappe = vi.fn(async (eingabe: RequestInfo | URL) => {
    const pfad = String(eingabe).replace(/^\/api\/v1/, "");
    if (!(pfad in antworten)) {
      return new Response(JSON.stringify({ detail: `Kein Testwert für ${pfad}` }), { status: 404 });
    }
    const antwort = antworten[pfad];
    if (typeof antwort === "function") return (antwort as () => Response)();
    return new Response(JSON.stringify(antwort), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", attrappe);
  return attrappe;
}

/** Rendert die ganze App (Shell, Module, Router) an der angegebenen Adresse. */
export function renderApp(adresse: string) {
  const router = erstelleRouter(module, createMemoryHistory({ initialEntries: [adresse] }));
  const queryClient = erstelleQueryClient({ wiederholen: false });
  return render(<App router={router} queryClient={queryClient} module={module} />);
}
