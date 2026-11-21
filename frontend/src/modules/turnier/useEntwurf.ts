import { useState } from "react";

function gleich(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * Lokaler Entwurf eines Formulars über Serverdaten. Kommen neue Daten vom Server (Ereignis,
 * anderes Gerät) und ist nichts geändert, folgt der Entwurf; sonst bleiben die Eingaben stehen.
 */
export function useEntwurf<T>(quelle: T) {
  const [basis, setBasis] = useState(quelle);
  const [werte, setWerte] = useState(quelle);
  const geaendert = !gleich(werte, basis);

  if (!gleich(quelle, basis)) {
    setBasis(quelle);
    if (!geaendert) setWerte(quelle);
  }

  return {
    werte,
    setWerte,
    geaendert,
    /** Server-Stand, gegen den verglichen wird */
    basis,
    verwerfen: () => setWerte(basis),
  };
}
