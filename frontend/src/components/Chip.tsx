import type { LucideIcon } from "lucide-react";
import type { ComponentPropsWithRef, ReactNode } from "react";
import s from "./Chip.module.css";

/** `gold` ist Platz 1 und Auszeichnungen vorbehalten. */
export type ChipTon = "neutral" | "gruen" | "warn" | "krit" | "info" | "gold";

interface ChipProps extends ComponentPropsWithRef<"span"> {
  ton?: ChipTon;
  icon?: LucideIcon;
  /** Statuspunkt vor dem Text */
  punkt?: boolean;
  children: ReactNode;
}

/** Kleine Statusmarke. Farbe trägt nie allein die Aussage; der Text sagt, was gemeint ist. */
export function Chip({
  ton = "neutral",
  icon: Icon,
  punkt,
  children,
  className,
  ...rest
}: ChipProps) {
  return (
    <span className={[s.chip, s[ton], className].filter(Boolean).join(" ")} {...rest}>
      {punkt && <span className={s.punkt} aria-hidden />}
      {Icon && <Icon aria-hidden />}
      {children}
    </span>
  );
}
