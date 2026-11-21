export const TEILNEHMER_PFAD = "/anmeldung/teilnehmer";
export const VEREINE_PFAD = "/anmeldung/teilnehmer/vereine";
export const IMPORT_PFAD = "/anmeldung/teilnehmer/import";

/**
 * Was in der Personenansicht offen ist. Steht in der Adresse, damit „Zurück“ funktioniert.
 * Nur IDs, nie Namen oder Suchtext (Datenschutz).
 */
export interface PersonenAdresse {
  /** ID der geöffneten Person */
  person?: string;
  /** Formular „Neue Person“ ist offen */
  neu?: boolean;
}
