import i18n, { type Resource } from "i18next";
import { initReactI18next } from "react-i18next";

/**
 * Sprachdateien liegen unter src/locales/<sprache>/<namensraum>.json.
 * Eine weitere Sprache ist nur ein weiterer Ordner mit denselben Dateinamen; Code muss dafür nicht geändert werden.
 */
const dateien = import.meta.glob<Record<string, unknown>>("../locales/*/*.json", {
  eager: true,
  import: "default",
});

export const STANDARD_SPRACHE = "de";
export const STANDARD_NAMENSRAUM = "allgemein";

const ressourcen: Resource = {};
for (const [pfad, inhalt] of Object.entries(dateien)) {
  const treffer = /\/locales\/([^/]+)\/([^/]+)\.json$/.exec(pfad);
  if (!treffer) continue;
  const [, sprache, namensraum] = treffer as unknown as [string, string, string];
  ressourcen[sprache] ??= {};
  (ressourcen[sprache] as Record<string, unknown>)[namensraum] = inhalt;
}

/** Alle Sprachen, für die es einen Ordner gibt. */
export const sprachen = Object.keys(ressourcen).sort();

void i18n.use(initReactI18next).init({
  resources: ressourcen,
  lng: STANDARD_SPRACHE,
  fallbackLng: STANDARD_SPRACHE,
  supportedLngs: sprachen,
  ns: Object.keys(ressourcen[STANDARD_SPRACHE] ?? {}),
  defaultNS: STANDARD_NAMENSRAUM,
  interpolation: { escapeValue: false },
  returnNull: false,
});

/** Aktive Sprache als BCP-47-Kennung, z. B. für Intl. */
export function aktiveSprache(): string {
  return i18n.resolvedLanguage ?? i18n.language ?? STANDARD_SPRACHE;
}

export default i18n;
