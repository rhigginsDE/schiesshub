import { ApiFehler } from "../../api/client";
import i18n from "../../i18n";

/**
 * Meldung zu einem fehlgeschlagenen Speichern: die Erklärung des Servers, sonst der allgemeine
 * Text zur Fehlerart (z. B. „Keine Verbindung zum Server“).
 */
export function fehlerText(fehler: unknown): string {
  if (fehler instanceof ApiFehler) {
    if (fehler.detail) return fehler.detail;
    return i18n.t(`allgemein:fehler.${fehler.art}.titel`, {
      defaultValue: i18n.t("allgemein:fehler.unbekannt.titel"),
    });
  }
  return i18n.t("allgemein:fehler.unbekannt.titel");
}
