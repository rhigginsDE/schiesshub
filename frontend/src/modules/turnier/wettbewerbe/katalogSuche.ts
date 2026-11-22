import type { Disziplin, Gruppe } from "../../../api/typen";

/**
 * Suche im Disziplin-Katalog, im Browser über die vollständige Liste eines Verbands (rund 200
 * Einträge). Durchsucht werden Kennziffer, Name, Gruppe, Waffe, Waffenart, Art und Distanz. Groß-
 * und Kleinschreibung sowie Umlaute spielen keine Rolle („prazision“, „präzision“ und
 * „praezision“ finden dasselbe); bei mehreren Wörtern muss jedes vorkommen.
 */

/** Kleinschreibung, Umlaute als ae/oe/ue, ß als ss, übrige Akzente ohne Zeichen. */
export function normalisiere(text: string): string {
  return text
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

/** Wörter der Eingabe; „15 m“ und „15m“ gelten gleich, Satzzeichen trennen. */
export function suchWoerter(eingabe: string): string[] {
  return normalisiere(eingabe)
    .split(/[\s,;/]+/)
    .map((wort) => wort.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}.]+$/gu, ""))
    .filter(Boolean);
}

/**
 * Suchtext einer Disziplin: alle Felder, zusätzlich ohne Leerzeichen („15m“) und mit Umlauten als
 * einfache Vokale („prazision“).
 */
export function suchText(disziplin: Disziplin, gruppe?: Gruppe): string {
  const teile = [
    disziplin.kennziffer,
    disziplin.name,
    disziplin.gruppe_name,
    disziplin.waffe,
    disziplin.anschlag,
    disziplin.visierung,
    gruppe?.waffenart,
    gruppe?.art.replace(/-/g, " "),
    typeof gruppe?.distanz_m === "number" ? `${gruppe.distanz_m} m` : undefined,
  ].filter((teil): teil is string => typeof teil === "string" && teil.length > 0);
  const text = normalisiere(teile.join(" "));
  const ohneUmlautE = text.replace(/ae/g, "a").replace(/oe/g, "o").replace(/ue/g, "u");
  return `${text} ${text.replace(/\s+/g, "")} ${ohneUmlautE}`;
}

/** Passt die Disziplin zu allen Wörtern? Ohne Wörter passt alles. */
export function passt(text: string, woerter: readonly string[]): boolean {
  return woerter.every((wort) => text.includes(wort));
}

/**
 * Filtert den Katalog. Kennziffern, die mit der Eingabe beginnen, stehen vorn; sonst bleibt die
 * Reihenfolge des Katalogs.
 */
export function sucheImKatalog(
  disziplinen: readonly Disziplin[],
  gruppen: readonly Gruppe[],
  eingabe: string,
): Disziplin[] {
  const woerter = suchWoerter(eingabe);
  if (woerter.length === 0) return [...disziplinen];
  const gruppeNachId = new Map(gruppen.map((gruppe) => [gruppe.id, gruppe]));
  const treffer = disziplinen.filter((disziplin) =>
    passt(suchText(disziplin, gruppeNachId.get(disziplin.gruppe_id)), woerter),
  );
  const erstes = woerter[0] ?? "";
  const vorn = (disziplin: Disziplin) =>
    woerter.length === 1 && disziplin.kennziffer.startsWith(erstes) ? 0 : 1;
  return treffer
    .map((disziplin, index) => ({ disziplin, index }))
    .sort((a, b) => vorn(a.disziplin) - vorn(b.disziplin) || a.index - b.index)
    .map(({ disziplin }) => disziplin);
}

/** Gruppen nach Waffenart in Katalogreihenfolge, für die Übersicht ohne Suche. */
export function gruppenNachWaffenart(gruppen: readonly Gruppe[]): [string, Gruppe[]][] {
  const ergebnis = new Map<string, Gruppe[]>();
  for (const gruppe of gruppen) {
    const art = gruppe.waffenart;
    ergebnis.set(art, [...(ergebnis.get(art) ?? []), gruppe]);
  }
  return [...ergebnis.entries()];
}
