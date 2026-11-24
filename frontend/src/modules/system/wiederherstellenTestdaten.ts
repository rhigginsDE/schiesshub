import type { Quelle, Vorschau, WiederherstellungsStatus } from "./wiederherstellenAblauf";

/** Testdaten für die Wiederherstellung (Logik- und Seitentests). */

/** Dieselbe Sicherung auf Stick und Server: ein Eintrag, die Stick-Kopie vorn. */
export const QUELLE_STICK: Quelle = {
  id: "usb:snapshot-20261123T210253Z.shb",
  location: "usb",
  locations: ["usb", "local"],
  other_ids: ["local:snapshot-20261123T210253Z.dump"],
  file_name: "snapshot-20261123T210253Z.shb",
  created_at: "2026-11-23T21:02:53Z",
  size_bytes: 297089,
  checksum_present: true,
  encrypted: true,
  needs_passphrase: true,
  contains_keys: true,
  journal_available: true,
};

export const QUELLE_SERVER: Quelle = {
  ...QUELLE_STICK,
  id: "local:snapshot-20261123T210253Z.dump",
  location: "local",
  locations: ["local"],
  other_ids: [],
  file_name: "snapshot-20261123T210253Z.dump",
  encrypted: false,
  needs_passphrase: false,
  contains_keys: false,
  journal_available: false,
};

export function vorschau(teil: Partial<Vorschau> = {}): Vorschau {
  return {
    source: QUELLE_STICK,
    confirm: QUELLE_STICK.id,
    checksum_ok: true,
    created_at: "2026-11-23T21:02:53Z",
    app_version: "0.1.0",
    app_version_current: "0.1.0",
    schema_check: { backup: ["0018"], current: ["0018"], state: "same", message_de: "passt" },
    tournaments: [
      {
        id: "t1",
        name: "Vereinsmeisterschaft",
        status: "active",
        date_from: "2026-11-22",
        starts: 18,
        final_results: 11,
        result_events: 48,
      },
    ],
    persons: 54,
    comparison: {
      events_now: 330,
      events_in_backup: 321,
      events_since_backup: 9,
      events_from_journal: 7,
      events_lost: 2,
      lost_start_missing: 2,
      lost_not_in_journal: 0,
      lost_conflict: 0,
      events_only_in_backup: 0,
      journal_applicable: 7,
      starts_now: 89,
      starts_in_backup: 87,
      starts_since_backup: 2,
      journal_files: 1,
      journal_unreadable: [],
      summary_de: "Seit dieser Sicherung sind 9 Ergebnis-Ereignisse hinzugekommen.",
    },
    keys: { field_keys: "same", backup_key: "same", message_de: "Schlüssel gleich." },
    access: {
      enforced_now: true,
      enforced_after: true,
      account_in_backup: true,
      account_is_admin_in_backup: true,
      device_in_backup: true,
      session_in_backup: true,
      pin_changed: false,
      admins_in_backup: 1,
      lockout_risk: false,
      message_de: "Konto und Gerät sind in der Sicherung; du bleibst angemeldet.",
      reasons: [
        {
          code: "stays_signed_in",
          message_de: "Konto und Gerät sind in der Sicherung; du bleibst angemeldet.",
        },
      ],
    },
    restorable: true,
    problem_items: [],
    note_items: [],
    ...teil,
  };
}

/** Ältere Sicherung, die nur auf dem Server liegt. */
export const QUELLE_ALT: Quelle = {
  ...QUELLE_SERVER,
  id: "local:snapshot-20261123T180000Z.dump",
  file_name: "snapshot-20261123T180000Z.dump",
  created_at: "2026-11-23T18:00:00Z",
};

/** Zugang, wenn dein Konto und dieses Gerät in der Sicherung fehlen. */
export function ausgesperrt(): Vorschau["access"] {
  return {
    ...vorschau().access,
    account_in_backup: false,
    account_is_admin_in_backup: false,
    device_in_backup: false,
    session_in_backup: false,
    lockout_risk: true,
    message_de: "In der Sicherung fehlt dein Konto und dieses Gerät. …",
    reasons: [
      { code: "lockout", message_de: "In der Sicherung fehlt dein Konto und dieses Gerät. …" },
    ],
  };
}

export function lauf(teil: Partial<WiederherstellungsStatus> = {}): WiederherstellungsStatus {
  return {
    state: "running",
    step: "load",
    progress: 0.4,
    steps: [
      { key: "check", label_de: "Sicherung prüfen", state: "done" },
      { key: "maintenance", label_de: "Eingaben anhalten", state: "done" },
      { key: "pre_backup", label_de: "Jetzigen Stand sichern", state: "done" },
      { key: "load", label_de: "Einspielen", state: "running" },
      { key: "upgrade", label_de: "Aktualisieren", state: "pending" },
      { key: "journal", label_de: "Mitschrift nachtragen", state: "pending" },
      { key: "verify", label_de: "Prüfen", state: "pending" },
      { key: "swap", label_de: "Tauschen", state: "pending" },
      { key: "finish", label_de: "Abschließen", state: "pending" },
    ],
    source: QUELLE_STICK,
    started_at: "2026-11-23T21:10:00Z",
    finished_at: null,
    result: null,
    error_de: null,
    maintenance: true,
    ...teil,
  };
}
