/**
 * Server-Ereignisse für den Bildschirm. Der Feed nennt in `reload_on` die genauen Ereignisnamen,
 * bei denen er neu geladen werden soll; sie gehen direkt an `EventSource.addEventListener`.
 *
 * Rückfall für ältere Server: Fehlt `reload_on`, gilt die Liste unten. Stehen darin noch Muster
 * (`start.*` für alle Ereignisse mit diesem Anfang), werden sie gegen diese Liste aufgelöst, denn
 * ein Browser kann nur auf einzelne Namen hören (Stand: Module turnier, starts, ergebnisse,
 * teilnehmer, anzeige, backup).
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

/**
 * Alle Ereignisnamen, auf die der Bildschirm hören muss, ohne Doppelte, sortiert: die Namen aus
 * `reload_on`; ohne das Feld die bekannte Liste.
 */
export function ereignisseZumNachladen(
  reloadOn: readonly string[] | null | undefined,
  bekannte: readonly string[] = BEKANNTE_EREIGNISSE,
): string[] {
  if (!Array.isArray(reloadOn)) return [...new Set(bekannte)].sort();
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
