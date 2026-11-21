/**
 * Kleine Prüfungen und Formate für Einrichtung, Kopplung und Anmeldung.
 * Die endgültige Prüfung macht der Server; hier geht es um schnelle, klare Rückmeldung.
 */

/**
 * Mindestlänge der PIN. Der Server erlaubt sie einzustellen (AUTH_PIN_MIN_LENGTH, Standard 4),
 * liefert sie aber nicht aus; ist sie höher eingestellt, meldet der Server das beim Absenden.
 */
export const PIN_MIN_LAENGE = 4;
export const PIN_MAX_LAENGE = 12;

export function pinGueltig(pin: string, minLaenge = PIN_MIN_LAENGE): boolean {
  return /^\d+$/.test(pin) && pin.length >= minLaenge;
}

/** Kopplungscode wie der Server ihn vergleicht: ohne Leerzeichen und Striche, groß geschrieben. */
export function codeNormalisieren(code: string): string {
  return code.trim().toUpperCase().replace(/[\s-]/g, "");
}

/** Code in Fünfergruppen zum Ablesen: `ABCDEFGHJK` → `ABCDE-FGHJK`. */
export function codeGruppiert(code: string): string {
  const rein = codeNormalisieren(code);
  return rein.match(/.{1,5}/g)?.join("-") ?? "";
}

/** Restzeit einer Sperre als `m:ss`, z. B. `272` → `4:32`. */
export function formatRestzeit(sekunden: number): string {
  const ganz = Math.max(0, Math.ceil(sekunden));
  const minuten = Math.floor(ganz / 60);
  const rest = ganz % 60;
  return `${minuten}:${String(rest).padStart(2, "0")}`;
}

/** Anfangsbuchstaben für die Personen-Kachel: „Maria Brandt“ → „MB“, „M. Brandt“ → „MB“. */
export function initialen(name: string): string {
  const teile = name
    .split(/[\s.-]+/)
    .map((teil) => teil.trim())
    .filter(Boolean);
  const erste = teile[0]?.[0] ?? "";
  const letzte = teile.length > 1 ? (teile[teile.length - 1]?.[0] ?? "") : "";
  return (erste + letzte).toUpperCase();
}
