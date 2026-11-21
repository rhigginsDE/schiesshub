import { useCallback, useEffect, useRef } from "react";

const RAND_PX = 32;

/**
 * Entscheidet, ob ein Element beim Scrollen haften darf (position: sticky), ohne dass Inhalt
 * unerreichbar wird: Passt es in das Fenster, bekommt es `data-haftet="ja"`, sonst `"nein"`.
 *
 * Ein haftendes Element, das höher als das Fenster ist, bräuchte einen eigenen Scrollbalken.
 * Den vermeiden wir: Jede Seite hat genau einen vertikalen Scroll. Rückgabe ist ein
 * Callback-Ref, damit es auch für später eingehängte Elemente funktioniert.
 */
export function useHaftetWennPasst<T extends HTMLElement>(): (element: T | null) => void {
  const element = useRef<T | null>(null);
  const beobachter = useRef<ResizeObserver | null>(null);

  const messen = useCallback(() => {
    const aktuell = element.current;
    if (!aktuell) return;
    const passt = aktuell.offsetHeight <= window.innerHeight - RAND_PX;
    aktuell.dataset.haftet = passt ? "ja" : "nein";
  }, []);

  useEffect(() => {
    window.addEventListener("resize", messen);
    return () => window.removeEventListener("resize", messen);
  }, [messen]);

  return useCallback(
    (neu: T | null) => {
      beobachter.current?.disconnect();
      beobachter.current = null;
      element.current = neu;
      if (!neu) return;
      messen();
      if (typeof ResizeObserver === "undefined") return;
      beobachter.current = new ResizeObserver(messen);
      beobachter.current.observe(neu);
    },
    [messen],
  );
}
