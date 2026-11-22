/**
 * Server-Ereignisse für den Bildschirm. Der Feed nennt in `reload_on`, wann er neu geladen werden
 * soll; Einträge mit `*` am Ende stehen für alle Ereignisse mit diesem Anfang.
 *
 * Server-Sent Events kommen als benannte Ereignisse (`event: start.booked`). Ein Browser kann nur
 * auf einzelne Namen hören, nicht auf Muster. Deshalb steht hier die Liste der Ereignisse, die das
 * Backend sendet (Stand: Module turnier, starts, ergebnisse, teilnehmer, anzeige, backup).
 * Ein Name ohne `*` aus `reload_on` gilt immer, auch wenn er hier fehlt.
 */
export const BEKANNTE_EREIGNISSE: readonly string[] = [
  "display.changed",
  "tournament.created",
  "tournament.updated",
  "tournament.status_changed",
  "tournament.deleted",
  "tournament.announcement_changed",
  "competition.created",
  "competition.updated",
  "competition.deleted",
  "competition.reordered",
  "competition.definition_changed",
  "range.created",
  "range.updated",
  "range.deleted",
  "range.reordered",
  "class.created",
  "class.updated",
  "class.deleted",
  "class.reordered",
  "class.imported",
  "entry.created",
  "entry.updated",
  "entry.deleted",
  "start.booked",
  "start.cancelled",
  "start.moved",
  "start.scheduled",
  "start.status_changed",
  "start.aborted",
  "start.reopened",
  "heat.created",
  "heat.updated",
  "heat.deleted",
  "result.raw_set",
  "result.finalized",
  "result.corrected",
  "result.reopened",
  "result.aborted",
  "result.recomputed",
  "person.created",
  "person.updated",
  "person.deleted",
  "person.imported",
  "club.created",
  "club.updated",
  "club.deleted",
  "club.merged",
  "backup.status",
  "backup.completed",
  "backup.failed",
  "device.updated",
  "device.deleted",
];

/** Passt ein Ereignisname auf einen Eintrag aus `reload_on` (`start.*` passt auf `start.booked`)? */
export function passtEreignis(muster: string, name: string): boolean {
  if (muster === "*") return true;
  if (muster.endsWith("*")) return name.startsWith(muster.slice(0, -1));
  return muster === name;
}

/** Alle Ereignisnamen, auf die der Bildschirm hören muss, ohne Doppelte, sortiert. */
export function ereignisseZumNachladen(
  reloadOn: readonly string[],
  bekannte: readonly string[] = BEKANNTE_EREIGNISSE,
): string[] {
  const namen = new Set<string>();
  for (const muster of reloadOn) {
    if (!muster.includes("*")) {
      namen.add(muster);
      continue;
    }
    for (const name of bekannte) if (passtEreignis(muster, name)) namen.add(name);
  }
  return [...namen].sort();
}
