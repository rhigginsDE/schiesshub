import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const BACKEND = "http://localhost:8010";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: true,
        // Läuft das Backend nicht, antwortet der Proxy mit 502 statt 500,
        // damit die Oberfläche „Server nicht erreichbar“ von einem Serverfehler unterscheiden kann.
        configure: (proxy) => {
          proxy.on("error", (_fehler, _anfrage, antwort) => {
            if ("writeHead" in antwort && !antwort.headersSent) {
              antwort.writeHead(502, { "Content-Type": "text/plain" });
              antwort.end("Backend nicht erreichbar");
            }
          });
        },
      },
    },
  },
  preview: {
    port: 5180,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
  },
});
