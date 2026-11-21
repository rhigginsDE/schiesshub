import { Hammer, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Chip } from "./Chip";
import s from "./InArbeit.module.css";

interface InArbeitProps {
  /** Namensraum des Moduls; liefert `titel` und `zweck` */
  namensraum: string;
  icon: LucideIcon;
}

/** Schlichte Seite für Stationen, die noch nicht gebaut sind. Zeigt nur den Zweck, keine Attrappen. */
export function InArbeit({ namensraum, icon: Icon }: InArbeitProps) {
  const { t } = useTranslation();
  return (
    <section className={`panel ${s.seite}`}>
      <div className={s.kopf}>
        <span className={s.symbol}>
          <Icon aria-hidden />
        </span>
        <h1 className="h-display">{t(`${namensraum}:titel`)}</h1>
        <Chip ton="warn" icon={Hammer}>
          {t("in_arbeit.chip")}
        </Chip>
      </div>
      <p className={s.zweck}>{t(`${namensraum}:zweck`)}</p>
      <p className="gedaempft">{t("in_arbeit.text")}</p>
    </section>
  );
}
