import { Delete } from "lucide-react";
import { useTranslation } from "react-i18next";
import s from "./Ziffernfeld.module.css";

interface ZiffernfeldProps {
  wert: string;
  onChange: (wert: string) => void;
  /** Ziffer 0 rechts unten: Bestätigen (z. B. „Anmelden“) */
  onFertig?: () => void;
  fertigText?: string;
  maxLaenge?: number;
  deaktiviert?: boolean;
  /** Beschriftung für Screenreader und Tastatur-Feld */
  beschriftung: string;
  /** Eingabe als Punkte statt Ziffern zeigen (PIN) */
  verdeckt?: boolean;
  /** id des Feldes, z. B. für eine Fehlermeldung über aria-describedby */
  id?: string;
  beschreibungId?: string;
}

const TASTEN = ["1", "2", "3", "4", "5", "6", "7", "8", "9"] as const;

/**
 * Großes Ziffernfeld für Touch-Geräte (PIN, Zahlen). Eine Hardware-Tastatur funktioniert auch:
 * Das Feld darüber nimmt Ziffern, Rücktaste und Enter an, öffnet aber keine Bildschirmtastatur.
 */
export function Ziffernfeld({
  wert,
  onChange,
  onFertig,
  fertigText,
  maxLaenge = 12,
  deaktiviert,
  beschriftung,
  verdeckt = true,
  id,
  beschreibungId,
}: ZiffernfeldProps) {
  const { t } = useTranslation("shell");
  const anhaengen = (ziffer: string) => {
    if (wert.length < maxLaenge) onChange(wert + ziffer);
  };

  return (
    <div className={s.feld}>
      <input
        id={id}
        className={`${s.anzeige} num`}
        type={verdeckt ? "password" : "text"}
        inputMode="none"
        autoComplete="off"
        value={wert}
        disabled={deaktiviert}
        aria-label={beschriftung}
        aria-describedby={beschreibungId}
        maxLength={maxLaenge}
        onChange={(ereignis) => onChange(ereignis.currentTarget.value.replace(/\D/g, ""))}
        onKeyDown={(ereignis) => {
          if (ereignis.key === "Enter" && onFertig) {
            ereignis.preventDefault();
            onFertig();
          }
        }}
      />
      <div className={s.tasten}>
        {TASTEN.map((ziffer) => (
          <button
            key={ziffer}
            type="button"
            className={`${s.taste} num`}
            disabled={deaktiviert}
            onClick={() => anhaengen(ziffer)}
          >
            {ziffer}
          </button>
        ))}
        <button
          type="button"
          className={`${s.taste} ${s.neben}`}
          disabled={deaktiviert || wert.length === 0}
          aria-label={t("ziffernfeld.loeschen")}
          onClick={() => onChange(wert.slice(0, -1))}
        >
          <Delete aria-hidden />
        </button>
        <button
          type="button"
          className={`${s.taste} num`}
          disabled={deaktiviert}
          onClick={() => anhaengen("0")}
        >
          0
        </button>
        {onFertig ? (
          <button
            type="button"
            className={`${s.taste} ${s.fertig}`}
            disabled={deaktiviert || wert.length === 0}
            onClick={onFertig}
          >
            {fertigText ?? t("ziffernfeld.ok")}
          </button>
        ) : (
          <span />
        )}
      </div>
    </div>
  );
}
