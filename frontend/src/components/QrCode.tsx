import { useMemo } from "react";
import { encode } from "uqr";
import { hell, marke } from "../theme/tokens";

interface QrCodeProps {
  /** Inhalt, z. B. eine Adresse */
  text: string;
  /** Kantenlänge in Pixeln */
  groesse?: number;
  /** Beschreibung für Screenreader */
  beschriftung: string;
}

/**
 * QR-Code als SVG, lokal erzeugt (Bibliothek `uqr`, ohne Netz). Immer dunkel auf hell,
 * auch im dunklen Farbschema, weil nicht jede Kamera invertierte Codes liest.
 */
export function QrCode({ text, groesse = 220, beschriftung }: QrCodeProps) {
  const { pfad, kante } = useMemo(() => {
    const qr = encode(text, { ecc: "M", border: 2 });
    const teile: string[] = [];
    qr.data.forEach((zeile, y) => {
      zeile.forEach((dunkel, x) => {
        if (dunkel) teile.push(`M${x} ${y}h1v1h-1z`);
      });
    });
    return { pfad: teile.join(""), kante: qr.size };
  }, [text]);

  return (
    <svg
      role="img"
      aria-label={beschriftung}
      width={groesse}
      height={groesse}
      viewBox={`0 0 ${kante} ${kante}`}
      shapeRendering="crispEdges"
      style={{ display: "block", borderRadius: 8, maxWidth: "100%", height: "auto" }}
    >
      <rect width={kante} height={kante} fill={hell.flaeche} />
      <path d={pfad} fill={marke.nacht} />
    </svg>
  );
}
