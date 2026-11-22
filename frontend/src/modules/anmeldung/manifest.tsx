import { createRoute } from "@tanstack/react-router";
import { UserPlus } from "lucide-react";
import type { ModulManifest } from "../../app/modul";
import { rootRoute } from "../../app/rootRoute";
import { AnmeldungSeite } from "./AnmeldungSeite";
import { startsEreignisse } from "./api";

export const ANMELDUNG_ID = "anmeldung";
const PFAD = "/anmeldung";

const route = createRoute({
  getParentRoute: () => rootRoute,
  path: PFAD,
  component: () => <AnmeldungSeite station={ANMELDUNG_ID} icon={UserPlus} />,
});

export const anmeldung: ModulManifest = {
  id: ANMELDUNG_ID,
  namensraum: ANMELDUNG_ID,
  navigation: { art: "station", pfad: PFAD, icon: UserPlus, reihenfolge: 20 },
  berechtigung: "anmeldung.nutzen",
  routen: [route],
  ereignisse: startsEreignisse,
};
