import { queryOptions } from "@tanstack/react-query";
import { schluessel } from "../../api/abfragen";
import { ApiFehler, apiGet, istWartungsFehler } from "../../api/client";
import type { components } from "../../api/schema.gen";

/**
 * Geführte Wiederherstellung einer Sicherung (`/backup/restore/*`): Typen, Abfragen und die
 * Entscheidungen des Ablaufs, getrennt von der Oberfläche, damit sie sich testen lassen.
 */

type Schemas = components["schemas"];
export type Quelle = Schemas["RestoreSourceOut"];
export type Quellen = Schemas["RestoreSourcesOut"];
export type Vorschau = Schemas["RestorePreviewOut"];
export type WiederherstellungsStatus = Schemas["RestoreStatusOut"];
export type WiederherstellungsSchritt = Schemas["RestoreStepOut"];
export type AusfuehrenAnfrage = Schemas["RestoreExecuteIn"];
export type SchrittId = WiederherstellungsSchritt["key"];
export type Ort = Quelle["location"];
/** Hinweis mit fester Kennung (`code`); `message_de` ist der Text des Servers. */
export type Meldung = Schemas["RestoreMessageOut"];
export type Zugang = Schemas["AccessCheckOut"];
export type UebersprungenerStart = Schemas["app__modules__backup__schemas__SkippedStartOut"];

/** Unter `sicherung.alle`: Ereignisse der Sicherung laden das mit neu. */
export const WIEDERHERSTELLEN_SCHLUESSEL = {
  quellen: [...schluessel.sicherung.alle, "wiederherstellen", "quellen"] as const,
  status: [...schluessel.sicherung.alle, "wiederherstellen", "status"] as const,
};

/** So oft fragt die Seite während der Wiederherstellung nach dem Fortschritt. */
export const ABFRAGE_MS = 1500;

export const quellenAbfrage = () =>
  queryOptions({
    queryKey: WIEDERHERSTELLEN_SCHLUESSEL.quellen,
    queryFn: ({ signal }) => apiGet<Quellen>("/backup/restore/sources", { signal }),
    staleTime: 0,
  });

/**
 * Fortschritt. Still, weil sich der Zugang mit dem Tausch der Datenbank ändern kann: Dann zeigt
 * die Seite selbst, was zu tun ist, statt zur Anmeldung zu springen.
 */
export const statusAbfrage = (beobachten: boolean) =>
  queryOptions({
    queryKey: WIEDERHERSTELLEN_SCHLUESSEL.status,
    queryFn: ({ signal }) =>
      apiGet<WiederherstellungsStatus>("/backup/restore/status", { signal, still: true }),
    refetchInterval: (abfrage) =>
      beobachten && weiterFragen(abfrage.state.data, abfrage.state.error) ? ABFRAGE_MS : false,
    retry: false,
  });

/**
 * Weiter nach dem Fortschritt fragen? Solange die Wiederherstellung läuft, und auch dann, wenn der
 * Server beim Umschalten kurz gar nicht oder mit 503 antwortet. Nicht mehr, wenn der Zugang weg ist.
 */
export function weiterFragen(
  status: WiederherstellungsStatus | undefined,
  fehler: unknown,
): boolean {
  if (fehler) return istKurzeUnterbrechung(fehler) && !istZugangWeg(fehler);
  return status?.state === "running";
}

/**
 * Fehler beim Abfragen des Fortschritts, die während einer laufenden Wiederherstellung dazugehören:
 * Wartung (503, `code: maintenance`) und kurz keine Antwort beim Umschalten der Datenbank.
 */
export function istKurzeUnterbrechung(fehler: unknown): boolean {
  return istWartungsFehler(fehler) || (fehler instanceof ApiFehler && fehler.art === "netzwerk");
}

/** Zugang geändert: Nach dem Tausch gelten Konten und Geräte aus der Sicherung. */
export function istZugangWeg(fehler: unknown): boolean {
  return (
    fehler instanceof ApiFehler && (fehler.art === "nicht_angemeldet" || fehler.art === "verboten")
  );
}

export type Ansicht = "waehlen" | "passwort" | "vorschau" | "bestaetigen" | "fortschritt";

/** Die Schritte, wie die Kopfzeile des Ablaufs sie zeigt. */
export const ANSICHTEN: readonly Ansicht[] = [
  "waehlen",
  "passwort",
  "vorschau",
  "bestaetigen",
  "fortschritt",
];

/** Beim Öffnen: Läuft schon eine Wiederherstellung, gleich den Fortschritt zeigen. */
export function startAnsicht(status: WiederherstellungsStatus | undefined): Ansicht {
  return status?.state === "running" ? "fortschritt" : "waehlen";
}

/** Nach der Wahl einer Sicherung: Passwort nur, wenn sie verschlüsselt ist. */
export function nachDerWahl(quelle: Quelle): Ansicht {
  return quelle.needs_passphrase ? "passwort" : "vorschau";
}

/** Schritt, der gerade läuft, oder der zuletzt fehlgeschlagene. */
export function aktuellerSchritt(status: WiederherstellungsStatus): SchrittId | null {
  const fehler = status.steps.find((schritt) => schritt.state === "failed");
  return fehler?.key ?? status.step ?? null;
}

/**
 * Schritte vor dem Tausch: Schlägt einer davon fehl, verwirft der Server die neue Datenbank, und
 * die bisherigen Daten sind unverändert.
 */
const VOR_DEM_TAUSCH: ReadonlySet<SchrittId> = new Set([
  "check",
  "maintenance",
  "pre_backup",
  "load",
  "upgrade",
  "journal",
  "verify",
]);

/** Sind die bisherigen Daten nach einem Fehler sicher unverändert? */
export function datenUnveraendert(status: WiederherstellungsStatus): boolean {
  if (status.state !== "failed") return false;
  const schritt = aktuellerSchritt(status);
  return schritt === null || VOR_DEM_TAUSCH.has(schritt);
}

/** Beim Umschalten (und kurz danach) ist der Server ein paar Sekunden nicht erreichbar. */
export function umschaltenLaeuft(status: WiederherstellungsStatus | undefined): boolean {
  return status?.state === "running" && (status.step === "swap" || status.step === "finish");
}

export interface Bestaetigungen {
  /** „Der jetzige Stand wird ersetzt“ */
  ersetzen: boolean;
  /** Ausdrücklich angenommen: danach an diesem Gerät kein Zugang zur Verwaltung */
  aussperren: boolean;
}

/** Was vor dem Ausführen noch fehlt; leer = es kann losgehen. */
export function fehlendeBestaetigungen(
  vorschau: Vorschau,
  bestaetigt: Bestaetigungen,
): (keyof Bestaetigungen)[] {
  const fehlt: (keyof Bestaetigungen)[] = [];
  if (vorschau.access.lockout_risk && !bestaetigt.aussperren) fehlt.push("aussperren");
  if (!bestaetigt.ersetzen) fehlt.push("ersetzen");
  return fehlt;
}

/** Die Anfrage für `POST /backup/restore/execute`; `confirm` ist laut Server die Kennung der Sicherung. */
export function ausfuehrenAnfrage(
  vorschau: Vorschau,
  passwort: string,
  nachtragen: boolean,
  aussperrenAngenommen: boolean,
): AusfuehrenAnfrage {
  return {
    source_id: vorschau.source.id,
    passphrase: vorschau.source.needs_passphrase ? passwort : null,
    confirm: vorschau.confirm,
    apply_journal: nachtragen,
    accept_lockout: vorschau.access.lockout_risk && aussperrenAngenommen,
  };
}

/** Lohnt sich die Wahl „Ergebnisse nachtragen“? Nur, wenn es eine Mitschrift dazu gibt. */
export function nachtragenMoeglich(vorschau: Vorschau): boolean {
  return vorschau.source.journal_available || vorschau.comparison.journal_applicable > 0;
}

/**
 * Was ohne Nachtragen verloren ginge: alle Ergebnis-Eingaben seit der Sicherung. Mit Nachtragen
 * nur die, die der Server als verloren meldet.
 */
export function verloreneEingaben(vorschau: Vorschau, nachtragen: boolean): number {
  const { comparison } = vorschau;
  return nachtragen ? comparison.events_lost : comparison.events_since_backup;
}

// --- Sicherungen in der Liste ---------------------------------------------------------

/** Reihenfolge der Orte: Stick zuerst, weil nur die Kopie dort die Schlüssel enthält. */
const ORT_REIHENFOLGE: readonly Ort[] = ["usb", "local", "pre_restore"];

/** Alle Orte, an denen eine Sicherung liegt, ohne Doppelte (Stick, Server, vor Wiederherstellung). */
export function orteDerQuelle(quelle: Quelle): Ort[] {
  const orte = new Set<Ort>([quelle.location, ...(quelle.locations ?? [])]);
  return ORT_REIHENFOLGE.filter((ort) => orte.has(ort));
}

/**
 * Jede Sicherung einmal. Der Server fasst Kopien derselben Sicherung schon zusammen und nennt die
 * übrigen in `other_ids`; steht eine dieser Kopien trotzdem als eigener Eintrag da, fällt sie weg.
 */
export function quellenZusammenfassen(quellen: readonly Quelle[]): Quelle[] {
  const abgedeckt = new Set<string>();
  const liste: Quelle[] = [];
  for (const quelle of quellen) {
    if (abgedeckt.has(quelle.id)) continue;
    liste.push(quelle);
    abgedeckt.add(quelle.id);
    for (const id of quelle.other_ids ?? []) abgedeckt.add(id);
  }
  return liste;
}

/**
 * Kopie derselben Sicherung, die ohne Sicherungspasswort lesbar ist (meist die vom Server), falls
 * der Server eine meldet (`other_sources` mit `needs_passphrase` false): der Ausweg, wenn das
 * Passwort vergessen ist. Eine Kopie mit Schlüsseln geht vor; ob die gewählte Schlüssel enthält,
 * steht in `contains_keys` (vom Server: nein – dann gelten die Schlüssel dieses Servers).
 */
export function kopieOhnePasswort(quelle: Quelle): Quelle | null {
  if (!quelle.needs_passphrase) return null;
  const ohnePasswort = (quelle.other_sources ?? []).filter((andere) => !andere.needs_passphrase);
  const kopie = ohnePasswort.find((andere) => andere.contains_keys) ?? ohnePasswort[0];
  if (!kopie) return null;
  return {
    ...quelle,
    id: kopie.id,
    location: kopie.location,
    locations: orteDerQuelle(quelle),
    other_ids: [],
    other_sources: [],
    // `file_name` bleibt der des Eintrags; Datei und Ort der Kopie nennt danach die Vorschau
    // des Servers (`vorschau.source`).
    encrypted: false,
    needs_passphrase: false,
    contains_keys: kopie.contains_keys,
  };
}

// --- Meldungen des Servers ------------------------------------------------------------

/**
 * Kennungen mit eigenem Text (`wiederherstellen.meldung.<code>` in `system.json`); siehe
 * `docs/WIEDERHERSTELLUNG.md`. Andere Kennungen zeigen den Text des Servers.
 */
export const MELDUNG_CODES = [
  // Probleme der Vorschau
  "schema_newer",
  "schema_missing",
  "keys_conflict",
  "db_unreachable",
  "db_not_found",
  "db_no_createdb",
  "db_not_owner",
  "restore_running",
  // Hinweise der Vorschau und des Ergebnisses
  "no_file_checksum",
  "server_copy_without_keys",
  "other_app_version",
  "module_restart_failed",
  "after_backup_failed",
  // Zugang danach
  "enforcement_off",
  "enforcement_on_after_restore",
  "lockout",
  "stays_signed_in",
  "sign_in_again",
  "pin_changed",
] as const;

const EIGENER_TEXT: ReadonlySet<string> = new Set(MELDUNG_CODES);

export type Uebersetzer = (schluessel: string, werte?: Record<string, unknown>) => string;

/** Versionen zu `other_app_version` (Vorschau und Ergebnis), als Werte für `meldungTexte`. */
export function versionWerte(
  sicherung: string | null | undefined,
  jetzt: string | null | undefined,
): { version_sicherung?: string; version_jetzt?: string } {
  const alt = sicherung?.trim();
  const neu = jetzt?.trim();
  return alt && neu ? { version_sicherung: alt, version_jetzt: neu } : {};
}

/**
 * Eigener Text für bekannte Kennungen, sonst der des Servers; gleiche Texte nur einmal. Zu
 * `other_app_version` mit beiden Versionsnummern (`versionWerte`) der Text mit den Nummern.
 */
export function meldungTexte(
  meldungen: readonly Meldung[] | undefined,
  t: Uebersetzer,
  werte: Record<string, unknown> = {},
): string[] {
  const texte = (meldungen ?? []).map((meldung) => {
    if (!EIGENER_TEXT.has(meldung.code)) return meldung.message_de;
    const mitNummern =
      meldung.code === "other_app_version" && werte.version_sicherung && werte.version_jetzt;
    const schluessel = mitNummern ? "other_app_version_nummern" : meldung.code;
    return t(`wiederherstellen.meldung.${schluessel}`, werte);
  });
  return [...new Set(texte.filter(Boolean))];
}

/** Die Texte des Servers, für „Einzelheiten für den Betreuer des Servers“. */
export function serverTexte(meldungen: readonly Meldung[] | undefined): string[] {
  return (meldungen ?? []).map((meldung) => meldung.message_de);
}

/** Was in der Sicherung fehlt, sodass du danach an diesem Gerät nicht mehr in die Verwaltung kommst. */
export function fehltInSicherung(zugang: Zugang): ("konto" | "rolle" | "geraet")[] {
  const fehlt: ("konto" | "rolle" | "geraet")[] = [];
  if (zugang.account_in_backup === false) fehlt.push("konto");
  else if (zugang.account_is_admin_in_backup === false) fehlt.push("rolle");
  if (zugang.device_in_backup === false) fehlt.push("geraet");
  return fehlt;
}

/** Hinweise im Ergebnis; „Sicherung danach fehlgeschlagen“ steht schon in der Zusammenfassung. */
export function ergebnisHinweise(status: WiederherstellungsStatus): Meldung[] {
  const ergebnis = status.result;
  if (!ergebnis) return [];
  return (ergebnis.note_items ?? []).filter(
    (meldung) => !(meldung.code === "after_backup_failed" && ergebnis.after_backup_ok === false),
  );
}

// --- Von Hand nachzutragen -------------------------------------------------------------

/** Gründe mit eigenem Text (`wiederherstellen.nachtragen_grund.<code>`). */
export const GRUND_CODES = ["start_not_in_backup", "does_not_match"] as const;

/**
 * Starts, deren Ergebnisse sich nicht nachtragen ließen, sortiert nach Wettbewerb, Startnummer und
 * Start. Sie müssen vom Startzettel von Hand nachgetragen werden.
 */
export function uebersprungeneStarts(status: WiederherstellungsStatus): UebersprungenerStart[] {
  const ergebnis = status.result;
  if (!ergebnis) return [];
  const liste = ergebnis.skipped_starts?.length
    ? ergebnis.skipped_starts
    : (ergebnis.journal?.skipped_starts ?? []);
  const ohne = Number.POSITIVE_INFINITY;
  return [...liste].sort(
    (a, b) =>
      (a.competition_name ?? "").localeCompare(b.competition_name ?? "", "de") ||
      (a.start_number ?? ohne) - (b.start_number ?? ohne) ||
      (a.attempt ?? ohne) - (b.attempt ?? ohne),
  );
}

/** Grund in Klartext: eigener Text für bekannte Gründe, sonst der des Servers. */
export function grundText(start: UebersprungenerStart, t: Uebersetzer): string {
  return (GRUND_CODES as readonly string[]).includes(start.reason_code)
    ? t(`wiederherstellen.nachtragen_grund.${start.reason_code}`)
    : start.message_de;
}
