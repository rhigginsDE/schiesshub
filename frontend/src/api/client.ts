/** Schlanker, typisierter Zugriff auf die Schiesshub-API. */

export const API_BASIS = "/api/v1";

/**
 * Art des Fehlers, damit die Oberfläche sagen kann, was los ist und was zu tun ist.
 * - `netzwerk`: Server nicht erreichbar (keine Antwort oder 502/503/504 vom Proxy)
 * - `nicht_gefunden`: 404
 * - `anfrage`: sonstige 4xx
 * - `server`: 5xx
 * - `format`: Antwort ist kein lesbares JSON
 */
export type ApiFehlerArt = "netzwerk" | "nicht_gefunden" | "anfrage" | "server" | "format";

export class ApiFehler extends Error {
  readonly art: ApiFehlerArt;
  readonly pfad: string;
  readonly status?: number;
  /** Erklärung des Servers (`detail` von FastAPI), falls vorhanden. */
  readonly detail?: string;

  constructor(art: ApiFehlerArt, pfad: string, status?: number, detail?: string) {
    super(
      `API-Fehler (${art}${status ? ` ${status}` : ""}) bei ${pfad}${detail ? `: ${detail}` : ""}`,
    );
    this.name = "ApiFehler";
    this.art = art;
    this.pfad = pfad;
    this.status = status;
    this.detail = detail;
  }
}

export type AbfrageParameter = Record<string, string | number | boolean | null | undefined>;

export interface AnfrageOptionen {
  /** Query-Parameter; leere Werte werden weggelassen. */
  parameter?: AbfrageParameter;
  signal?: AbortSignal;
  /** Statuscodes, deren JSON-Inhalt trotzdem als Antwort gilt (z. B. 503 bei `/health`). */
  auchBeiStatus?: number[];
}

export function apiUrl(pfad: string, parameter?: AbfrageParameter): string {
  const suche = new URLSearchParams();
  for (const [name, wert] of Object.entries(parameter ?? {})) {
    if (wert === null || wert === undefined || wert === "") continue;
    suche.set(name, String(wert));
  }
  const anhang = suche.toString();
  return `${API_BASIS}${pfad}${anhang ? `?${anhang}` : ""}`;
}

function artAusStatus(status: number): ApiFehlerArt {
  if (status === 404) return "nicht_gefunden";
  if (status === 502 || status === 503 || status === 504) return "netzwerk";
  if (status >= 500) return "server";
  return "anfrage";
}

async function detailAus(antwort: Response): Promise<string | undefined> {
  try {
    const inhalt: unknown = await antwort.json();
    if (inhalt && typeof inhalt === "object" && "detail" in inhalt) {
      const { detail } = inhalt as { detail: unknown };
      return typeof detail === "string" ? detail : JSON.stringify(detail);
    }
  } catch {
    // Antwort ohne JSON-Inhalt: kein Detail
  }
  return undefined;
}

export async function apiGet<T>(pfad: string, optionen: AnfrageOptionen = {}): Promise<T> {
  let antwort: Response;
  try {
    antwort = await fetch(apiUrl(pfad, optionen.parameter), {
      headers: { Accept: "application/json" },
      signal: optionen.signal,
    });
  } catch (fehler) {
    if (fehler instanceof DOMException && fehler.name === "AbortError") throw fehler;
    throw new ApiFehler("netzwerk", pfad);
  }

  if (!antwort.ok && !optionen.auchBeiStatus?.includes(antwort.status)) {
    throw new ApiFehler(
      artAusStatus(antwort.status),
      pfad,
      antwort.status,
      await detailAus(antwort),
    );
  }

  try {
    return (await antwort.json()) as T;
  } catch {
    throw new ApiFehler("format", pfad, antwort.status);
  }
}
