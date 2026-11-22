import { Button } from "@mantine/core";
import { Check, ChevronRight, Save, TriangleAlert, Undo2 } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import a from "../aufgaben.module.css";
import s from "../turnier.module.css";

/** Hilfetexte unter dem Feld, damit nebeneinander stehende Felder auf einer Höhe bleiben. */
export const HILFE_UNTEN = ["label", "input", "description", "error"] as (
  | "label"
  | "input"
  | "description"
  | "error"
)[];

export function BereichKopf({
  titel,
  text,
  children,
}: {
  titel: string;
  text?: string;
  children?: ReactNode;
}) {
  return (
    <header className={s.bereichKopf}>
      <div>
        <h2 className="h-section">{titel}</h2>
        {text && <p>{text}</p>}
      </div>
      {children}
    </header>
  );
}

/**
 * Zugeklappter Abschnitt „Erweitert“ für Seltenes. Öffnet sich von selbst, wenn darin ein Fehler
 * steht, damit niemand einen unsichtbaren Fehler sucht.
 */
export function Erweitert({
  titel,
  text,
  fehler,
  children,
}: {
  titel: string;
  /** Was darin steht, z. B. „Währung, Erfassung, Einspruchsfrist“ */
  text?: string;
  fehler?: boolean;
  children: ReactNode;
}) {
  const [offen, setOffen] = useState(false);
  useEffect(() => {
    if (fehler) setOffen(true);
  }, [fehler]);
  return (
    <details className={a.erweitert} open={offen} onToggle={(e) => setOffen(e.currentTarget.open)}>
      <summary>
        <ChevronRight className={a.erweitertPfeil} aria-hidden />
        <span className={a.erweitertText}>
          <strong>{titel}</strong>
          {text && <span>{text}</span>}
        </span>
      </summary>
      <div className={a.erweitertInhalt}>{children}</div>
    </details>
  );
}

interface SpeicherleisteProps {
  geaendert: boolean;
  laedt: boolean;
  gespeichert: boolean;
  fehler?: string;
  gesperrt?: boolean;
  /** Text des Speichern-Knopfs, Standard „Speichern“ */
  knopf?: string;
  /** Grün nur, wenn dies die Hauptaktion der Ansicht ist */
  primaer?: boolean;
  onVerwerfen: () => void;
}

/**
 * Fuß eines Formulars: Zustand, Verwerfen und Speichern (Submit des umgebenden Formulars).
 * Mit Änderungen bleibt die Leiste am unteren Rand der Spalte stehen, damit „Speichern“ sichtbar ist.
 */
export function Speicherleiste({
  geaendert,
  laedt,
  gespeichert,
  fehler,
  gesperrt,
  knopf,
  primaer = true,
  onVerwerfen,
}: SpeicherleisteProps) {
  const { t } = useTranslation("turnier");
  return (
    <div className={s.speicherleiste} data-geaendert={geaendert || undefined}>
      <span className={s.speicherZustand} aria-live="polite">
        {fehler ? (
          <span className={s.fehlerText} role="alert">
            <TriangleAlert aria-hidden />
            {fehler}
          </span>
        ) : geaendert ? (
          t("speichern.ungespeichert")
        ) : gespeichert ? (
          <span className={s.okText}>
            <Check aria-hidden />
            {t("speichern.gespeichert")}
          </span>
        ) : null}
      </span>
      {geaendert && (
        <Button
          variant="default"
          size="md"
          leftSection={<Undo2 aria-hidden />}
          onClick={onVerwerfen}
        >
          {t("speichern.verwerfen")}
        </Button>
      )}
      <Button
        type="submit"
        size="md"
        variant={primaer ? "filled" : "default"}
        leftSection={<Save aria-hidden />}
        loading={laedt}
        disabled={!geaendert || gesperrt}
      >
        {knopf ?? t("speichern.knopf")}
      </Button>
    </div>
  );
}
