/**
 * Hilfen für die drei Wege, ein Turnier zu beginnen (leer, wie ein früheres, aus einer Vorlage):
 * Datum und Name vorschlagen, doppelte Namen erkennen, geänderte Katalog-Wettbewerbe finden.
 */
import type { Turnier, Wettbewerb } from "./typen";

const zwei = (zahl: number) => String(zahl).padStart(2, "0");

/** Heutiges Datum als `JJJJ-MM-TT` (Ortszeit). */
export function heute(jetzt = new Date()): string {
  return `${jetzt.getFullYear()}-${zwei(jetzt.getMonth() + 1)}-${zwei(jetzt.getDate())}`;
}

/** Datum um ganze Jahre verschieben; der 29. Februar wird in Nicht-Schaltjahren der 28. */
function plusJahre(datum: string, jahre: number): string {
  const [j, m, t] = datum.split("-").map(Number) as [number, number, number];
  const ziel = j + jahre;
  const letzter = new Date(ziel, m, 0).getDate();
  return `${ziel}-${zwei(m)}-${zwei(Math.min(t, letzter))}`;
}

/**
 * Vorschlag für den Termin der Kopie: derselbe Tag ein Jahr später, und so lange ein weiteres
 * Jahr, bis der Tag nicht mehr in der Vergangenheit liegt („wie letztes Jahr“).
 */
export function naechsterTermin(quelle: string, heuteDatum = heute()): string {
  let jahre = 1;
  let vorschlag = plusJahre(quelle, jahre);
  while (vorschlag < heuteDatum && jahre < 50) {
    jahre += 1;
    vorschlag = plusJahre(quelle, jahre);
  }
  return vorschlag;
}

const JAHR = /\b(?:19|20)\d{2}\b/g;

/**
 * Name der Kopie: Steht im Namen eine Jahreszahl, wird die letzte durch das neue Jahr ersetzt
 * („Herbstpokal 2026“ → „Herbstpokal 2027“); sonst wird das Jahr angehängt.
 */
export function nameMitJahr(name: string, jahr: string): string {
  const basis = name.trim();
  const treffer = [...basis.matchAll(JAHR)];
  const letzter = treffer[treffer.length - 1];
  if (!letzter || letzter.index === undefined) return `${basis} ${jahr}`;
  return basis.slice(0, letzter.index) + jahr + basis.slice(letzter.index + letzter[0].length);
}

/** Name wie der Server vergleicht: ohne Leerzeichen am Rand, ohne Groß-/Kleinschreibung. */
function nameVergleich(name: string): string {
  return name.trim().toLocaleLowerCase("de");
}

/**
 * Gibt es schon ein Turnier mit diesem Namen am selben Anfangsdatum? Dieselbe Regel wie der Server
 * (409, Feldfehler `name`): Gleicher Name an einem anderen Tag ist erlaubt, das Übungsturnier zählt
 * nicht mit, und das Turnier selbst (`eigeneId`, beim Ändern) auch nicht.
 */
export function nameVergeben(
  name: string,
  datum: string,
  turniere: readonly Turnier[],
  eigeneId?: string,
): boolean {
  const gesucht = nameVergleich(name);
  if (!gesucht || !datum) return false;
  return turniere.some(
    (turnier) =>
      turnier.id !== eigeneId &&
      !turnier.is_practice &&
      turnier.date_from === datum &&
      nameVergleich(turnier.name) === gesucht,
  );
}

/** Anzahl der Turniertage (1 bei einem eintägigen Turnier). */
export function tage(turnier: Pick<Turnier, "date_from" | "date_to">): number {
  const tag = (datum: string) => {
    const [j, m, t] = datum.split("-").map(Number) as [number, number, number];
    return Date.UTC(j, m - 1, t);
  };
  return Math.round((tag(turnier.date_to) - tag(turnier.date_from)) / 86_400_000) + 1;
}

const TAG_MS = 86_400_000;

/**
 * Tag als fortlaufende Zahl; `null` bei leerem oder unvollständigem Datum. Auch Jahre unter 100
 * zählen richtig (beim Tippen meldet das Datumsfeld Zwischenstände wie „0002-12-05“).
 */
function tagNummer(datum: string): number | null {
  const teile = /^(\d{4,})-(\d{2})-(\d{2})$/.exec(datum);
  if (!teile) return null;
  const tag = new Date(0);
  tag.setUTCFullYear(Number(teile[1]), Number(teile[2]) - 1, Number(teile[3]));
  return Math.round(tag.getTime() / TAG_MS);
}

function ausTagNummer(nummer: number): string {
  const tag = new Date(nummer * TAG_MS);
  const jahr = String(tag.getUTCFullYear()).padStart(4, "0");
  return `${jahr}-${zwei(tag.getUTCMonth() + 1)}-${zwei(tag.getUTCDate())}`;
}

/**
 * „Datum bis“, nachdem sich „Datum von“ geändert hat: Es wandert mit und behält die Dauer
 * (eintägig: gleich „Datum von“), solange es in dieser Sitzung niemand selbst geändert hat
 * (`bisEigen`). Sonst, bei leerem „Datum bis“ („leer lassen bei einem Tag“) und bei
 * unvollständigem Datum bleibt es, wie es ist – dann greift die Prüfung „Enddatum vor Beginn“.
 */
export function bisNachVon(
  alt: { date_from: string; date_to: string },
  neuVon: string,
  bisEigen: boolean,
): string {
  if (bisEigen || !alt.date_to) return alt.date_to;
  const von = tagNummer(alt.date_from);
  const bis = tagNummer(alt.date_to);
  const neu = tagNummer(neuVon);
  if (von === null || bis === null || neu === null) return alt.date_to;
  return ausTagNummer(neu + Math.max(0, bis - von));
}

/** Turniere, die sich als Vorbild eignen: jüngstes zuerst, das Übungsturnier zuletzt. */
export function vorbilder(turniere: readonly Turnier[]): Turnier[] {
  return [...turniere].sort(
    (a, b) =>
      Number(a.is_practice) - Number(b.is_practice) ||
      b.date_from.localeCompare(a.date_from) ||
      a.name.localeCompare(b.name, "de"),
  );
}

// --- Hinweis „Katalog geändert“ ----------------------------------------------------------------

/**
 * Wettbewerbe, bei denen sich der Katalog seit der Übernahme geändert hat (`catalog_changed`, vom
 * Server je Abruf berechnet, gleich auf jedem Gerät).
 */
export function katalogGeaendert<W extends Pick<Wettbewerb, "catalog_changed">>(
  wettbewerbe: readonly W[],
): W[] {
  return wettbewerbe.filter((w) => w.catalog_changed);
}

/**
 * Kennung des Hinweises: welche Wettbewerbe mit welchem Katalogstand. Kommt eine neue Änderung
 * dazu, ändert sich die Kennung und ein ausgeblendeter Hinweis erscheint wieder.
 */
export function hinweisKennung(
  wettbewerbe: readonly Pick<Wettbewerb, "id" | "catalog_stand_now">[],
): string {
  return wettbewerbe
    .map((w) => `${w.id}@${w.catalog_stand_now ?? "-"}`)
    .sort()
    .join(",");
}

const AUSGEBLENDET = (turnierId: string) => `schiesshub.katalog-hinweis.${turnierId}`;

/**
 * „Ausblenden“ gilt nur auf diesem Gerät und nur für den Hinweis oben in der Einrichtung; das
 * Kennzeichen am Wettbewerb bleibt, bis der neue Stand übernommen ist.
 */
export function hinweisAusgeblendet(turnierId: string, kennung: string): boolean {
  try {
    return window.localStorage.getItem(AUSGEBLENDET(turnierId)) === kennung;
  } catch {
    return false;
  }
}

export function hinweisAusblenden(turnierId: string, kennung: string): void {
  try {
    window.localStorage.setItem(AUSGEBLENDET(turnierId), kennung);
  } catch {
    // Ohne Speicher (privates Fenster) bleibt der Hinweis eben stehen.
  }
}
