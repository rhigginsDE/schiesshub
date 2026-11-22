import { Button, Modal } from "@mantine/core";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import s from "./Bestaetigung.module.css";

interface BestaetigungProps {
  offen: boolean;
  titel: string;
  /** Was passiert, in ein bis zwei Sätzen */
  text: ReactNode;
  /** Beschriftung des Bestätigen-Knopfs */
  bestaetigen: string;
  /** Beschriftung des Abbrechen-Knopfs */
  abbrechen: string;
  /** `gefahr`: roter Knopf, z. B. für Löschen */
  ton?: "normal" | "gefahr";
  laedt?: boolean;
  /** Bestätigen noch nicht möglich, z. B. solange ein Pflichtfeld leer ist */
  gesperrt?: boolean;
  /** Fehlertext der Aktion; erscheint im Dialog */
  fehler?: string;
  onSchliessen: () => void;
  onBestaetigen: () => void;
  /** Zusätzliche Eingaben, z. B. ein Grund */
  children?: ReactNode;
}

/**
 * Rückfrage vor einer folgenreichen Aktion. Schließt nicht von selbst; das macht der Aufrufer.
 * Beim Öffnen steht der Fokus auf „Abbrechen“, nicht auf dem ersten Eingabefeld.
 */
export function Bestaetigung({
  offen,
  titel,
  text,
  bestaetigen,
  abbrechen,
  ton = "normal",
  laedt,
  gesperrt,
  fehler,
  onSchliessen,
  onBestaetigen,
  children,
}: BestaetigungProps) {
  const { t } = useTranslation();
  return (
    <Modal
      opened={offen}
      onClose={onSchliessen}
      title={titel}
      centered
      size="md"
      closeButtonProps={{ "aria-label": t("shell:dialog.schliessen") }}
    >
      <div className={s.inhalt}>
        <div className={s.text}>{text}</div>
        {children}
        {fehler && (
          <p className={s.fehler} role="alert">
            {fehler}
          </p>
        )}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "flex-end" }}>
          {/* Fokus beim Öffnen auf dem sicheren Knopf: Enter löst nichts Folgenreiches aus. */}
          <Button variant="default" onClick={onSchliessen} disabled={laedt} data-autofocus>
            {abbrechen}
          </Button>
          <Button
            color={ton === "gefahr" ? "red" : undefined}
            loading={laedt}
            disabled={gesperrt}
            onClick={onBestaetigen}
          >
            {bestaetigen}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
