/**
 * Reine Logik des Bildschirms: Szenenwechsel, Zeitscheiben und Seiten. Ohne React und ohne DOM,
 * damit sie sich einzeln prüfen lässt.
 */

export interface SzenenKennung {
  scene_id: string;
  part: number;
}

/** Eine Seite einer Szene ist eindeutig durch Szenen-ID und Seite (`part`). */
export function szenenSchluessel(szene: SzenenKennung): string {
  return `${szene.scene_id}#${szene.part}`;
}

/**
 * Welche Szene nach einem neuen Feed gezeigt wird: dieselbe Seite, wenn es sie noch gibt (der
 * Bildschirm springt nicht zurück, nur weil ein Ergebnis dazukam); sonst dieselbe Stelle, solange
 * die Liste lang genug ist; sonst von vorn.
 */
export function indexNachWechsel(
  alte: readonly SzenenKennung[],
  neue: readonly SzenenKennung[],
  index: number,
): number {
  if (neue.length === 0) return 0;
  const bisher = alte[index];
  if (bisher) {
    const schluessel = szenenSchluessel(bisher);
    const gleich = neue.findIndex((szene) => szenenSchluessel(szene) === schluessel);
    if (gleich >= 0) return gleich;
  }
  return index >= 0 && index < neue.length ? index : 0;
}

/** Nächste Szene in der Runde; bei einer einzigen Szene bleibt sie stehen. */
export function naechsterIndex(index: number, anzahl: number): number {
  if (anzahl <= 1) return 0;
  return (index + 1) % anzahl;
}

/** Zeitscheibe, in der etwas gezeigt wird (Szene oder Teil einer Szene). */
export interface Takt {
  /** Beginn in Millisekunden (Geräteuhr, nur für Abstände) */
  start: number;
  dauer: number;
}

/**
 * Welche Seite gerade dran ist, wenn `seiten` Seiten gleichmäßig auf die Dauer verteilt werden.
 * Läuft die Zeit über die Dauer hinaus (eine einzelne Szene steht still), beginnt sie von vorn.
 */
export function seiteZurZeit(takt: Takt, jetzt: number, seiten: number): number {
  if (seiten <= 1 || takt.dauer <= 0) return 0;
  const vergangen = Math.max(0, jetzt - takt.start) % takt.dauer;
  return Math.min(seiten - 1, Math.floor(vergangen / (takt.dauer / seiten)));
}

/** Teil `index` von `anzahl` gleich langen Teilen einer Zeitscheibe. */
export function teilTakt(takt: Takt, index: number, anzahl: number): Takt {
  if (anzahl <= 1) return takt;
  const dauer = takt.dauer / anzahl;
  return { start: takt.start + index * dauer, dauer };
}

/**
 * Wie viele gleich hohe Zeilen in die verfügbare Höhe passen. `null`, solange nichts gemessen ist
 * (dann zeigt die Ansicht alles, z. B. in Tests ohne Layout). Mindestens eine Zeile.
 */
export function zeilenProSeite(verfuegbar: number, zeile: number, abstand = 0): number | null {
  if (!(verfuegbar > 0) || !(zeile > 0)) return null;
  return Math.max(1, Math.floor((verfuegbar + abstand) / (zeile + abstand)));
}

/** Teilt eine Liste in Seiten zu höchstens `proSeite` Einträgen; immer mindestens eine Seite. */
export function inSeiten<T>(liste: readonly T[], proSeite: number | null): T[][] {
  if (proSeite === null || proSeite <= 0 || liste.length <= proSeite) return [[...liste]];
  const seiten: T[][] = [];
  for (let i = 0; i < liste.length; i += proSeite) seiten.push(liste.slice(i, i + proSeite));
  return seiten;
}

/** Restsekunden bis zum Ende der Zeitscheibe, aufgerundet, nie negativ. */
export function restSekunden(takt: Takt, jetzt: number): number {
  return Math.max(0, Math.ceil((takt.start + takt.dauer - jetzt) / 1000));
}
