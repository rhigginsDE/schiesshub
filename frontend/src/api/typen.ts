/**
 * Typen der API-Antworten (Felder deutsch, snake_case, wie vom Backend geliefert).
 * Quelle ist `schema.gen.ts`, erzeugt mit `pnpm gen:api` aus der OpenAPI-Beschreibung des Backends.
 * Hier stehen nur sprechende Namen dafür; von Hand gepflegt wird nichts.
 */
import type { components } from "./schema.gen";

type Schemas = components["schemas"];

export type Health = Schemas["HealthOut"];
export type KatalogStatus = Schemas["KatalogStatusOut"];
export type KatalogFehler = Schemas["KatalogFehlerOut"];
export type Verband = Schemas["VerbandOut"];
export type Gruppe = Schemas["GruppeOut"];
export type Disziplin = Schemas["DisziplinOut"];
export type DisziplinDetail = Schemas["DisziplinDetailOut"];
export type Ablauf = Schemas["AblaufOut"];
export type Variante = Schemas["Variante"];
export type Abschnitt = Schemas["Abschnitt"];
export type Wertung = Schemas["Wertung"];
export type Klasse = Schemas["KlasseOut"];
