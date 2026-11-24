import {
  ApiFehler,
  type ApiFehlerArt,
  apiSenden,
  type FeldFehler,
  feldFehlerAus,
  type Schreibmethode,
} from "../../api/client";

export type { FeldFehler };

/**
 * Fehler einer schreibenden Anfrage des Turnier-Moduls. Die Feldfehler trägt inzwischen jeder
 * `ApiFehler` (`felder`); die Klasse bleibt, damit vorhandene Aufrufer und Tests unverändert gehen.
 */
export class EingabeFehler extends ApiFehler {
  declare readonly felder: FeldFehler[];

  constructor(
    art: ApiFehlerArt,
    pfad: string,
    status: number,
    detail: string | undefined,
    felder: FeldFehler[],
    inhalt?: unknown,
    code?: string,
  ) {
    super(art, pfad, status, detail, undefined, felder, inhalt, code);
    this.name = "EingabeFehler";
  }
}

/**
 * Liest Feldfehler und Meldung aus einer Fehlerantwort. Bevorzugt `errors` (deutsch, vom
 * Turnier-Modul); sonst die Standardliste von FastAPI in `detail`.
 */
export function leseFehlerInhalt(inhalt: unknown): { detail?: string; felder: FeldFehler[] } {
  const felder = feldFehlerAus(inhalt);
  if (!inhalt || typeof inhalt !== "object") return { felder };
  const { detail } = inhalt as { detail?: unknown };
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

/** Wie `leseFehlerInhalt`, aber aus einem fertigen `ApiFehler` von `apiSenden`. */
function zusammenfassung(fehler: ApiFehler): string | undefined {
  const { detail, felder } = fehler;
  const keinSatz = detail === undefined || /^[[{]/.test(detail.trim());
  return felder.length > 0 && keinSatz ? felder.map((f) => f.meldung).join(" ") : detail;
}

/**
 * Schreibende Anfrage wie `apiSenden`, aber mit Feldfehlern im Fehlerfall (`EingabeFehler`).
 * 401/403 meldet sie nicht an die App-Shell (wie bisher); das Formular zeigt den Fehler selbst.
 */
export async function turnierSenden<T = void>(
  methode: Schreibmethode,
  pfad: string,
  inhalt?: unknown,
): Promise<T> {
  try {
    return await apiSenden<T>(methode, pfad, inhalt, { still: true });
  } catch (fehler) {
    if (!(fehler instanceof ApiFehler) || fehler.status === undefined) throw fehler;
    if (fehler.art === "format") throw fehler;
    throw new EingabeFehler(
      fehler.art,
      pfad,
      fehler.status,
      zusammenfassung(fehler),
      [...fehler.felder],
      fehler.inhalt,
      fehler.code,
    );
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
  const felder = fehler.felder;
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

/** Eine Lücke im Katalog, wegen der eine Vorlage gerade nicht geht (`TemplateGapOut`). */
export interface VorlagenLuecke {
  kind: "competition" | "classes";
  federation: string;
  code?: string | null;
  variant_id?: string | null;
  /** Fertiger Text des Servers, z. B. „Kennziffer 4403 (BDS)“ */
  message_de: string;
}

/**
 * 409 `template_unavailable` (Vorlage oder Übungsturnier): was im Katalog fehlt. `null` bei jedem
 * anderen Fehler.
 */
export function vorlagenLuecken(fehler: unknown): VorlagenLuecke[] | null {
  if (!(fehler instanceof ApiFehler) || fehler.status !== 409) return null;
  const inhalt = fehler.inhalt as { code?: unknown; missing?: unknown } | undefined;
  if ((fehler.code ?? inhalt?.code) !== "template_unavailable") return null;
  const liste = Array.isArray(inhalt?.missing) ? (inhalt.missing as unknown[]) : [];
  return liste.flatMap((eintrag) => {
    if (!eintrag || typeof eintrag !== "object") return [];
    const { kind, federation, code, variant_id, message_de } = eintrag as Record<string, unknown>;
    if (typeof message_de !== "string" || !message_de.trim()) return [];
    return [
      {
        kind: kind === "classes" ? "classes" : "competition",
        federation: typeof federation === "string" ? federation : "",
        code: typeof code === "string" ? code : null,
        variant_id: typeof variant_id === "string" ? variant_id : null,
        message_de: message_de.trim(),
      },
    ];
  });
}
