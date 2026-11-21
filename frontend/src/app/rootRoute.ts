import { createRootRoute } from "@tanstack/react-router";

/**
 * Wurzel aller Routen. Steht bewusst in einer eigenen Datei ohne weitere Importe,
 * damit Module sie als Eltern-Route nutzen können, ohne die App-Shell zu laden.
 * Die Shell hängt sich in `router.ts` als Komponente ein.
 */
export const rootRoute = createRootRoute();
