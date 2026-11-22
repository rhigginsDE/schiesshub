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
  /** Name oder Kürzel enthält den Suchtext */
  treffer: V[];
  /** Kein direkter Treffer, aber ein Wort des Suchtexts kommt im Namen vor (z. B. „Hubertus“) */
  aehnlich: V[];
  /** Name oder Kürzel stimmt genau mit dem Suchtext überein: dann nicht „neu anlegen“ anbieten */
  exakt: boolean;
}

/** Sucht Vereine zum getippten Text: direkte Treffer, ähnliche (wortweise) und ob es ihn genau so schon gibt. */
export function vereinTreffer<V extends VereinLike>(alle: V[], suche: string): VereinTreffer<V> {
  const filter = vergleichsform(suche);
  if (!filter) return { treffer: alle, aehnlich: [], exakt: false };

  const treffer: V[] = [];
  const rest: V[] = [];
  let exakt = false;
  for (const verein of alle) {
    const name = vergleichsform(verein.name);
    const kurz = verein.short ? vergleichsform(verein.short) : "";
    if (name === filter || (kurz !== "" && kurz === filter)) exakt = true;
    if (name.includes(filter) || (kurz !== "" && kurz.includes(filter))) treffer.push(verein);
    else rest.push(verein);
  }

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
