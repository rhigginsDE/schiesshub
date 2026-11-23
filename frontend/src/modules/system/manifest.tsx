import { createRoute } from "@tanstack/react-router";
import { Settings } from "lucide-react";
import { schluessel } from "../../api/abfragen";
import type { EreignisZuordnung } from "../../api/ereignisse";
import type { ModulManifest } from "../../app/modul";
import { rootRoute } from "../../app/rootRoute";
import { SYSTEM_BERECHTIGUNG } from "./bereiche";
import { GeraeteBereich } from "./Geraete";
import { PersonenBereich } from "./Personen";
import { ProtokollBereich } from "./Protokoll";
import { PRUEFUNG_SCHLUESSEL } from "./Pruefung";
import { ServerBereich } from "./Server";
import { SicherungBereich } from "./Sicherung";
import { SystemSeite } from "./SystemSeite";
import { WiederherstellenBereich } from "./Wiederherstellen";
import { WIEDERHERSTELLEN_SCHLUESSEL } from "./wiederherstellenAblauf";

const ID = "system";
const PFAD = "/system";

const systemRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: PFAD,
  component: SystemSeite,
});

const startRoute = createRoute({
  getParentRoute: () => systemRoute,
  path: "/",
  // SystemSeite leitet auf den ersten erlaubten Bereich weiter.
  component: () => null,
});

const sicherungRoute = createRoute({
  getParentRoute: () => systemRoute,
  path: "sicherung",
  component: SicherungBereich,
});

/** Geführte Wiederherstellung; die Seite prüft `backup.restore` selbst. */
const wiederherstellenRoute = createRoute({
  getParentRoute: () => systemRoute,
  path: "sicherung/wiederherstellen",
  component: WiederherstellenBereich,
});

const geraeteRoute = createRoute({
  getParentRoute: () => systemRoute,
  path: "geraete",
  component: GeraeteBereich,
});

const personenRoute = createRoute({
  getParentRoute: () => systemRoute,
  path: "personen",
  component: PersonenBereich,
});

interface ProtokollSuche {
  seite?: number;
}

const protokollRoute = createRoute({
  getParentRoute: () => systemRoute,
  path: "protokoll",
  validateSearch: (suche: Record<string, unknown>): ProtokollSuche => {
    const seite = Number(suche.seite);
    return Number.isInteger(seite) && seite > 1 ? { seite } : {};
  },
  component: function Protokoll() {
    const { seite = 1 } = protokollRoute.useSearch();
    const navigate = protokollRoute.useNavigate();
    return (
      <ProtokollBereich
        seite={seite}
        onSeite={(neu) => void navigate({ search: neu > 1 ? { seite: neu } : {} })}
      />
    );
  },
});

const serverRoute = createRoute({
  getParentRoute: () => systemRoute,
  path: "server",
  component: ServerBereich,
});

// Geräte, Benutzer und Rollen entscheiden mit, ob Koppeln und PIN eingeschaltet werden dürfen.
const geraete = [schluessel.auth.geraete, schluessel.auth.protokollAlle, PRUEFUNG_SCHLUESSEL];
const personen = [
  schluessel.auth.personen,
  schluessel.auth.rollen,
  schluessel.auth.protokollAlle,
  PRUEFUNG_SCHLUESSEL,
];
const rollen = [schluessel.auth.rollen, schluessel.auth.protokollAlle, PRUEFUNG_SCHLUESSEL];

/** Live-Aktualisierung; die Sicherung (`backup.*`) lädt die App-Shell selbst neu. */
const ereignisse: EreignisZuordnung = {
  "device.paired": geraete,
  "device.updated": geraete,
  "device.deleted": geraete,
  "device.pairing_code_created": [schluessel.auth.protokollAlle],
  "role.created": rollen,
  "role.updated": rollen,
  "role.deleted": rollen,
  "user.created": personen,
  "user.updated": personen,
  "user.locked": personen,
  "auth.setup": personen,
  "auth.login": [schluessel.auth.protokollAlle],
  "auth.logout": [schluessel.auth.protokollAlle],
  "auth.enforcement_changed": [PRUEFUNG_SCHLUESSEL, schluessel.auth.protokollAlle],
  // Fortschritt einer Wiederherstellung (Zustand und Schritt; Einzelheiten holt die Seite selbst)
  "backup.restore": [WIEDERHERSTELLEN_SCHLUESSEL.status],
};

export const system: ModulManifest = {
  id: ID,
  namensraum: ID,
  navigation: { art: "station", pfad: PFAD, icon: Settings, reihenfolge: 50 },
  berechtigung: SYSTEM_BERECHTIGUNG,
  routen: [
    systemRoute.addChildren([
      startRoute,
      sicherungRoute,
      wiederherstellenRoute,
      geraeteRoute,
      personenRoute,
      protokollRoute,
      serverRoute,
    ]),
  ],
  ereignisse,
};
