import { createRoute, useNavigate } from "@tanstack/react-router";
import { LayoutGrid } from "lucide-react";
import type { ModulManifest } from "../../app/modul";
import { rootRoute } from "../../app/rootRoute";
import { startsEreignisse } from "../anmeldung/api";
import { leseStandSuche, STAND_ID, STAND_PFAD, type StandSuche } from "./pfade";
import { StandSeite } from "./StandSeite";

export { STAND_ID, STAND_PFAD };

const route = createRoute({
  getParentRoute: () => rootRoute,
  path: STAND_PFAD,
  validateSearch: leseStandSuche,
  component: StandRouteSeite,
});

function StandRouteSeite() {
  const suche = route.useSearch();
  const navigate = useNavigate();
  return (
    <StandSeite
      suche={suche}
      onSuche={(neu: StandSuche) => void navigate({ to: STAND_PFAD, search: neu })}
    />
  );
}

export const stand: ModulManifest = {
  id: STAND_ID,
  namensraum: STAND_ID,
  navigation: {
    art: "bereich",
    station: "erfassung",
    pfad: STAND_PFAD,
    icon: LayoutGrid,
    reihenfolge: 10,
    // Die Standaufsicht (nur `start.*`) sieht die Erfassung nicht: dann ist der Stand ihre Station.
    eigenstaendig: true,
  },
  titelTurnier: "aktiv",
  berechtigung: ["start.read", "start.call"],
  routen: [route],
  ereignisse: startsEreignisse,
};
