import { ApiFehler } from "../../api/client";
import { vergleichsform } from "./anzeigename";

interface VereinLike {
  id: string;
  name: string;
  short?: string | null;
}

/** Wörter dieser Länge zählen für „ähnlich“; kürzere („SV“, „e.V.“) passen zu fast jedem Verein. */
const MIN_WORTLAENGE = 4;
/** Höchstens so viele ähnliche Vereine anbieten. */
const MAX_AEHNLICH = 5;

export interface VereinTreffer<V extends VereinLike> {
  /** Name oder Kürzel enthält den Suchtext; wer damit beginnt, steht vorn (wie `GET /clubs?q=`) */
  treffer: V[];
  /** Kein direkter Treffer, aber ein Wort des Suchtexts kommt im Namen vor (z. B. „Hubertus“) */
  aehnlich: V[];
  /** Name oder Kürzel stimmt genau mit dem Suchtext überein: dann nicht „neu anlegen“ anbieten */
  exakt: boolean;
}

/**
 * Sucht Vereine zum getippten Text: direkte Treffer, ähnliche (wortweise) und ob es ihn genau so
 * schon gibt. Direkte Treffer vergleicht und ordnet sie wie der Server bei `GET /clubs?q=`
 * (Vergleichsform, Treffer am Anfang von Name oder Kürzel zuerst); die Liste ist ohnehin geladen,
 * weil das Feld den gewählten Verein und die genaue Übereinstimmung kennen muss.
 */
export function vereinTreffer<V extends VereinLike>(alle: V[], suche: string): VereinTreffer<V> {
  const filter = vergleichsform(suche);
  if (!filter) return { treffer: alle, aehnlich: [], exakt: false };

  const amAnfang: V[] = [];
  const mittendrin: V[] = [];
  const rest: V[] = [];
  let exakt = false;
  for (const verein of alle) {
    const name = vergleichsform(verein.name);
    const kurz = verein.short ? vergleichsform(verein.short) : "";
    if (name === filter || (kurz !== "" && kurz === filter)) exakt = true;
    if (name.startsWith(filter) || (kurz !== "" && kurz.startsWith(filter))) amAnfang.push(verein);
    else if (name.includes(filter) || (kurz !== "" && kurz.includes(filter)))
      mittendrin.push(verein);
    else rest.push(verein);
  }
  const treffer = [...amAnfang, ...mittendrin];

  const woerter = filter.split(" ").filter((wort) => wort.length >= MIN_WORTLAENGE);
  const aehnlich =
    woerter.length === 0
      ? []
      : rest
          .filter((verein) => {
            const name = vergleichsform(verein.name);
            return woerter.some((wort) => name.includes(wort));
          })
          .slice(0, MAX_AEHNLICH);

  return { treffer, aehnlich, exakt };
}

interface VereinSichernOptionen<V extends VereinLike> {
  /** Die schon geladenen Vereine */
  vorhandene: readonly V[];
  /** Legt den Verein am Server an (`POST /clubs`) */
  anlegen: (name: string) => Promise<V>;
  /** Lädt die Vereinsliste frisch vom Server */
  neuLaden: () => Promise<readonly V[]>;
}

/**
 * Liefert den Verein zum vorgemerkten Namen und legt ihn nur an, wenn es ihn noch nicht gibt.
 * Meldet der Server, dass es den Namen schon gibt (anderes Gerät oder ein früherer Versuch, dessen
 * Antwort verloren ging), wird der vorhandene Verein genommen statt eines zweiten.
 */
export async function vereinSichern<V extends VereinLike>(
  name: string,
  { vorhandene, anlegen, neuLaden }: VereinSichernOptionen<V>,
): Promise<V> {
  const gesucht = vergleichsform(name);
  const gleich = (liste: readonly V[]) =>
    liste.find((verein) => vergleichsform(verein.name) === gesucht);
  const schon = gleich(vorhandene);
  if (schon) return schon;
  try {
    return await anlegen(name);
  } catch (fehler) {
    if (!(fehler instanceof ApiFehler && fehler.art === "konflikt")) throw fehler;
    const nachher = gleich(await neuLaden());
    if (nachher) return nachher;
    throw fehler;
  }
}
