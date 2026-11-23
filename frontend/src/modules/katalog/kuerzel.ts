/**
 * Fachkürzel, die in Stammdaten und Ablauftext des Katalogs vorkommen und eine Erklärung haben.
 * Die Erklärungen stehen in `katalog.json` unter `detail.kuerzel` und sind wörtlich aus dem Glossar
 * des Katalogs (`catalog/bds/katalog.yaml`, Abschnitt `glossar`) übernommen. Ohne Quelle dort kommt
 * kein Kürzel hierher (z. B. Verweise wie „K 4.06“ bleiben unerklärt). Die Erklärungen gelten nur
 * für den BDS; bei anderen Verbänden bedeuten dieselben Buchstaben etwas anderes oder nichts.
 */
const VERBAND = "bds";
const KUERZEL = {
  mi: /\bMI\b/,
  kw_patronen: /\bKW-Patronen\b/,
  z_scheibe: /\bZ\s?\d+\b/,
} as const;

export type Kuerzel = keyof typeof KUERZEL;

/** Kürzel, die im Text vorkommen, in fester Reihenfolge. */
export function verwendeteKuerzel(text: string, verband: string): Kuerzel[] {
  if (verband !== VERBAND) return [];
  return (Object.keys(KUERZEL) as Kuerzel[]).filter((kuerzel) => KUERZEL[kuerzel].test(text));
}
