import { Users } from "lucide-react";
import { EREIGNIS_VERBUNDEN } from "../../api/ereignisse";
import type { ModulManifest } from "../../app/modul";
import { teilnehmerSchluessel } from "./api";
import { TEILNEHMER_PFAD } from "./pfade";
import { teilnehmerRouten } from "./routen";

const alles = [teilnehmerSchluessel.alle];

export const teilnehmer: ModulManifest = {
  id: "teilnehmer",
  namensraum: "teilnehmer",
  navigation: {
    art: "bereich",
    station: "anmeldung",
    pfad: TEILNEHMER_PFAD,
    icon: Users,
    reihenfolge: 10,
  },
  berechtigung: "person.read",
  routen: teilnehmerRouten,
  // Ereignisnamen aus backend/app/modules/teilnehmer/service.py. Neu geladen wird im Hintergrund;
  // Eingaben in offenen Formularen bleiben stehen (siehe PersonFormular).
  ereignisse: {
    "person.created": alles,
    "person.updated": alles,
    "person.deleted": alles,
    "person.imported": alles,
    "club.created": alles,
    "club.updated": alles,
    "club.deleted": alles,
    "club.merged": alles,
    [EREIGNIS_VERBUNDEN]: alles,
  },
};
