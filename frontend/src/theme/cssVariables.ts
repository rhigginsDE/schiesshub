import type { CSSVariablesResolver } from "@mantine/core";
import { type Farbschema, farbschemata, radius, schriften, schriftgroesse } from "./tokens";

function variablen(schema: Farbschema): Record<string, string> {
  return {
    "--sh-bg": schema.bg,
    "--sh-flaeche": schema.flaeche,
    "--sh-flaeche-2": schema.flaeche2,
    "--sh-linie": schema.linie,
    "--sh-linie-stark": schema.linieStark,
    "--sh-text": schema.text,
    "--sh-text-weich": schema.textWeich,
    "--sh-text-gedaempft": schema.textGedaempft,
    "--sh-akzent": schema.akzent,
    "--sh-akzent-hover": schema.akzentHover,
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

    // Mantine-Grundfarben auf die Markenflächen legen
    "--mantine-color-body": schema.bg,
    "--mantine-color-text": schema.text,
    "--mantine-color-dimmed": schema.textGedaempft,
    "--mantine-color-placeholder": schema.textGedaempft,
    "--mantine-color-anchor": schema.akzentText,
    "--mantine-color-error": schema.krit,
    "--mantine-color-default": schema.flaeche,
    "--mantine-color-default-hover": schema.flaeche2,
    "--mantine-color-default-color": schema.text,
    "--mantine-color-default-border": schema.linieStark,
    "--mantine-color-gruen-filled": schema.akzent,
    "--mantine-color-gruen-filled-hover": schema.akzentHover,
    "--mantine-primary-color-filled": schema.akzent,
    "--mantine-primary-color-filled-hover": schema.akzentHover,
    "--mantine-primary-color-contrast": schema.aufAkzent,
  };
}

/** Schreibt die Farbrollen als CSS-Variablen `--sh-*` für hell und dunkel. */
export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {
    "--sh-radius-s": `${radius.s}px`,
    "--sh-radius-m": `${radius.m}px`,
    "--sh-radius-l": `${radius.l}px`,
    "--sh-font-display": schriften.display,
    "--sh-font-text": schriften.text,
    "--sh-font-mono": schriften.mono,
    "--sh-fz-text": `${schriftgroesse.text}px`,
    "--sh-fz-klein": `${schriftgroesse.klein}px`,
    "--sh-fz-label": `${schriftgroesse.label}px`,
  },
  light: variablen(farbschemata.light),
  dark: variablen(farbschemata.dark),
});
