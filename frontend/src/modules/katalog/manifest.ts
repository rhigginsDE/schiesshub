import { BookOpenText } from "lucide-react";
import { schluessel } from "../../api/abfragen";
import { EREIGNIS_VERBUNDEN } from "../../api/ereignisse";
import type { ModulManifest } from "../../app/modul";
import { KATALOG_PFAD } from "./pfade";
import { katalogRouten } from "./routen";

export const katalog: ModulManifest = {
  id: "katalog",
  namensraum: "katalog",
  navigation: {
    art: "bereich",
    station: "turnier",
    pfad: KATALOG_PFAD,
    icon: BookOpenText,
    reihenfolge: 10,
  },
  // Der Katalog ist öffentlich lesbar (`/katalog/*` ohne Berechtigung): für jede Rolle.
  berechtigung: null,
  routen: katalogRouten,
  ereignisse: {
    // Der Server hat catalog/ neu eingelesen: Katalogdaten und Importstatus neu laden.
    "katalog.importiert": [schluessel.katalog.alle, schluessel.health],
    // Verbindung (wieder) da, etwa nach einem Server-Neustart: der Katalog kann sich geändert haben.
    [EREIGNIS_VERBUNDEN]: [schluessel.katalog.alle, schluessel.health],
  },
};
