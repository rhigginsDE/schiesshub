import { createRoute, useNavigate } from "@tanstack/react-router";
import { rootRoute } from "../../app/rootRoute";
import { ImportSeite } from "./ImportSeite";
import { PersonenSeite } from "./PersonenSeite";
import { IMPORT_PFAD, type PersonenAdresse, TEILNEHMER_PFAD, VEREINE_PFAD } from "./pfade";
import { VereineSeite } from "./VereineSeite";

const ID_MUSTER = /^[0-9a-f-]{8,64}$/i;

const personenRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: TEILNEHMER_PFAD,
  validateSearch: (suche: Record<string, unknown>): PersonenAdresse => ({
    person:
      typeof suche.person === "string" && ID_MUSTER.test(suche.person) ? suche.person : undefined,
    neu: suche.neu === true || suche.neu === 1 || suche.neu === "1" ? true : undefined,
  }),
  component: PersonenRouteSeite,
});

function PersonenRouteSeite() {
  const adresse = personenRoute.useSearch();
  const navigate = useNavigate();
  return (
    <PersonenSeite
      adresse={adresse}
      onAdresse={(neu) =>
        void navigate({
          to: TEILNEHMER_PFAD,
          search: { person: neu.person, neu: neu.neu || undefined },
        })
      }
    />
  );
}

const vereineRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: VEREINE_PFAD,
  component: VereineSeite,
});

const importRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: IMPORT_PFAD,
  component: ImportSeite,
});

export const teilnehmerRouten = [personenRoute, vereineRoute, importRoute];
