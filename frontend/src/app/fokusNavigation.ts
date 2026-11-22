import { useEffect, useRef } from "react";

/** ID des `main`-Elements der Shell; Ziel des Sprunglinks. */
export const INHALT_ID = "inhalt";

/** Setzt den Fokus auf die Überschrift der Seite (h1), sonst auf `main`. */
export function springeZumInhalt(): void {
  const inhalt = document.getElementById(INHALT_ID);
  if (!inhalt) return;
  const ueberschrift = inhalt.querySelector<HTMLElement>("h1");
  const ziel = ueberschrift ?? inhalt;
  if (!ziel.hasAttribute("tabindex")) ziel.setAttribute("tabindex", "-1");
  ziel.focus();
}

/**
 * Nach einem Seitenwechsel über Kopfzeile oder Menü steht der Fokus sonst noch dort; Screenreader
 * sagen nichts an. Dann wandert er auf die Überschrift der neuen Seite. Liegt der Fokus schon im
 * Inhalt (z. B. Unterreiter, Suchfeld mit Autofokus), bleibt er dort.
 */
export function useFokusNachSeitenwechsel(pfad: string): void {
  const vorher = useRef(pfad);
  useEffect(() => {
    if (vorher.current === pfad) return;
    vorher.current = pfad;
    const bild = requestAnimationFrame(() => {
      const inhalt = document.getElementById(INHALT_ID);
      const aktiv = document.activeElement;
      if (!inhalt) return;
      if (aktiv && aktiv !== document.body && inhalt.contains(aktiv)) return;
      springeZumInhalt();
    });
    return () => cancelAnimationFrame(bild);
  }, [pfad]);
}
