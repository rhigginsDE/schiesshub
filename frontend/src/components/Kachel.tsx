import { Link } from "@tanstack/react-router";
import { ArrowRight, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import s from "./Kachel.module.css";

interface KachelProps {
  pfad: string;
  icon: LucideIcon;
  titel: string;
  text: string;
  /** Große Ausführung für die Stationsauswahl */
  gross?: boolean;
}

/** Große, antippbare Fläche, die zu einer Station oder einem Bereich führt. */
export function Kachel({ pfad, icon: Icon, titel, text, gross }: KachelProps) {
  return (
    <li>
      <Link to={pfad} className={[s.kachel, gross && s.gross].filter(Boolean).join(" ")}>
        <span className={s.symbol}>
          <Icon aria-hidden />
        </span>
        <span className={s.text}>
          <strong className="h-section">{titel}</strong>
          <span>{text}</span>
        </span>
        <ArrowRight className={s.pfeil} aria-hidden />
      </Link>
    </li>
  );
}

export function KachelRaster({ children, gross }: { children: ReactNode; gross?: boolean }) {
  return (
    <ul className={[s.raster, gross && s.rasterGross].filter(Boolean).join(" ")}>{children}</ul>
  );
}
