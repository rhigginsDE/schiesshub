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
  /** Einstieg für ein Turnier (z. B. „Ergebnisse zeigen“ auf der Startseite): dessen Anzeige */
  turnier?: string;
}

const text = (wert: unknown) => (typeof wert === "string" && wert ? wert : undefined);

const verwaltungRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: PFAD,
  validateSearch: (suche: Record<string, unknown>): VerwaltungSuche => {
    const anzeige = text(suche.anzeige);
    const turnier = text(suche.turnier);
    return { ...(anzeige && { anzeige }), ...(turnier && { turnier }) };
  },
  component: function AnzeigeVerwaltung() {
    const { anzeige, turnier } = verwaltungRoute.useSearch();
    const navigate = verwaltungRoute.useNavigate();
    return (
      <VerwaltungSeite
        auswahl={anzeige}
        turnierId={turnier}
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
  titelTurnier: "aktiv",
  // Verwaltung braucht `display.control`, der Bildschirm `display.read`; eins reicht für die Station.
  berechtigung: ["display.control", "display.read"],
  routen: [verwaltungRoute, geraetSchirmRoute, anzeigeSchirmRoute],
  ereignisse: anzeigeEreignisse,
};
