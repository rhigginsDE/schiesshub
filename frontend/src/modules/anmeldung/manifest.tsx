import { createRoute } from "@tanstack/react-router";
import { UserPlus } from "lucide-react";
import type { ModulManifest } from "../../app/modul";
import { rootRoute } from "../../app/rootRoute";
import { InArbeit } from "../../components/InArbeit";

const ID = "anmeldung";
const PFAD = "/anmeldung";

const route = createRoute({
  getParentRoute: () => rootRoute,
  path: PFAD,
  component: () => <InArbeit namensraum={ID} icon={UserPlus} />,
});

export const anmeldung: ModulManifest = {
  id: ID,
  namensraum: ID,
  navigation: { art: "station", pfad: PFAD, icon: UserPlus, reihenfolge: 10 },
  berechtigung: "anmeldung.nutzen",
  routen: [route],
};
