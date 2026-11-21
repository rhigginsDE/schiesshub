/** Schlanker, typisierter Zugriff auf die Schiesshub-API. */

export const API_BASIS = "/api/v1";

/**
 * Art des Fehlers, damit die Oberfläche sagen kann, was los ist und was zu tun ist.
 * - `netzwerk`: Server nicht erreichbar (keine Antwort oder 502/503/504 vom Proxy)
 * - `nicht_angemeldet`: 401 (Gerät nicht gekoppelt oder niemand angemeldet)
 * - `verboten`: 403 (Berechtigung fehlt)
 * - `nicht_gefunden`: 404
 * - `konflikt`: 409 (z. B. Dublette, Zustand passt nicht)
 * - `gesperrt`: 429 (zu viele Fehlversuche)
 * - `anfrage`: sonstige 4xx
 * - `server`: 5xx
 * - `format`: Antwort ist kein lesbares JSON
 */
export type ApiFehlerArt =
  | "netzwerk"
  | "nicht_angemeldet"
  | "verboten"
  | "nicht_gefunden"
  | "konflikt"
  | "gesperrt"
  | "anfrage"
  | "server"
  | "format";

export class ApiFehler extends Error {
  readonly art: ApiFehlerArt;
  readonly pfad: string;
  readonly status?: number;
  /** Erklärung des Servers (`detail` von FastAPI), falls vorhanden. */
  readonly detail?: string;
  /** Sekunden bis zum nächsten sinnvollen Versuch (Header `Retry-After`, z. B. bei 429). */
  readonly wiederholenNachSekunden?: number;

  constructor(
    art: ApiFehlerArt,
    pfad: string,
    status?: number,
    detail?: string,
    wiederholenNachSekunden?: number,
  ) {
    super(
      `API-Fehler (${art}${status ? ` ${status}` : ""}) bei ${pfad}${detail ? `: ${detail}` : ""}`,
    );
    this.name = "ApiFehler";
    this.art = art;
    this.pfad = pfad;
    this.status = status;
    this.detail = detail;
    this.wiederholenNachSekunden = wiederholenNachSekunden;
  }
}

/** Meldung des Servers in Klartext, wenn er eine geliefert hat (nicht bei Prüffehlern als Liste). */
export function serverMeldung(fehler: unknown): string | undefined {
  if (!(fehler instanceof ApiFehler) || !fehler.detail) return undefined;
  const text = fehler.detail.trim();
  return text.startsWith("[") || text.startsWith("{") ? undefined : text;
}

type FehlerBeobachter = (fehler: ApiFehler) => void;
const beobachter = new Set<FehlerBeobachter>();

/**
 * Meldet 401 und 403 von jedem Endpunkt an die App-Shell (zurück zur Anmeldung bzw. Hinweis
 * „Berechtigung fehlt“). Gibt eine Funktion zum Abmelden zurück.
 * Anfragen mit `still: true` melden nichts, z. B. Hintergrundabfragen der Kopfzeile.
 */
export function beiApiFehler(rueckruf: FehlerBeobachter): () => void {
  beobachter.add(rueckruf);
  return () => beobachter.delete(rueckruf);
}

function melden(fehler: ApiFehler, optionen: AnfrageOptionen): ApiFehler {
  if (!optionen.still && (fehler.art === "nicht_angemeldet" || fehler.art === "verboten")) {
    for (const rueckruf of beobachter) rueckruf(fehler);
  }
  return fehler;
}

function sekundenAus(antwort: Response): number | undefined {
  const wert = antwort.headers?.get?.("Retry-After");
  if (!wert) return undefined;
  const sekunden = Number(wert);
  return Number.isFinite(sekunden) && sekunden > 0 ? Math.ceil(sekunden) : undefined;
}

async function fehlerAus(antwort: Response, pfad: string, optionen: AnfrageOptionen) {
  return melden(
    new ApiFehler(
      artAusStatus(antwort.status),
      pfad,
      antwort.status,
      await detailAus(antwort),
      sekundenAus(antwort),
    ),
    optionen,
  );
}

export type AbfrageParameter = Record<string, string | number | boolean | null | undefined>;

export interface AnfrageOptionen {
  /** Query-Parameter; leere Werte werden weggelassen. */
  parameter?: AbfrageParameter;
  signal?: AbortSignal;
  /** Statuscodes, deren JSON-Inhalt trotzdem als Antwort gilt (z. B. 503 bei `/health`). */
  auchBeiStatus?: number[];
  /** 401/403 nicht an `beiApiFehler` melden (die Stelle behandelt den Fehler selbst). */
  still?: boolean;
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
  if (status === 401) return "nicht_angemeldet";
  if (status === 403) return "verboten";
  if (status === 404) return "nicht_gefunden";
  if (status === 409) return "konflikt";
  if (status === 429) return "gesperrt";
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
    throw await fehlerAus(antwort, pfad, optionen);
  }

  try {
    return (await antwort.json()) as T;
  } catch {
    throw new ApiFehler("format", pfad, antwort.status);
  }
}

export type Schreibmethode = "POST" | "PUT" | "PATCH" | "DELETE";

export interface SendeOptionen extends AnfrageOptionen {
  /** Inhalt ohne JSON-Umwandlung senden, z. B. CSV. */
  roh?: { inhalt: BodyInit; typ: string };
}

/**
 * Schreibende Anfrage. Sendet den Inhalt als JSON und den Header `X-Schiesshub-Request`,
 * den das Backend für alle schreibenden Methoden verlangt (Schutz vor fremden Seiten).
 * Antworten ohne Inhalt (204) ergeben `undefined`.
 */
export async function apiSenden<T = void>(
  methode: Schreibmethode,
  pfad: string,
  inhalt?: unknown,
  optionen: SendeOptionen = {},
): Promise<T> {
  const kopf: Record<string, string> = {
    Accept: "application/json",
    "X-Schiesshub-Request": "1",
  };
  let koerper: BodyInit | undefined;
  if (optionen.roh) {
    kopf["Content-Type"] = optionen.roh.typ;
    koerper = optionen.roh.inhalt;
  } else if (inhalt !== undefined) {
    kopf["Content-Type"] = "application/json";
    koerper = JSON.stringify(inhalt);
  }

  let antwort: Response;
  try {
    antwort = await fetch(apiUrl(pfad, optionen.parameter), {
      method: methode,
      headers: kopf,
      body: koerper,
      signal: optionen.signal,
    });
  } catch (fehler) {
    if (fehler instanceof DOMException && fehler.name === "AbortError") throw fehler;
    throw new ApiFehler("netzwerk", pfad);
  }

  if (!antwort.ok && !optionen.auchBeiStatus?.includes(antwort.status)) {
    throw await fehlerAus(antwort, pfad, optionen);
  }
  if (antwort.status === 204) return undefined as T;

  try {
    return (await antwort.json()) as T;
  } catch {
    throw new ApiFehler("format", pfad, antwort.status);
  }
}

export interface Datei {
  inhalt: Blob;
  /** Dateiname aus `Content-Disposition`, sonst der Rückfallname */
  name: string;
}

/** Datei herunterladen (z. B. eine Sicherung). Fehler kommen wie bei `apiGet` als `ApiFehler`. */
export async function apiDatei(
  pfad: string,
  rueckfallName: string,
  optionen: AnfrageOptionen = {},
): Promise<Datei> {
  let antwort: Response;
  try {
    antwort = await fetch(apiUrl(pfad, optionen.parameter), { signal: optionen.signal });
  } catch (fehler) {
    if (fehler instanceof DOMException && fehler.name === "AbortError") throw fehler;
    throw new ApiFehler("netzwerk", pfad);
  }
  if (!antwort.ok) throw await fehlerAus(antwort, pfad, optionen);
  const kopf = antwort.headers.get("Content-Disposition") ?? "";
  const treffer = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(kopf);
  const name = treffer?.[1] ? decodeURIComponent(treffer[1]) : rueckfallName;
  return { inhalt: await antwort.blob(), name };
}
