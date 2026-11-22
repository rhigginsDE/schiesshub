import { createRoute } from "@tanstack/react-router";
import type { AnmeldeSeite } from "../../app/anmeldeLage";
import { rootRoute } from "../../app/rootRoute";
import { AnmeldenSeite } from "./AnmeldenSeite";
import { EinrichtungSeite } from "./EinrichtungSeite";
import { KoppelnSeite } from "./KoppelnSeite";

/** Pfade der Anmelde-Seiten. Die App-Shell zeigt sie ohne Stationsnavigation. */
export const ANMELDE_PFADE = {
  einrichtung: "/einrichtung",
  koppeln: "/pair",
  anmelden: "/anmelden",
} as const satisfies Record<AnmeldeSeite, string>;

export interface KoppelnSuche {
  code?: string;
}

const einrichtungRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: ANMELDE_PFADE.einrichtung,
  component: EinrichtungSeite,
});

const koppelnRoute = createRoute({
  getParentRoute: () => rootRoute,
  // Den Pfad gibt der Server im Kopplungscode vor (`pair_path`), deshalb englisch.
  path: ANMELDE_PFADE.koppeln,
  validateSearch: (suche: Record<string, unknown>): KoppelnSuche =>
    typeof suche.code === "string" && suche.code ? { code: suche.code } : {},
  component: function Koppeln() {
    const { code } = koppelnRoute.useSearch();
    return <KoppelnSeite code={code} />;
  },
});

const anmeldenRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: ANMELDE_PFADE.anmelden,
  component: AnmeldenSeite,
});

export const anmeldeRouten = [einrichtungRoute, koppelnRoute, anmeldenRoute];

export function istAnmeldePfad(pfad: string): boolean {
  return Object.values(ANMELDE_PFADE).some((ziel) => pfad === ziel);
}

/** Welche Anmelde-Seite unter der Adresse liegt, sonst `null`. */
export function anmeldeSeiteZuPfad(pfad: string): AnmeldeSeite | null {
  const treffer = Object.entries(ANMELDE_PFADE).find(([, ziel]) => ziel === pfad);
  return treffer ? (treffer[0] as AnmeldeSeite) : null;
}

/** Die Seite, die erscheint, wenn der Server eine Anmeldung verlangt und etwas fehlt. */
export function PflichtSeite({ seite }: { seite: AnmeldeSeite }) {
  if (seite === "einrichtung") return <EinrichtungSeite />;
  if (seite === "koppeln") return <KoppelnSeite />;
  return <AnmeldenSeite />;
}
