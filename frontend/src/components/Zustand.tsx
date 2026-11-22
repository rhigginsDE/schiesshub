import { Button } from "@mantine/core";
import { type LucideIcon, RefreshCw, SearchX, ServerCrash, Unplug } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ApiFehler } from "../api/client";
import s from "./Zustand.module.css";

interface LeerzustandProps {
  icon: LucideIcon;
  titel: string;
  text: string;
  /** Aktionen, z. B. ein Button */
  children?: ReactNode;
  /** Ohne eigenen Rahmen, z. B. in einer Fläche mit Rahmen. Direkt in `.panel` geschieht das von selbst. */
  ohneRahmen?: boolean;
}

/** Nichts anzuzeigen: sagt, warum, und bietet wenn möglich den nächsten Schritt an. */
export function Leerzustand({ icon: Icon, titel, text, children, ohneRahmen }: LeerzustandProps) {
  return (
    <div className={ohneRahmen ? `${s.zustand} ${s.ohneRahmen}` : s.zustand}>
      <Icon className={s.symbol} aria-hidden />
      <strong className={s.titel}>{titel}</strong>
      <p className={s.text}>{text}</p>
      {children && <div className={s.aktionen}>{children}</div>}
    </div>
  );
}

interface FehlerzustandProps {
  fehler: unknown;
  /** Lädt die Daten erneut */
  onErneut?: () => void;
  /** Ersetzt Titel und Text für eine Fehlerart, z. B. ein genauerer Text bei „nicht gefunden“ */
  eigene?: Partial<Record<ApiFehler["art"], { titel: string; text: string }>>;
  children?: ReactNode;
}

/** Laden fehlgeschlagen: sagt, was los ist und was zu tun ist. */
export function Fehlerzustand({ fehler, onErneut, eigene, children }: FehlerzustandProps) {
  const { t } = useTranslation();
  const art = fehler instanceof ApiFehler ? fehler.art : "unbekannt";
  const eigener = art === "unbekannt" ? undefined : eigene?.[art];
  const Icon = art === "netzwerk" ? Unplug : art === "nicht_gefunden" ? SearchX : ServerCrash;
  const technisch =
    fehler instanceof ApiFehler
      ? [fehler.status, fehler.detail, fehler.pfad].filter(Boolean).join(" · ")
      : fehler instanceof Error
        ? fehler.message
        : "";

  return (
    <div className={`${s.zustand} ${s.fehler}`} role="alert">
      <Icon className={s.symbol} aria-hidden />
      <strong className={s.titel}>{eigener?.titel ?? t(`fehler.${art}.titel`)}</strong>
      <p className={s.text}>{eigener?.text ?? t(`fehler.${art}.text`)}</p>
      {technisch && (
        <p className={s.technisch}>
          {t("fehler.technisch")}: <span className="num">{technisch}</span>
        </p>
      )}
      {(onErneut || children) && (
        <div className={s.aktionen}>
          {onErneut && art !== "nicht_gefunden" && (
            <Button variant="default" leftSection={<RefreshCw aria-hidden />} onClick={onErneut}>
              {t("aktion.erneut_versuchen")}
            </Button>
          )}
          {children}
        </div>
      )}
    </div>
  );
}
