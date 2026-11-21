import { createRoute } from "@tanstack/react-router";
import { MonitorPlay } from "lucide-react";
import type { ModulManifest } from "../../app/modul";
import { rootRoute } from "../../app/rootRoute";
import { InArbeit } from "../../components/InArbeit";

const ID = "anzeige";
const PFAD = "/anzeige";

const route = createRoute({
  getParentRoute: () => rootRoute,
  path: PFAD,
  component: () => <InArbeit namensraum={ID} icon={MonitorPlay} />,
});

export const anzeige: ModulManifest = {
  id: ID,
  namensraum: ID,
  navigation: { art: "station", pfad: PFAD, icon: MonitorPlay, reihenfolge: 40 },
  berechtigung: "anzeige.nutzen",
  routen: [route],
};
