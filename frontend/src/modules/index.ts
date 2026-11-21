import type { ModulManifest } from "../app/modul";
import { anmeldung } from "./anmeldung/manifest";
import { anzeige } from "./anzeige/manifest";
import { erfassung } from "./erfassung/manifest";
import { katalog } from "./katalog/manifest";
import { system } from "./system/manifest";
import { turnier } from "./turnier/manifest";

/**
 * Alle Module der Oberfläche. Ein neues Modul wird hier eingetragen;
 * Navigation, Kacheln und Routen entstehen daraus von selbst.
 */
export const module: ModulManifest[] = [anmeldung, turnier, katalog, erfassung, anzeige, system];
