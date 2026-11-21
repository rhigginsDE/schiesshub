import type { ModulManifest } from "./modul";

/**
 * Platzhalter für die Rechteprüfung. Sobald das Backend-Modul `auth` Geräte und Rollen liefert,
 * entscheidet diese Funktion anhand der Berechtigungen der angemeldeten Person.
 * Bis dahin ist alles sichtbar.
 */
export function darf(_berechtigung: string | null): boolean {
  return true;
}

export function sichtbareModule(module: ModulManifest[]): ModulManifest[] {
  return module.filter((modul) => darf(modul.berechtigung));
}
