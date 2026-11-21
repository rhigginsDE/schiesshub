import { createTheme, type MantineColorsTuple } from "@mantine/core";
import { marke, radius, schriften } from "./tokens";

const gruen: MantineColorsTuple = [
  "#F1FAE6",
  "#DFF3C8",
  "#C4E89C",
  "#A9DC6F",
  marke.gruenHell,
  "#7CC62B",
  marke.gruen,
  "#5A9F1D",
  "#4A8417",
  marke.gruenText,
];

// Mantine liest daraus Text (0–2), Rahmen (4), Hover (5), Flächen (6) und Seitenhintergrund (7).
const nacht: MantineColorsTuple = [
  marke.weiss,
  "#C9D2DB",
  "#9AA8B6",
  "#7A8997",
  "#3B4D61",
  marke.linie,
  marke.nacht2,
  marke.nacht,
  "#080E14",
  "#05090D",
];

const ohneSchatten = { xs: "none", sm: "none", md: "none", lg: "none", xl: "none" };

export const theme = createTheme({
  colors: { gruen, dark: nacht },
  primaryColor: "gruen",
  primaryShade: 6,
  // Grüne Flächen bekommen dunkle Schrift (Primär-Button).
  autoContrast: true,
  luminanceThreshold: 0.3,
  black: marke.nacht,
  white: "#FFFFFF",
  fontFamily: schriften.text,
  fontFamilyMonospace: schriften.mono,
  headings: { fontFamily: schriften.display, fontWeight: "700" },
  radius: {
    xs: "4px",
    sm: `${radius.s}px`,
    md: `${radius.m}px`,
    lg: `${radius.l}px`,
    xl: "24px",
  },
  defaultRadius: "md",
  shadows: ohneSchatten,
  cursorType: "pointer",
  components: {
    Tooltip: { defaultProps: { withArrow: true, openDelay: 300 } },
  },
});

/** Unter diesem Schlüssel merkt sich der Browser die Wahl hell/dunkel (siehe auch index.html). */
export const FARBSCHEMA_SCHLUESSEL = "schiesshub-farbschema";
