import { createRoute } from "@tanstack/react-router";
import { Settings } from "lucide-react";
import type { ModulManifest } from "../../app/modul";
import { rootRoute } from "../../app/rootRoute";
import { InArbeit } from "../../components/InArbeit";

const ID = "system";
const PFAD = "/system";

const route = createRoute({
  getParentRoute: () => rootRoute,
  path: PFAD,
  component: () => <InArbeit namensraum={ID} icon={Settings} />,
});

export const system: ModulManifest = {
  id: ID,
  namensraum: ID,
  navigation: { art: "station", pfad: PFAD, icon: Settings, reihenfolge: 50 },
  berechtigung: "system.verwalten",
  routen: [route],
};
