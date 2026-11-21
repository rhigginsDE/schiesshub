import {
  type LucideIcon,
  MonitorSmartphone,
  ScrollText,
  Server,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import type { Anforderung } from "../../app/berechtigungen";

export type BereichId = "sicherung" | "geraete" | "personen" | "protokoll" | "server";

export interface SystemBereich {
  id: BereichId;
  pfad: `/system/${BereichId}`;
  icon: LucideIcon;
  berechtigung: Anforderung;
}

/** Bereiche der Station System in der Reihenfolge der Navigation. */
export const BEREICHE: readonly SystemBereich[] = [
  { id: "sicherung", pfad: "/system/sicherung", icon: ShieldCheck, berechtigung: "backup.read" },
  {
    id: "geraete",
    pfad: "/system/geraete",
    icon: MonitorSmartphone,
    berechtigung: "device.manage",
  },
  {
    id: "personen",
    pfad: "/system/personen",
    icon: UsersRound,
    berechtigung: ["user.manage", "role.manage"],
  },
  { id: "protokoll", pfad: "/system/protokoll", icon: ScrollText, berechtigung: "system.manage" },
  { id: "server", pfad: "/system/server", icon: Server, berechtigung: "system.manage" },
];

/** Wer einen der Bereiche sehen darf, sieht die Station. */
export const SYSTEM_BERECHTIGUNG: Anforderung = [
  "backup.read",
  "device.manage",
  "user.manage",
  "role.manage",
  "system.manage",
];

export function bereichZuPfad(pfad: string): SystemBereich | undefined {
  return BEREICHE.find((bereich) => pfad === bereich.pfad || pfad.startsWith(`${bereich.pfad}/`));
}
