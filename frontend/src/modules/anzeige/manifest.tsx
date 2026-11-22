import { createRoute } from "@tanstack/react-router";
import { MonitorPlay } from "lucide-react";
import type { ModulManifest } from "../../app/modul";
import { rootRoute } from "../../app/rootRoute";
import { anzeigeEreignisse } from "./api";
import { SchirmSeite } from "./schirm/SchirmSeite";
import { VerwaltungSeite } from "./verwaltung/VerwaltungSeite";

const ID = "anzeige";
const PFAD = "/anzeige";

interface VerwaltungSuche {
  anzeige?: string;
}

const verwaltungRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: PFAD,
  validateSearch: (suche: Record<string, unknown>): VerwaltungSuche =>
    typeof suche.anzeige === "string" && suche.anzeige ? { anzeige: suche.anzeige } : {},
  component: function AnzeigeVerwaltung() {
    const { anzeige } = verwaltungRoute.useSearch();
    const navigate = verwaltungRoute.useNavigate();
    return (
      <VerwaltungSeite
        auswahl={anzeige}
        onAuswahl={(id) => void navigate({ search: { anzeige: id }, replace: true })}
      />
    );
  },
});

/** Bildschirm dieses Geräts (`GET /displays/mine/feed`): für Fernseher mit gekoppeltem Gerät. */
const geraetSchirmRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: `${PFAD}/schirm`,
  component: () => <SchirmSeite quelle={{ art: "geraet" }} />,
});

/** Bildschirm einer bestimmten Anzeige, z. B. zum Öffnen aus der Verwaltung. */
const anzeigeSchirmRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: `${PFAD}/schirm/$anzeigeId`,
  component: function AnzeigeSchirm() {
    const { anzeigeId } = anzeigeSchirmRoute.useParams();
    return <SchirmSeite quelle={{ art: "anzeige", id: anzeigeId }} />;
  },
});

export const anzeige: ModulManifest = {
  id: ID,
  namensraum: ID,
  navigation: { art: "station", pfad: PFAD, icon: MonitorPlay, reihenfolge: 40 },
  // Verwaltung braucht `display.control`, der Bildschirm `display.read`; eins reicht für die Station.
  berechtigung: ["display.control", "display.read"],
  routen: [verwaltungRoute, geraetSchirmRoute, anzeigeSchirmRoute],
  ereignisse: anzeigeEreignisse,
};
