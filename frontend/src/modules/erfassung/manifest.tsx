import { createRoute, useNavigate } from "@tanstack/react-router";
import { Target } from "lucide-react";
import type { ModulManifest } from "../../app/modul";
import { rootRoute } from "../../app/rootRoute";
import { erfassungEreignisse } from "./api";
import { ErfassungSeite } from "./ErfassungSeite";
import { ERFASSUNG_ID, ERFASSUNG_PFAD, type ErfassungSuche, leseErfassungSuche } from "./pfade";

const route = createRoute({
  getParentRoute: () => rootRoute,
  path: ERFASSUNG_PFAD,
  validateSearch: leseErfassungSuche,
  component: ErfassungRouteSeite,
});

function ErfassungRouteSeite() {
  const suche = route.useSearch();
  const navigate = useNavigate();
  return (
    <ErfassungSeite
      station={ERFASSUNG_ID}
      icon={Target}
      suche={suche}
      onSuche={(neu: ErfassungSuche) => void navigate({ to: ERFASSUNG_PFAD, search: neu })}
    />
  );
}

export const erfassung: ModulManifest = {
  id: ERFASSUNG_ID,
  namensraum: ERFASSUNG_ID,
  navigation: { art: "station", pfad: ERFASSUNG_PFAD, icon: Target, reihenfolge: 30 },
  titelTurnier: "aktiv",
  berechtigung: ["result.capture", "result.read"],
  routen: [route],
  ereignisse: erfassungEreignisse,
};
