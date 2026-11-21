import { ActionIcon } from "@mantine/core";
import { ArrowDown, ArrowUp } from "lucide-react";
import s from "./Reihenfolge.module.css";

/** Verschiebt den Eintrag an `index` um eine Stelle; außerhalb der Liste bleibt alles, wie es ist. */
export function verschiebe<T>(liste: readonly T[], index: number, richtung: -1 | 1): T[] {
  const ziel = index + richtung;
  if (index < 0 || index >= liste.length || ziel < 0 || ziel >= liste.length) return [...liste];
  const neu = [...liste];
  [neu[index], neu[ziel]] = [neu[ziel] as T, neu[index] as T];
  return neu;
}

interface ReihenfolgeKnoepfeProps {
  index: number;
  anzahl: number;
  /** Beschriftungen für Screenreader, z. B. „Stand 1 nach oben“ */
  hoch: string;
  runter: string;
  gesperrt?: boolean;
  onVerschieben: (richtung: -1 | 1) => void;
}

/** Zwei Knöpfe zum Umsortieren einer Liste; ohne Ziehen, damit es auf Touch zuverlässig geht. */
export function ReihenfolgeKnoepfe({
  index,
  anzahl,
  hoch,
  runter,
  gesperrt,
  onVerschieben,
}: ReihenfolgeKnoepfeProps) {
  return (
    <span className={s.knoepfe}>
      <ActionIcon
        variant="subtle"
        color="gray"
        size={40}
        aria-label={hoch}
        title={hoch}
        disabled={gesperrt || index === 0}
        onClick={() => onVerschieben(-1)}
      >
        <ArrowUp aria-hidden />
      </ActionIcon>
      <ActionIcon
        variant="subtle"
        color="gray"
        size={40}
        aria-label={runter}
        title={runter}
        disabled={gesperrt || index >= anzahl - 1}
        onClick={() => onVerschieben(1)}
      >
        <ArrowDown aria-hidden />
      </ActionIcon>
    </span>
  );
}
