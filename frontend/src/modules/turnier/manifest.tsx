import { Trophy } from "lucide-react";
import type { ModulManifest } from "../../app/modul";
import { turnierEreignisse } from "./abfragen";
import { TURNIER_ID, TURNIER_PFAD } from "./pfade";
import { turnierRouten } from "./routen";

export const turnier: ModulManifest = {
  id: TURNIER_ID,
  namensraum: TURNIER_ID,
  navigation: { art: "station", pfad: TURNIER_PFAD, icon: Trophy, reihenfolge: 10 },
  berechtigung: "tournament.read",
  routen: turnierRouten,
  ereignisse: turnierEreignisse,
};
