import { createRoute, useNavigate } from "@tanstack/react-router";
import { Trophy } from "lucide-react";
import { rootRoute } from "../../app/rootRoute";
import { DRUCK_PFAD } from "./ausschreibung/Ausschreibung";
import { DruckSeite } from "./ausschreibung/DruckSeite";
import { EinrichtenSeite } from "./EinrichtenSeite";
import { EINRICHTEN_PFAD, type EinrichtenSuche, TURNIER_ID, TURNIER_PFAD } from "./pfade";
import { TurnierSeite } from "./TurnierSeite";
import { istBereich } from "./vollstaendigkeit";

const listeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: TURNIER_PFAD,
  component: () => <TurnierSeite station={TURNIER_ID} icon={Trophy} />,
});

const einrichtenRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: EINRICHTEN_PFAD,
  validateSearch: (suche: Record<string, unknown>): EinrichtenSuche => ({
    bereich: istBereich(suche.bereich) ? suche.bereich : undefined,
    wettbewerb: typeof suche.wettbewerb === "string" ? suche.wettbewerb : undefined,
  }),
  component: EinrichtenRouteSeite,
});

function EinrichtenRouteSeite() {
  const { turnierId } = einrichtenRoute.useParams();
  const suche = einrichtenRoute.useSearch();
  const navigate = useNavigate();
  return (
    <EinrichtenSeite
      turnierId={turnierId}
      suche={suche}
      onSuche={(neu) =>
        void navigate({
          to: EINRICHTEN_PFAD,
          params: { turnierId },
          search: neu,
          replace: true,
        })
      }
    />
  );
}

const druckRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: DRUCK_PFAD,
  component: function DruckRouteSeite() {
    const { turnierId } = druckRoute.useParams();
    return <DruckSeite turnierId={turnierId} />;
  },
});

export const turnierRouten = [listeRoute, einrichtenRoute, druckRoute];
