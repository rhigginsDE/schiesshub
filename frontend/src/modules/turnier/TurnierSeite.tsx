import { Hammer, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBereiche } from "../../app/modul";
import { Chip } from "../../components/Chip";
import { Kachel, KachelRaster } from "../../components/Kachel";
import s from "./TurnierSeite.module.css";

interface TurnierSeiteProps {
  station: string;
  icon: LucideIcon;
}

/** Übersicht der Station Turnier: zeigt die Bereiche, die Module hier angemeldet haben. */
export function TurnierSeite({ station, icon: Icon }: TurnierSeiteProps) {
  const { t } = useTranslation();
  const bereiche = useBereiche(station);

  return (
    <>
      <section className={`panel ${s.kopf}`}>
        <div className={s.titel}>
          <span className={s.symbol}>
            <Icon aria-hidden />
          </span>
          <h1 className="h-display">{t("turnier:titel")}</h1>
        </div>
        <p className={s.zweck}>{t("turnier:zweck")}</p>
        <p className={s.hinweis}>
          <Chip ton="warn" icon={Hammer}>
            {t("in_arbeit.chip")}
          </Chip>
          <span className="gedaempft">{t("turnier:in_arbeit")}</span>
        </p>
      </section>

      {bereiche.length > 0 && (
        <section className={s.bereiche} aria-labelledby="turnier-bereiche">
          <h2 className="h-label" id="turnier-bereiche">
            {t("turnier:bereiche")}
          </h2>
          <KachelRaster>
            {bereiche.map((modul) => (
              <Kachel
                key={modul.id}
                pfad={modul.navigation.pfad}
                icon={modul.navigation.icon}
                titel={t(`${modul.namensraum}:titel`)}
                text={t(`${modul.namensraum}:zweck`)}
              />
            ))}
          </KachelRaster>
        </section>
      )}
    </>
  );
}
