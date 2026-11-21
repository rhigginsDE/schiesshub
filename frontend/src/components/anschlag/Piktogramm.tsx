import type { ReactElement } from "react";
import s from "./Piktogramm.module.css";
import type { Haltung, Hand } from "./typen";

/**
 * Anschlag-Piktogramm: Körperhaltung als Silhouette, die Hand als rundes Abzeichen oben rechts.
 * Bewusst ohne Waffe. Farbe kommt aus `color`; die Fläche hinter dem Abzeichen aus `--pikto-grund`.
 */
export interface PiktogrammProps {
  haltung: Haltung;
  hand?: Hand | null;
  /** Zugänglicher Name; ohne ihn gilt das Piktogramm als Schmuck (Text steht daneben). */
  label?: string;
  className?: string;
}

const FIGUR: Record<Haltung, ReactElement> = {
  stehend: (
    <>
      <circle cx="10" cy="4.2" r="2.6" />
      <rect x="6.4" y="7.8" width="7.2" height="8.4" rx="3.6" />
      <rect x="6.9" y="13" width="2.7" height="9" rx="1.35" />
      <rect x="10.4" y="13" width="2.7" height="9" rx="1.35" />
    </>
  ),
  kniend: (
    <>
      <circle cx="10" cy="4.6" r="2.6" />
      <rect x="6.4" y="8.2" width="7.2" height="7.8" rx="3.6" />
      <path
        d="M11.6 14.6H16.6V20.2H18.4M8.4 14.8L8.6 20.2H3.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <rect x="1" y="21.8" width="22" height="1.4" rx="0.7" opacity="0.35" />
    </>
  ),
  liegend: (
    <>
      <circle cx="17.2" cy="12.4" r="2.6" />
      <rect x="2" y="13.4" width="13.4" height="4.6" rx="2.3" />
      <rect x="1" y="19.6" width="22" height="1.6" rx="0.8" opacity="0.35" />
    </>
  ),
};

/** Rechte Hand, Handfläche zum Betrachter. */
function HandForm() {
  return (
    <>
      <rect x="7" y="6" width="2.2" height="8" rx="1.1" />
      <rect x="9.6" y="4" width="2.2" height="10" rx="1.1" />
      <rect x="12.2" y="4.5" width="2.2" height="9.5" rx="1.1" />
      <rect x="14.8" y="6.5" width="2.2" height="7.5" rx="1.1" />
      <rect x="7" y="11" width="10" height="9" rx="4" />
      <rect x="15" y="10.5" width="2.4" height="6" rx="1.2" transform="rotate(35 16.2 13.5)" />
    </>
  );
}

const ABZEICHEN: Record<Hand, { stil: string | undefined; inhalt: ReactElement }> = {
  beidhaendig: {
    stil: s.voll,
    inhalt: (
      <>
        <g transform="matrix(-0.78 0 0 0.78 15.46 1.9)">
          <HandForm />
        </g>
        <g transform="matrix(0.78 0 0 0.78 6.54 1.9)">
          <HandForm />
        </g>
      </>
    ),
  },
  // Starke Hand: rechte Hand, gefülltes Abzeichen
  starke_hand: { stil: s.voll, inhalt: <HandForm /> },
  // Schwache Hand: linke (gespiegelte) Hand, Ring
  schwache_hand: {
    stil: s.ring,
    inhalt: (
      <g transform="matrix(-1 0 0 1 24 0)">
        <HandForm />
      </g>
    ),
  },
  // Eine Hand, frei wählbar: gestrichelter Ring
  einhaendig: { stil: s.gestrichelt, inhalt: <HandForm /> },
};

export function Piktogramm({ haltung, hand, label, className }: PiktogrammProps) {
  const abzeichen = hand ? ABZEICHEN[hand] : null;
  const klassen = [s.pikto, className].filter(Boolean).join(" ");
  const inhalt = (
    <>
      <svg viewBox="0 0 24 24" className={s.figur} fill="currentColor" aria-hidden="true">
        {FIGUR[haltung]}
      </svg>
      {abzeichen && (
        <span className={`${s.abzeichen} ${abzeichen.stil}`}>
          <svg
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
            className={hand === "beidhaendig" ? s.handBeide : s.hand}
          >
            {abzeichen.inhalt}
          </svg>
        </span>
      )}
    </>
  );
  return label ? (
    <span
      className={klassen}
      role="img"
      aria-label={label}
      data-haltung={haltung}
      data-hand={hand ?? undefined}
    >
      {inhalt}
    </span>
  ) : (
    <span
      className={klassen}
      aria-hidden="true"
      data-haltung={haltung}
      data-hand={hand ?? undefined}
    >
      {inhalt}
    </span>
  );
}
