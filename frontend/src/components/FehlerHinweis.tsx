import { CircleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ApiFehler, serverMeldung } from "../api/client";
import s from "./FehlerHinweis.module.css";

/**
 * Text zu einem Fehler: die Meldung des Servers, wenn er eine in Klartext geliefert hat
 * (sie sagt meist genau, was zu tun ist), sonst ein allgemeiner Text zur Fehlerart.
 */
export function useFehlerText(): (fehler: unknown) => string {
  const { t, i18n } = useTranslation();
  return (fehler) => {
    const meldung = serverMeldung(fehler);
    if (meldung) return meldung;
    const art = fehler instanceof ApiFehler ? fehler.art : "unbekannt";
    if (i18n.exists(`shell:fehler.${art}`)) return t(`shell:fehler.${art}`);
    if (i18n.exists(`allgemein:fehler.${art}.text`)) return t(`allgemein:fehler.${art}.text`);
    return t("allgemein:fehler.unbekannt.text");
  };
}

interface FehlerHinweisProps {
  fehler: unknown;
  /** Eigener Text statt der Meldung des Servers */
  text?: string;
}

/** Fehler direkt an einem Formular oder einer Aktion. Nichts, solange `fehler` leer ist. */
export function FehlerHinweis({ fehler, text }: FehlerHinweisProps) {
  const fehlerText = useFehlerText();
  if (!fehler) return null;
  return (
    <p className={s.hinweis} role="alert">
      <CircleAlert aria-hidden />
      <span>{text ?? fehlerText(fehler)}</span>
    </p>
  );
}
