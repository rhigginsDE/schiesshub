import { ApiFehler, type ApiFehlerArt, apiUrl, type Schreibmethode } from "../../api/client";

/** Fehler eines einzelnen Eingabefelds, wie ihn der Server meldet. */
export interface FeldFehler {
  /** Feldpfad mit Punkten, z. B. `settings.currency` oder `definition.variant.abschnitte.0.serien` */
  feld: string;
  meldung: string;
}

/**
 * Fehler einer schreibenden Anfrage mit den Feldfehlern des Servers. `client.ts` gibt nur `detail`
 * weiter; dieses Modul braucht zusätzlich `errors: [{field, message}]`, um Meldungen am Feld zu zeigen.
 */
export class EingabeFehler extends ApiFehler {
  readonly felder: FeldFehler[];

  constructor(
    art: ApiFehlerArt,
    pfad: string,
    status: number,
    detail: string | undefined,
    felder: FeldFehler[],
  ) {
    super(art, pfad, status, detail);
    this.name = "EingabeFehler";
    this.felder = felder;
  }
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

/** Pfad aus FastAPI-`loc` ohne das führende `body`. */
function pfadAusLoc(loc: unknown): string {
  if (!Array.isArray(loc)) return "";
  const teile = loc.map(String);
  if (teile[0] === "body") teile.shift();
  return teile.join(".");
}

/**
 * Liest Feldfehler und Meldung aus einer Fehlerantwort. Bevorzugt `errors` (deutsch, vom
 * Turnier-Modul); sonst die Standardliste von FastAPI in `detail`.
 */
export function leseFehlerInhalt(inhalt: unknown): { detail?: string; felder: FeldFehler[] } {
  if (!inhalt || typeof inhalt !== "object") return { felder: [] };
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

  const text =
    typeof detail === "string"
      ? detail
      : felder.length > 0
        ? felder.map((f) => f.meldung).join(" ")
        : detail !== undefined
          ? JSON.stringify(detail)
          : undefined;
  return { detail: text, felder };
}

/**
 * Schreibende Anfrage wie `apiSenden`, aber mit Feldfehlern im Fehlerfall (`EingabeFehler`).
 * Header `X-Schiesshub-Request` verlangt das Backend für alle schreibenden Methoden.
 */
export async function turnierSenden<T = void>(
  methode: Schreibmethode,
  pfad: string,
  inhalt?: unknown,
): Promise<T> {
  const kopf: Record<string, string> = {
    Accept: "application/json",
    "X-Schiesshub-Request": "1",
  };
  if (inhalt !== undefined) kopf["Content-Type"] = "application/json";

  let antwort: Response;
  try {
    antwort = await fetch(apiUrl(pfad), {
      method: methode,
      headers: kopf,
      body: inhalt === undefined ? undefined : JSON.stringify(inhalt),
    });
  } catch {
    throw new ApiFehler("netzwerk", pfad);
  }

  if (!antwort.ok) {
    let gelesen: { detail?: string; felder: FeldFehler[] } = { felder: [] };
    try {
      gelesen = leseFehlerInhalt(await antwort.json());
    } catch {
      // Antwort ohne JSON-Inhalt
    }
    throw new EingabeFehler(
      artAusStatus(antwort.status),
      pfad,
      antwort.status,
      gelesen.detail,
      gelesen.felder,
    );
  }
  if (antwort.status === 204) return undefined as T;
  try {
    return (await antwort.json()) as T;
  } catch {
    throw new ApiFehler("format", pfad, antwort.status);
  }
}

/**
 * Feldfehler für ein Formular: Schlüssel ist der Feldpfad ohne Präfix. Fehler, die zu keinem der
 * bekannten Felder passen, landen unter `""` (allgemeine Meldung).
 */
export function feldFehlerFuer(
  fehler: unknown,
  bekannteFelder: readonly string[],
  praefix = "",
): Record<string, string> {
  if (!(fehler instanceof ApiFehler)) return {};
  const ergebnis: Record<string, string> = {};
  const felder = fehler instanceof EingabeFehler ? fehler.felder : [];
  const rest: string[] = [];
  for (const { feld, meldung } of felder) {
    const ohne = praefix && feld.startsWith(`${praefix}.`) ? feld.slice(praefix.length + 1) : feld;
    // Längster bekannter Pfad, der passt: `settings.currency` vor `settings`.
    const treffer = [...bekannteFelder]
      .sort((a, b) => b.length - a.length)
      .find((bekannt) => ohne === bekannt || ohne.startsWith(`${bekannt}.`));
    if (treffer && !ergebnis[treffer]) ergebnis[treffer] = meldung;
    else if (!treffer) rest.push(meldung);
  }
  if (rest.length > 0 || felder.length === 0) {
    const allgemein = rest.length > 0 ? rest.join(" ") : fehler.detail;
    if (allgemein) ergebnis[""] = allgemein;
  }
  return ergebnis;
}
