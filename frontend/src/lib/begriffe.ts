import { queryOptions, useQuery } from "@tanstack/react-query";
import { apiGet } from "../api/client";
import type { components } from "../api/schema.gen";

/**
 * Formelle Begriffe je Verband (`GET /api/v1/terms`): die Wörter für Ausschreibung, Aushang,
 * Start- und Ergebnisliste und Anzeige. Die Bedienung der Stationen behält ihre Alltagswörter
 * („Gleichstand“, „aufgegeben“) und nutzt diese Begriffe nicht.
 */
export type Begriffe = components["schemas"]["Begriffe"];
export type BegriffSchluessel = keyof Begriffe;
/** Antwort des Servers: Standardsatz und je Verband (Kleinbuchstaben) der vollständige Satz. */
export type Begriffssaetze = components["schemas"]["TermsOut"];

/**
 * Rückfall, solange der Server nichts geliefert hat (oder ein älterer Server ohne `/terms`): die
 * bisherigen festen Wörter, wie sie im Standardsatz des Servers stehen (BDS-Sporthandbuch).
 */
export const BEGRIFFE_RUECKFALL: Readonly<Begriffe> = Object.freeze({
  ergebnisliste: "Ergebnisliste",
  ergebnislisten: "Ergebnislisten",
  startliste: "Startliste",
  startnummer: "Startnummer",
  startzeit: "Starttermin",
  schiessstand: "Schießstand",
  schiessstaende: "Schießstände",
  schuetzenstand: "Schützenstand",
  schuetzenstaende: "Schützenstände",
  durchgang: "Durchgang",
  durchgaenge: "Durchgänge",
  durchgangszeit: "Durchgangszeit",
  serie: "Serie",
  serien: "Serien",
  wertungsserie: "Wertungsserie",
  wertungsserien: "Wertungsserien",
  wertungsschuesse: "Wertungsschüsse",
  trefferaufnahme: "Trefferaufnahme",
  ergebnisgleichheit: "Ringgleichheit",
  ringgleichheit: "Ringgleichheit",
  treffergleichheit: "Treffergleichheit",
  abbruch: "Abbruch",
  abbruch_kurz: "AB",
  nicht_angetreten: "nicht angetreten",
  disqualifiziert: "disqualifiziert",
  disqualifikation: "Disqualifikation",
  einspruch: "Einspruch",
  protest: "Protest",
  protestgebuehr: "Protestgebühr",
  gebuehr_einspruch: "Protestgebühr",
  standaufsicht: "Standaufsicht",
  schiessleiter: "Schießleiter",
  wettkampfleitung: "Wettkampfleitung",
  startgeld: "Startgeld",
  klasse: "Wettbewerbsklasse",
  klassen: "Wettbewerbsklassen",
  kennziffer: "Kennziffer",
});

export const begriffeSchluessel = ["begriffe"] as const;

/**
 * Die Begriffe ändern sich nur mit einer neuen Version des Servers: einmal laden, lange behalten.
 * `still`: Ein Fehler (z. B. älterer Server) wird nicht gemeldet – dann gilt der Rückfall.
 */
export const begriffeAbfrage = () =>
  queryOptions({
    queryKey: begriffeSchluessel,
    queryFn: ({ signal }) => apiGet<Begriffssaetze>("/terms", { signal, still: true }),
    staleTime: 12 * 60 * 60 * 1000,
    gcTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
  });

/** Alle Begriffssätze des Servers; `null`, solange nichts da ist (dann gilt der Rückfall). */
export function useBegriffe(): Begriffssaetze | null {
  const { data } = useQuery(begriffeAbfrage());
  return data ?? null;
}

/**
 * Der Begriffssatz für einen Verband (`catalog_federation`, Groß-/Kleinschreibung egal): erst der
 * Satz des Verbands, dann der Standardsatz, dann der feste Rückfall – je Begriff, damit ein
 * fehlendes oder leeres Wort nie eine Lücke lässt.
 */
export function begriffeFuer(
  begriffe: Begriffssaetze | null | undefined,
  verband?: string | null,
): Begriffe {
  const satzVerband = verband ? begriffe?.federations?.[verband.trim().toLowerCase()] : undefined;
  const standard = begriffe?.default;
  const ergebnis = { ...BEGRIFFE_RUECKFALL };
  for (const schluessel of Object.keys(ergebnis) as BegriffSchluessel[]) {
    const wort =
      textOderNichts(satzVerband?.[schluessel]) ?? textOderNichts(standard?.[schluessel]);
    if (wort) ergebnis[schluessel] = wort;
  }
  return ergebnis;
}

/** Bequem in Komponenten: lädt die Begriffe und löst sie für den Verband auf. */
export function useBegriffeFuer(verband?: string | null): Begriffe {
  return begriffeFuer(useBegriffe(), verband);
}

function textOderNichts(wert: unknown): string | null {
  return typeof wert === "string" && wert.trim() !== "" ? wert : null;
}
