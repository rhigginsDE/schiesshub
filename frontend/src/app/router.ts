import { createRoute, createRouter, type RouterHistory } from "@tanstack/react-router";
import { anmeldeRouten } from "../modules/auth/routen";
import { AppShell } from "./AppShell";
import type { ModulManifest } from "./modul";
import { NichtGefunden } from "./NichtGefunden";
import { rootRoute } from "./rootRoute";
import { Startseite } from "./Startseite";

const startRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: Startseite,
});

/** Baut den Router aus der Startseite und den Routen aller Module. */
export function erstelleRouter(module: ModulManifest[], history?: RouterHistory) {
  rootRoute.update({ component: AppShell, notFoundComponent: NichtGefunden });
  const routeTree = rootRoute.addChildren([
    startRoute,
    ...anmeldeRouten,
    ...module.flatMap((modul) => modul.routen),
  ]);
  return createRouter({
    routeTree,
    history,
    defaultPreload: "intent",
    scrollRestoration: true,
  });
}

export type AppRouter = ReturnType<typeof erstelleRouter>;
