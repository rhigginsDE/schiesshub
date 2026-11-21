import { localStorageColorSchemeManager, MantineProvider } from "@mantine/core";
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { type ModulManifest, ModulProvider } from "./app/modul";
import type { AppRouter } from "./app/router";
import { cssVariablesResolver, FARBSCHEMA_SCHLUESSEL, theme } from "./theme";

const farbschemaSpeicher = localStorageColorSchemeManager({ key: FARBSCHEMA_SCHLUESSEL });

interface AppProps {
  router: AppRouter;
  queryClient: QueryClient;
  module: ModulManifest[];
}

/** Stellt Theme, Daten-Cache, Modul-Liste und Router bereit. */
export function App({ router, queryClient, module }: AppProps) {
  return (
    <MantineProvider
      theme={theme}
      cssVariablesResolver={cssVariablesResolver}
      colorSchemeManager={farbschemaSpeicher}
      defaultColorScheme="dark"
    >
      <QueryClientProvider client={queryClient}>
        <ModulProvider value={module}>
          <RouterProvider router={router} />
        </ModulProvider>
      </QueryClientProvider>
    </MantineProvider>
  );
}
