import { useLocalStorage } from "@mantine/hooks";
import { useEffect } from "react";

/** Wie breit die Seite den Bildschirm nutzt. Einstellung je Gerät, bleibt gespeichert. */
export type Seitenbreite = "voll" | "zentriert";

const SCHLUESSEL = "schiesshub.seitenbreite";

export function useSeitenbreite(): [Seitenbreite, (breite: Seitenbreite) => void] {
  const [breite, setBreite] = useLocalStorage<Seitenbreite>({
    key: SCHLUESSEL,
    defaultValue: "voll",
    getInitialValueInEffect: false,
  });

  useEffect(() => {
    document.documentElement.dataset.breite = breite;
  }, [breite]);

  return [breite, setBreite];
}
