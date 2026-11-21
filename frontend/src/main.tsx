import "@mantine/core/styles.css";
import "./theme/schriften";
import "./theme/global.css";
import "./theme/bausteine.css";
import "./i18n";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { sichtbareModule } from "./app/berechtigungen";
import { erstelleQueryClient } from "./app/queryClient";
import { type AppRouter, erstelleRouter } from "./app/router";
import { module as alleModule } from "./modules";

const module = sichtbareModule(alleModule);
const router = erstelleRouter(module);
const queryClient = erstelleQueryClient();

declare module "@tanstack/react-router" {
  interface Register {
    router: AppRouter;
  }
}

const wurzel = document.getElementById("root");
if (!wurzel) throw new Error("Element #root fehlt in index.html");

createRoot(wurzel).render(
  <StrictMode>
    <App router={router} queryClient={queryClient} module={module} />
  </StrictMode>,
);
