import { Modal, type ModalProps } from "@mantine/core";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { TIPPZIEL_PX } from "../theme/theme";

/**
 * Gibt den Tastaturfokus an das Element zurück, das beim Öffnen fokussiert war (meist der Knopf,
 * der den Dialog geöffnet hat). Greift beim Schließen (`offen` wird `false`) und beim Entfernen der
 * Komponente, also auch bei `{offen && <MeinDialog />}`. Steht der Fokus inzwischen woanders
 * sinnvoll (nicht auf `body`), bleibt er dort.
 */
export function useFokusZurueck(offen = true): void {
  const ausloeser = useRef<HTMLElement | null>(null);
  const warOffen = useRef(false);
  // Beim ersten Rendern des offenen Dialogs steht der Fokus noch auf dem Auslöser.
  if (offen && !warOffen.current && typeof document !== "undefined") {
    const aktiv = document.activeElement;
    ausloeser.current = aktiv instanceof HTMLElement && aktiv !== document.body ? aktiv : null;
  }
  warOffen.current = offen;

  useEffect(() => {
    if (!offen) return;
    return () => {
      const ziel = ausloeser.current;
      if (!ziel) return;
      // Nach dem Abbau des Dialogs (Mantine gibt den Fokus ggf. selbst zurück) prüfen.
      window.setTimeout(() => {
        const jetzt = document.activeElement;
        const verloren = !jetzt || jetzt === document.body || !jetzt.isConnected;
        if (verloren && ziel.isConnected) ziel.focus({ preventScroll: true });
      }, 0);
    };
  }, [offen]);
}

export type DialogProps = Omit<ModalProps, "opened"> & {
  /** Standard `true`: für Dialoge, die nur gerendert werden, solange sie offen sind */
  opened?: boolean;
};

/**
 * Mantine-Modal mit den Regeln der App: der Schließen-Knopf hat einen Namen und 44 px, und nach dem
 * Schließen (Esc, Abbrechen, ×, Erfolg) steht der Fokus wieder am Auslöser.
 */
export function Dialog({ opened = true, closeButtonProps, ...props }: DialogProps) {
  const { t } = useTranslation();
  useFokusZurueck(opened);
  return (
    <Modal
      opened={opened}
      closeButtonProps={{
        size: TIPPZIEL_PX,
        "aria-label": t("shell:dialog.schliessen"),
        ...closeButtonProps,
      }}
      {...props}
    />
  );
}
