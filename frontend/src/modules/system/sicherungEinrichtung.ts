import type {
  SicherungsEinstellungen,
  SicherungsLauf,
  SicherungsStatus,
} from "../../api/typenSystem";

/**
 * Ersteinrichtung der Sicherung als kurze Aufgabenliste: Stick, Passwort, erste Sicherung.
 * Daraus folgt auch die eine Hauptaktion der Ansicht.
 */

export type AufgabeId = "stick" | "passwort" | "erste";

export interface Aufgabe {
  id: AufgabeId;
  erledigt: boolean;
}

export type Hauptaktion = "stick_einrichten" | "stick_pruefen" | "passwort" | "sichern";

/** Liegt schon einmal eine Sicherung auf dem Stick? */
export function ersteSicherungAufStick(
  status: SicherungsStatus,
  laeufe: readonly SicherungsLauf[] | undefined,
): boolean {
  if (status.last_usb_copy?.ok) return true;
  return (laeufe ?? []).some(
    (lauf) => lauf.kind === "snapshot" && lauf.target === "usb" && lauf.ok,
  );
}

/**
 * Die Aufgaben der Ersteinrichtung, oder `null`, wenn keine Liste nötig ist: Kopie auf den Stick
 * ist ausgeschaltet, die Einstellungen fehlen noch, oder es lag schon einmal eine Sicherung auf
 * dem Stick (dann ist die Einrichtung abgeschlossen; spätere Störungen meldet die Warnung).
 */
export function einrichtungsAufgaben(
  status: SicherungsStatus,
  einstellungen: SicherungsEinstellungen | undefined,
  laeufe: readonly SicherungsLauf[] | undefined,
): Aufgabe[] | null {
  if (!einstellungen?.enabled || !einstellungen.usb_enabled) return null;
  const erste = ersteSicherungAufStick(status, laeufe);
  if (erste) return null;
  const aufgaben: Aufgabe[] = [
    { id: "stick", erledigt: status.usb.present && status.usb.writable },
  ];
  if (einstellungen.encrypt) aufgaben.push({ id: "passwort", erledigt: status.passphrase_set });
  aufgaben.push({ id: "erste", erledigt: false });
  return aufgaben;
}

export function naechsteAufgabe(aufgaben: readonly Aufgabe[] | null): AufgabeId | null {
  return aufgaben?.find((aufgabe) => !aufgabe.erledigt)?.id ?? null;
}

/** Ein Stick, der noch nie erkannt wurde, wird eingerichtet; ein bekannter nur neu gesucht. */
function stickAktion(status: SicherungsStatus): Hauptaktion {
  return status.usb.last_seen_at ? "stick_pruefen" : "stick_einrichten";
}

/** Die eine grüne Aktion: der nächste fehlende Schritt, sonst „Jetzt sichern“. */
export function hauptaktion(
  status: SicherungsStatus,
  einstellungen: SicherungsEinstellungen | undefined,
  aufgaben: readonly Aufgabe[] | null,
): Hauptaktion {
  const naechste = naechsteAufgabe(aufgaben);
  if (naechste === "stick") return stickAktion(status);
  if (naechste === "passwort") return "passwort";
  if (naechste === "erste") return "sichern";
  if (einstellungen?.usb_enabled && !status.usb.present) return stickAktion(status);
  if (einstellungen?.encrypt && !status.passphrase_set) return "passwort";
  return "sichern";
}
