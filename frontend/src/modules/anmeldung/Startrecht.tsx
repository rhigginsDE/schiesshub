import { Info, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import s from "./AnmeldungSeite.module.css";
import type { StartrechtMeldung } from "./api";
import { istWarnung, startrechtListe } from "./logik";

interface StartrechtHinweiseProps {
  meldungen: readonly StartrechtMeldung[];
  /** Vor dem Buchen: bei Warnungen der Satz, dass der Start trotzdem buchbar ist */
  vorBuchung?: boolean;
  className?: string;
}

/**
 * Warnungen und Hinweise des Servers zum Startrecht (Tabelle des Verbands zur Deutschen
 * Meisterschaft). Text und Fundstelle kommen fertig vom Server; hier steht nur der Rahmen.
 * Warnung: Warnfarbe, Dreieck und das Wort „Warnung“. Hinweis: ruhig, Info-Symbol. Nichts davon
 * sperrt das Buchen. Ohne Meldung erscheint nichts.
 */
export function StartrechtHinweise({ meldungen, vorBuchung, className }: StartrechtHinweiseProps) {
  const { t } = useTranslation("anmeldung");
  const liste = startrechtListe(meldungen);
  if (liste.length === 0) return null;
  return (
    <ul
      className={[s.startrecht, className].filter(Boolean).join(" ")}
      aria-label={t("startrecht.titel")}
    >
      {liste.map((meldung) => {
        const warnung = istWarnung(meldung);
        const Zeichen = warnung ? TriangleAlert : Info;
        return (
          <li
            key={`${meldung.code}|${meldung.message_de}`}
            className={s.startrechtEintrag}
            data-ton={warnung ? "warn" : "info"}
          >
            <Zeichen aria-hidden className={s.startrechtSymbol} />
            <div className={s.startrechtText}>
              <strong>{t(warnung ? "startrecht.warnung" : "startrecht.hinweis")}</strong>
              <span>{meldung.message_de}</span>
              {meldung.source && (
                <small>{t("startrecht.fundstelle", { quelle: meldung.source })}</small>
              )}
              {warnung && vorBuchung && <small>{t("startrecht.bleibt_buchbar")}</small>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
