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

/** Fehler eines einzelnen Eingabefelds, wie ihn der Server meldet. */
export interface FeldFehler {
  /** Feldpfad mit Punkten, z. B. `settings.currency` oder `definition.variant.abschnitte.0.serien`; leer = ganze Anfrage */
  feld: string;
  meldung: string;
}

export class ApiFehler extends Error {
  readonly art: ApiFehlerArt;
  readonly pfad: string;
  readonly status?: number;
  /** Erklärung des Servers (`detail` von FastAPI), falls vorhanden. */
  readonly detail?: string;
  /** Sekunden bis zum nächsten sinnvollen Versuch (Header `Retry-After`, z. B. bei 429). */
  readonly wiederholenNachSekunden?: number;
  /**
   * Feldgenaue Meldungen aus der Server-Antwort (`errors: [{field, message}]`, sonst die
   * Standardliste von FastAPI in `detail`). Leer, wenn der Server keine geliefert hat.
   */
  readonly felder: readonly FeldFehler[];
  /**
   * Gelesener JSON-Inhalt der Fehlerantwort, für Stellen mit eigenen Zusatzangaben (z. B. 409 mit
   * dem aktuellen Stand eines Ergebnisses). `undefined`, wenn die Antwort kein JSON hatte.
   */
  readonly inhalt?: unknown;
  /**
   * Maschinenlesbarer Grund aus der Fehlerantwort (`{"detail": …, "code": …}`), z. B. bei 401
   * `device_unknown`, `device_revoked`, `session_expired`, `login_required`, `login_failed` oder
   * bei 409 `heat_imminent`. `undefined`, wenn der Server keinen liefert.
   */
  readonly code?: string;

  constructor(
    art: ApiFehlerArt,
    pfad: string,
    status?: number,
    detail?: string,
    wiederholenNachSekunden?: number,
    felder: readonly FeldFehler[] = [],
    inhalt?: unknown,
    code?: string,
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
    this.felder = felder;
    this.inhalt = inhalt;
    this.code = code;
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

/** `code` aus einer Fehlerantwort, falls es ein nicht leerer Text ist. */
function codeAus(inhalt: unknown): string | undefined {
  if (!inhalt || typeof inhalt !== "object") return undefined;
  const wert = (inhalt as { code?: unknown }).code;
  return typeof wert === "string" && wert !== "" ? wert : undefined;
}

async function fehlerAus(antwort: Response, pfad: string, optionen: AnfrageOptionen) {
  const { detail, felder, inhalt } = await inhaltAus(antwort);
  return melden(
    new ApiFehler(
      artAusStatus(antwort.status),
      pfad,
      antwort.status,
      detail,
      sekundenAus(antwort),
      felder,
      inhalt,
      codeAus(inhalt),
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

/** Fehlerart zu einem HTTP-Status. */
export function artAusStatus(status: number): ApiFehlerArt {
  if (status === 401) return "nicht_angemeldet";
  if (status === 403) return "verboten";
  if (status === 404) return "nicht_gefunden";
  if (status === 409) return "konflikt";
  if (status === 429) return "gesperrt";
  if (status === 502 || status === 503 || status === 504) return "netzwerk";
  if (status >= 500) return "server";
  return "anfrage";
}

/** Pfad aus FastAPI-`loc` ohne das führende `body`. */
function pfadAusLoc(loc: unknown): string {
  if (!Array.isArray(loc)) return "";
  const teile = loc.map(String);
  if (teile[0] === "body") teile.shift();
  return teile.join(".");
}

/**
 * Feldfehler aus einer Fehlerantwort: bevorzugt `errors: [{field, message}]` (deutsch, siehe
 * `backend/app/core/errors.py`), sonst die Standardliste von FastAPI in `detail` (`loc`, `msg`).
 * Gilt für jeden Status: 422 (Prüffehler) ebenso wie 409 mit Feldbezug, z. B.
 * `{detail: "Bahn 2 ist schon belegt.", errors: [{field: "lane", message: …}]}`.
 * `field` wie `abschnitte[0].serien` wird zu `abschnitte.0.serien`.
 */
export function feldFehlerAus(inhalt: unknown): FeldFehler[] {
  if (!inhalt || typeof inhalt !== "object") return [];
  const { detail, errors } = inhalt as { detail?: unknown; errors?: unknown };
  const felder: FeldFehler[] = [];
  if (Array.isArray(errors)) {
    for (const eintrag of errors) {
      if (!eintrag || typeof eintrag !== "object") continue;
      const { field, message } = eintrag as { field?: unknown; message?: unknown };
      if (typeof message !== "string") continue;
      felder.push({
        feld: typeof field === "string" ? field.replace(/\[(\d+)\]/g, ".$1") : "",
        meldung: message,
      });
    }
  } else if (Array.isArray(detail)) {
    for (const eintrag of detail) {
      if (!eintrag || typeof eintrag !== "object") continue;
      const { loc, msg } = eintrag as { loc?: unknown; msg?: unknown };
      if (typeof msg !== "string") continue;
      felder.push({ feld: pfadAusLoc(loc), meldung: msg });
    }
  }
  return felder;
}

async function inhaltAus(
  antwort: Response,
): Promise<{ detail: string | undefined; felder: FeldFehler[]; inhalt: unknown }> {
  try {
    const inhalt: unknown = await antwort.json();
    let detail: string | undefined;
    if (inhalt && typeof inhalt === "object" && "detail" in inhalt) {
      const wert = (inhalt as { detail: unknown }).detail;
      detail = typeof wert === "string" ? wert : JSON.stringify(wert);
    }
    return { detail, felder: feldFehlerAus(inhalt), inhalt };
  } catch {
    // Antwort ohne JSON-Inhalt: kein Detail
    return { detail: undefined, felder: [], inhalt: undefined };
  }
}

async function abrufen(pfad: string, optionen: AnfrageOptionen): Promise<Response> {
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
  return antwort;
}

async function jsonAus<T>(antwort: Response, pfad: string): Promise<T> {
  try {
    return (await antwort.json()) as T;
  } catch {
    throw new ApiFehler("format", pfad, antwort.status);
  }
}

export async function apiGet<T>(pfad: string, optionen: AnfrageOptionen = {}): Promise<T> {
  const antwort = await abrufen(pfad, optionen);
  return jsonAus<T>(antwort, pfad);
}

export interface AntwortMitKopf<T> {
  daten: T;
  /** Kopfzeilen der Antwort, z. B. `X-Total-Count` */
  kopf: Headers;
}

/** Wie `apiGet`, liefert zusätzlich die Kopfzeilen der Antwort (z. B. `X-Total-Count`). */
export async function apiGetMitKopf<T>(
  pfad: string,
  optionen: AnfrageOptionen = {},
): Promise<AntwortMitKopf<T>> {
  const antwort = await abrufen(pfad, optionen);
  return { daten: await jsonAus<T>(antwort, pfad), kopf: antwort.headers };
}

/** Ganze Zahl aus einer Kopfzeile wie `X-Total-Count`; fehlt sie oder ist sie unlesbar: `undefined`. */
export function zahlAusKopf(kopf: Headers, name: string): number | undefined {
  const wert = kopf.get(name);
  return wert !== null && /^\d+$/.test(wert) ? Number(wert) : undefined;
}

export type Schreibmethode = "POST" | "PUT" | "PATCH" | "DELETE";

export interface SendeOptionen extends AnfrageOptionen {
  /** Inhalt ohne JSON-Umwandlung senden, z. B. CSV. */
  roh?: { inhalt: BodyInit; typ: string };
  /**
   * Zusätzliche Kopfzeilen, z. B. `Idempotency-Key`. `X-Schiesshub-Request` und `Content-Type`
   * setzt die Funktion selbst; gleichnamige Einträge hier werden nicht übernommen.
   */
  kopf?: Record<string, string>;
}

/** Kopfzeilen, die `apiSenden` selbst setzt (Vergleich ohne Groß-/Kleinschreibung). */
const GESCHUETZTE_KOPFZEILEN = new Set(["x-schiesshub-request", "content-type"]);

/**
 * Schreibende Anfrage. Sendet den Inhalt als JSON und den Header `X-Schiesshub-Request`,
 * den das Backend für alle schreibenden Methoden verlangt (Schutz vor fremden Seiten).
 * Antworten ohne Inhalt (204) ergeben `undefined`. Eigene Kopfzeilen über `optionen.kopf`.
 */
export async function apiSenden<T = void>(
  methode: Schreibmethode,
  pfad: string,
  inhalt?: unknown,
  optionen: SendeOptionen = {},
): Promise<T> {
  const kopf: Record<string, string> = { Accept: "application/json" };
  for (const [name, wert] of Object.entries(optionen.kopf ?? {})) {
    if (!GESCHUETZTE_KOPFZEILEN.has(name.toLowerCase())) kopf[name] = wert;
  }
  kopf["X-Schiesshub-Request"] = "1";
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
