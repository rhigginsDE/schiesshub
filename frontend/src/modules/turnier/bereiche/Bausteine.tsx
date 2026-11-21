import { Button } from "@mantine/core";
import { Check, Save, TriangleAlert, Undo2 } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import s from "../turnier.module.css";

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

/** Fuß eines Formulars: Zustand, Verwerfen und Speichern (Submit des umgebenden Formulars). */
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
    <div className={s.speicherleiste}>
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
