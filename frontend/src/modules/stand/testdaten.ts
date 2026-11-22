import type { StationStart } from "../anmeldung/api";

/** Ein Start, wie ihn Startliste und Reihenfolge liefern; nur für Tests. */
export function stationStart(teil: Partial<StationStart> & { start_id: string }): StationStart {
  return {
    entry_id: `e-${teil.start_id}`,
    called_at: null,
    start_number: 1,
    display_name: "Markus Brandt",
    club: null,
    class_id: "k",
    class_short: "S",
    competition_id: "w",
    competition_name: "Pistole",
    range_id: "r",
    attempt: 1,
    status: "registered",
    abort_reason: null,
    queue_position: null,
    lane: null,
    heat_id: null,
    heat_number: null,
    heat_starts_at: null,
    ...teil,
  };
}
