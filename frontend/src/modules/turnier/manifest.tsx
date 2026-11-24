import { Trophy } from "lucide-react";
import type { EreignisZuordnung } from "../../api/ereignisse";
import type { ModulManifest } from "../../app/modul";
import { turnierEreignisse } from "./abfragen";
import { turnierGeloescht } from "./geloescht";
import { TURNIER_ID, TURNIER_PFAD } from "./pfade";
import { turnierRouten } from "./routen";

/** Wie `turnierEreignisse`, dazu das Aufräumen nach `tournament.deleted` (vor dem Neuladen). */
const ereignisse: EreignisZuordnung = {
  ...turnierEreignisse,
  "tournament.deleted": [turnierGeloescht, ...(turnierEreignisse["tournament.deleted"] ?? [])],
};

export const turnier: ModulManifest = {
  id: TURNIER_ID,
  namensraum: TURNIER_ID,
  navigation: { art: "station", pfad: TURNIER_PFAD, icon: Trophy, reihenfolge: 10 },
  berechtigung: "tournament.read",
  routen: turnierRouten,
  ereignisse,
  titelTurnier: "adresse",
};
