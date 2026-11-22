import type { CSSProperties } from "react";
import { type Farbschema, farbschemata } from "../../../theme/tokens";

/**
 * Farbvariablen für den Bildschirm. Das Thema kommt aus dem Feed und gilt unabhängig vom
 * Farbschema des Geräts; deshalb setzt der Bildschirm die Variablen `--sh-*` selbst auf seinem
 * Wurzelelement (aus denselben Tokens wie die App), statt dem Gerät zu folgen.
 */
export function themaStil(thema: "dark" | "light"): CSSProperties {
  const schema: Farbschema = thema === "light" ? farbschemata.light : farbschemata.dark;
  return {
    colorScheme: thema,
    "--sh-bg": schema.bg,
    "--sh-flaeche": schema.flaeche,
    "--sh-flaeche-2": schema.flaeche2,
    "--sh-linie": schema.linie,
    "--sh-linie-stark": schema.linieStark,
    "--sh-text": schema.text,
    "--sh-text-weich": schema.textWeich,
    "--sh-text-gedaempft": schema.textGedaempft,
    "--sh-akzent": schema.akzent,
    "--sh-auf-akzent": schema.aufAkzent,
    "--sh-akzent-text": schema.akzentText,
    "--sh-akzent-flaeche": schema.akzentFlaeche,
    "--sh-warn": schema.warn,
    "--sh-warn-flaeche": schema.warnFlaeche,
    "--sh-warn-linie": schema.warnLinie,
    "--sh-krit": schema.krit,
    "--sh-krit-flaeche": schema.kritFlaeche,
    "--sh-krit-linie": schema.kritLinie,
    "--sh-info": schema.info,
    "--sh-info-flaeche": schema.infoFlaeche,
    "--sh-gold": schema.gold,
    "--sh-gold-flaeche": schema.goldFlaeche,
  } as CSSProperties;
}
