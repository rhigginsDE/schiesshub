/** Kontrastberechnung nach WCAG 2.x, zum Prüfen der Theme-Farben in Tests. */

type Rgba = [r: number, g: number, b: number, a: number];

export function parseFarbe(farbe: string): Rgba {
  const hex = /^#([0-9a-f]{6})$/i.exec(farbe.trim());
  if (hex?.[1]) {
    const n = Number.parseInt(hex[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1];
  }
  const rgba = /^rgba?\(([^)]+)\)$/i.exec(farbe.trim());
  if (rgba?.[1]) {
    const [r = 0, g = 0, b = 0, a = 1] = rgba[1].split(",").map((teil) => Number(teil.trim()));
    return [r, g, b, a];
  }
  throw new Error(`Unbekanntes Farbformat: ${farbe}`);
}

/** Legt eine (teil)transparente Farbe über einen deckenden Untergrund. */
export function mischen(farbe: string, untergrund: string): string {
  const [r, g, b, a] = parseFarbe(farbe);
  const [ur, ug, ub] = parseFarbe(untergrund);
  const kanal = (vorn: number, hinten: number) => Math.round(vorn * a + hinten * (1 - a));
  return `rgb(${kanal(r, ur)}, ${kanal(g, ug)}, ${kanal(b, ub)})`;
}

function leuchtdichte(farbe: string): number {
  const [r, g, b] = parseFarbe(farbe);
  const linear = (wert: number) => {
    const s = wert / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

/** Kontrastverhältnis zweier deckender Farben (1 bis 21). */
export function kontrast(vordergrund: string, hintergrund: string): number {
  const a = leuchtdichte(vordergrund);
  const b = leuchtdichte(hintergrund);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
