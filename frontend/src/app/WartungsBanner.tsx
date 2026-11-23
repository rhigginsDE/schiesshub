import { Loader } from "@mantine/core";
import { useTranslation } from "react-i18next";
import s from "./WartungsBanner.module.css";
import { useWartung } from "./wartung";

/**
 * Ruhiger Hinweis auf jedem Gerät, solange eine Sicherung wiederhergestellt wird. Ersetzt die
 * Fehlermeldungen, die Eingaben in dieser Zeit sonst auslösen würden: Es ist nichts kaputt, es
 * dauert nur einen Moment.
 */
export function WartungsBanner() {
  const { t } = useTranslation("shell");
  const wartung = useWartung();
  if (!wartung.active) return null;
  return (
    <div className={s.banner} role="status" aria-live="polite">
      <Loader size="sm" color="var(--sh-info)" className={s.symbol} aria-hidden />
      <div className={s.text}>
        <strong className={s.titel}>{t("wartung.titel")}</strong>
        <span>{wartung.exclusive ? t("wartung.text_umschalten") : t("wartung.text")}</span>
      </div>
    </div>
  );
}
