import { ActionIcon } from "@mantine/core";
import { Minus, Plus } from "lucide-react";
import type { KeyboardEvent } from "react";
import s from "./Stepper.module.css";

export interface StepperProps {
  wert: number;
  min?: number;
  max: number;
  onWert: (wert: number) => void;
  /** Beschriftung der Gruppe für Screenreader, z. B. „Starts in 1001“ */
  beschriftung: string;
  weniger: string;
  mehr: string;
  gesperrt?: boolean;
}

/**
 * Anzahl mit − und + (große Ziele für Touch). Tastatur: Fokus auf der Zahl, dann ↑/↓ oder + und −,
 * Ziffern setzen den Wert direkt; Pos1/Ende springen auf Minimum/Maximum.
 */
export function Stepper({
  wert,
  min = 0,
  max,
  onWert,
  beschriftung,
  weniger,
  mehr,
  gesperrt,
}: StepperProps) {
  const setze = (neu: number) => {
    const begrenzt = Math.min(max, Math.max(min, neu));
    if (begrenzt !== wert) onWert(begrenzt);
  };

  const beiTaste = (ereignis: KeyboardEvent<HTMLElement>) => {
    if (gesperrt) return;
    const { key } = ereignis;
    if (key === "ArrowUp" || key === "+" || key === "ArrowRight") setze(wert + 1);
    else if (key === "ArrowDown" || key === "-" || key === "ArrowLeft") setze(wert - 1);
    else if (key === "Home") setze(min);
    else if (key === "End") setze(max);
    else if (/^\d$/.test(key)) setze(Number(key));
    else return;
    ereignis.preventDefault();
  };

  return (
    <div className={s.stepper} data-gesperrt={gesperrt || undefined}>
      <ActionIcon
        variant="default"
        size={44}
        aria-label={weniger}
        title={weniger}
        disabled={gesperrt || wert <= min}
        onClick={() => setze(wert - 1)}
        tabIndex={-1}
      >
        <Minus aria-hidden />
      </ActionIcon>
      <span
        className={`num ${s.wert}`}
        role="spinbutton"
        tabIndex={gesperrt ? -1 : 0}
        aria-label={beschriftung}
        aria-valuenow={wert}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-disabled={gesperrt || undefined}
        onKeyDown={beiTaste}
      >
        {wert}
      </span>
      <ActionIcon
        variant="default"
        size={44}
        aria-label={mehr}
        title={mehr}
        disabled={gesperrt || wert >= max}
        onClick={() => setze(wert + 1)}
        tabIndex={-1}
      >
        <Plus aria-hidden />
      </ActionIcon>
    </div>
  );
}
