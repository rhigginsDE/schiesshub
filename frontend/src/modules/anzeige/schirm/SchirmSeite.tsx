import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Schirm } from "./Schirm";
import s from "./schirmSeite.module.css";
import type { FeedQuelle } from "./useFeed";

const ZEIGER_AUS_MS = 3000;
const DOPPELTIPP_MS = 350;

/**
 * Für die Dauer des Bildschirms: App ausblenden (eigene Ebene statt App-Leiste) und die Seite nicht
 * scrollen lassen. Wie die Druckansicht der Ausschreibung, nur ohne Werkzeugleiste.
 */
function useSchirmRahmen() {
  const { t } = useTranslation("anzeige");
  useLayoutEffect(() => {
    const wurzel = document.documentElement;
    wurzel.setAttribute("data-anzeige-schirm", "");
    const titel = document.title;
    document.title = t("schirm.seitentitel");
    return () => {
      wurzel.removeAttribute("data-anzeige-schirm");
      document.title = titel;
    };
  }, [t]);
}

/** Bildschirm wach halten, solange die Seite sichtbar ist; ohne Wake Lock geht es eben ohne. */
function useWachHalten() {
  useEffect(() => {
    const api = (navigator as Navigator & { wakeLock?: WakeLock }).wakeLock;
    if (!api) return;
    let sperre: WakeLockSentinel | null = null;
    let beendet = false;
    const anfordern = async () => {
      if (beendet || document.visibilityState !== "visible") return;
      try {
        sperre = await api.request("screen");
      } catch {
        // Verweigert (z. B. Energiesparmodus): ignorieren.
      }
    };
    const sichtbar = () => void anfordern();
    void anfordern();
    document.addEventListener("visibilitychange", sichtbar);
    return () => {
      beendet = true;
      document.removeEventListener("visibilitychange", sichtbar);
      void sperre?.release().catch(() => {});
    };
  }, []);
}

function vollbildUmschalten() {
  try {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    else void document.documentElement.requestFullscreen?.().catch(() => {});
  } catch {
    // Vollbild nicht erlaubt: nichts tun.
  }
}

/** Taste F oder Doppeltipp schaltet Vollbild; der Mauszeiger verschwindet nach kurzer Ruhe. */
function useBedienung(): boolean {
  const [zeigerAus, setZeigerAus] = useState(false);
  const letzterTipp = useRef(0);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const bewegt = () => {
      setZeigerAus(false);
      clearTimeout(timer);
      timer = setTimeout(() => setZeigerAus(true), ZEIGER_AUS_MS);
    };
    const taste = (ereignis: KeyboardEvent) => {
      if (ereignis.key === "f" || ereignis.key === "F") vollbildUmschalten();
    };
    const tipp = () => {
      const jetzt = Date.now();
      if (jetzt - letzterTipp.current < DOPPELTIPP_MS) {
        letzterTipp.current = 0;
        vollbildUmschalten();
      } else {
        letzterTipp.current = jetzt;
      }
    };
    bewegt();
    window.addEventListener("mousemove", bewegt);
    window.addEventListener("keydown", taste);
    window.addEventListener("dblclick", vollbildUmschalten);
    window.addEventListener("touchend", tipp);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("mousemove", bewegt);
      window.removeEventListener("keydown", taste);
      window.removeEventListener("dblclick", vollbildUmschalten);
      window.removeEventListener("touchend", tipp);
    };
  }, []);

  return zeigerAus;
}

/** Route ohne App-Leiste: der Bildschirm füllt das Fenster genau. */
export function SchirmSeite({ quelle }: { quelle: FeedQuelle }) {
  useSchirmRahmen();
  useWachHalten();
  const zeigerAus = useBedienung();
  const schluessel = quelle.art === "geraet" ? "geraet" : quelle.id;

  return createPortal(
    <div className={s.vollbild} data-zeiger={zeigerAus ? "aus" : undefined}>
      <Schirm key={schluessel} quelle={quelle} />
    </div>,
    document.body,
  );
}
