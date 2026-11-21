import { createRoute } from "@tanstack/react-router";
import { Target } from "lucide-react";
import type { ModulManifest } from "../../app/modul";
import { rootRoute } from "../../app/rootRoute";
import { InArbeit } from "../../components/InArbeit";

const ID = "erfassung";
const PFAD = "/erfassung";

const route = createRoute({
  getParentRoute: () => rootRoute,
  path: PFAD,
  component: () => <InArbeit namensraum={ID} icon={Target} />,
});

export const erfassung: ModulManifest = {
  id: ID,
  namensraum: ID,
  navigation: { art: "station", pfad: PFAD, icon: Target, reihenfolge: 30 },
  berechtigung: "erfassung.nutzen",
  routen: [route],
};
