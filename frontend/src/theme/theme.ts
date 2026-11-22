import {
  ActionIcon,
  Button,
  createTheme,
  Input,
  type MantineColorsTuple,
  rem,
} from "@mantine/core";
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

/** Kleinste Trefferfläche für Finger (Markenhandbuch, WCAG 2.5.5). */
export const TIPPZIEL_PX = 44;
const tippziel = rem(TIPPZIEL_PX);

/**
 * Eingabefelder starten in Größe „md“: 16 px Schrift (kein Zoom auf dem iPhone) und 44 px Höhe.
 * Gilt für jedes Feld, das keine eigene Größe setzt.
 */
const FELDER = [
  "Input",
  "InputWrapper",
  "InputBase",
  "TextInput",
  "PasswordInput",
  "NumberInput",
  "Textarea",
  "Select",
  "MultiSelect",
  "Autocomplete",
  "TagsInput",
  "NativeSelect",
  "JsonInput",
] as const;
const felder = Object.fromEntries(FELDER.map((name) => [name, { defaultProps: { size: "md" } }]));

export const theme = createTheme({
  colors: { gruen, dark: nacht },
  primaryColor: "gruen",
  primaryShade: 6,
  // Grüne Flächen bekommen dunkle Schrift (Primär-Button).
  autoContrast: true,
  luminanceThreshold: 0.3,
  black: marke.nacht,
  white: "#FFFFFF",
  // Markenhandbuch: Text 16, klein 13; nichts Lesenswertes darunter.
  fontSizes: { xs: rem(13), sm: rem(15), md: rem(16), lg: rem(18), xl: rem(20) },
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
    ...felder,
    // „md“ ist bei Mantine 42 px hoch; für Finger auf 44 px angehoben.
    Input: Input.extend({
      defaultProps: { size: "md" },
      vars: (_theme, props) => ({
        wrapper: { "--input-height": props.size === "md" ? tippziel : undefined },
      }),
    }),
    Button: Button.extend({
      defaultProps: { size: "md" },
      vars: (_theme, props) => ({
        root: { "--button-height": props.size === "md" ? tippziel : undefined },
      }),
    }),
    // Ohne Größe oder mit einer Zahl unter 44 px wird ein Symbolknopf auf 44 px gebracht.
    ActionIcon: ActionIcon.extend({
      defaultProps: { size: TIPPZIEL_PX },
      vars: (_theme, props) => ({
        root: {
          "--ai-size":
            typeof props.size === "number" && props.size < TIPPZIEL_PX ? tippziel : undefined,
        },
      }),
    }),
    Tooltip: { defaultProps: { withArrow: true, openDelay: 300 } },
  },
});

/** Unter diesem Schlüssel merkt sich der Browser die Wahl hell/dunkel (siehe auch index.html). */
export const FARBSCHEMA_SCHLUESSEL = "schiesshub-farbschema";
