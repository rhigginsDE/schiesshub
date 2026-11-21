import { createRoute } from "@tanstack/react-router";
import { Trophy } from "lucide-react";
import type { ModulManifest } from "../../app/modul";
import { rootRoute } from "../../app/rootRoute";
import { TurnierSeite } from "./TurnierSeite";

export const TURNIER_ID = "turnier";
const PFAD = "/turnier";

const route = createRoute({
  getParentRoute: () => rootRoute,
  path: PFAD,
  component: () => <TurnierSeite station={TURNIER_ID} icon={Trophy} />,
});

export const turnier: ModulManifest = {
  id: TURNIER_ID,
  namensraum: TURNIER_ID,
  navigation: { art: "station", pfad: PFAD, icon: Trophy, reihenfolge: 20 },
  berechtigung: "turnier.verwalten",
  routen: [route],
};
