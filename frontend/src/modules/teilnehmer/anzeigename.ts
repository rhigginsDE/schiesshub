/**
 * Anzeigename und Vergleichsform wie im Backend (`backend/app/modules/teilnehmer/names.py`).
 * Dient der Live-Vorschau im Formular und der Vereinsfilterung; maßgeblich bleibt, was der Server
 * als `display_name` liefert.
 */

export type Anzeigeart = "full" | "short" | "hidden";

/** Namenszusätze, die zum Nachnamen gehören („Anna von der Leyen“ → „A. von der Leyen“). */
const ZUSAETZE = new Set([
  "von",
  "vom",
  "zu",
  "zum",
  "zur",
  "van",
  "der",
  "den",
  "de",
  "del",
  "della",
  "di",
  "da",
  "du",
  "la",
  "le",
  "ten",
  "ter",
  "op",
]);

/** Unicode normalisieren, Leerraum am Rand entfernen und innen zusammenfassen. */
export function bereinigen(text: string): string {
  return text.normalize("NFC").split(/\s+/u).filter(Boolean).join(" ");
}

/** Vergleichsform: ohne Groß-/Kleinschreibung, Akzente und Umlaut-Schreibweise. */
export function vergleichsform(text: string): string {
  const ohneZeichen = text.normalize("NFKD").replace(/\p{M}/gu, "");
  return bereinigen(
    ohneZeichen
      .toLowerCase()
      .replace(/ß/g, "ss")
      .replace(/ae/g, "a")
      .replace(/oe/g, "o")
      .replace(/ue/g, "u"),
  );
}

/** „Hans-Peter“ → „H.-P.“ */
function initiale(vorname: string): string {
  return vorname
    .split("-")
    .map((teil) => teil.replace(/\.+$/u, ""))
    .filter(Boolean)
    .map((teil) => `${Array.from(teil)[0]}.`)
    .join("-");
}

/** Vornamen als Initialen, Nachname vollständig: „Markus Brandt“ → „M. Brandt“. */
export function abkuerzen(name: string): string {
  const woerter = bereinigen(name).split(" ");
  if (woerter.length < 2) return woerter.join(" ");
  let nachname = woerter.length - 1;
  while (nachname > 0 && ZUSAETZE.has((woerter[nachname - 1] ?? "").toLowerCase())) {
    nachname -= 1;
  }
  const initialen = woerter.slice(0, nachname).map(initiale).filter(Boolean);
  if (initialen.length === 0) return woerter.join(" ");
  return [...initialen, ...woerter.slice(nachname)].join(" ");
}

/** Name, wie er auf Anzeige und Listen erscheint; `null` = nicht anzeigen. */
export function anzeigename(name: string, art: Anzeigeart): string | null {
  if (art === "full") return bereinigen(name);
  if (art === "short") return abkuerzen(name);
  return null;
}
