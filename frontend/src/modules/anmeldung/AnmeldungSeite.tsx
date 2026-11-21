import { Hammer, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBereiche } from "../../app/modul";
import { Chip } from "../../components/Chip";
import { Kachel, KachelRaster } from "../../components/Kachel";
import s from "./AnmeldungSeite.module.css";

interface AnmeldungSeiteProps {
  station: string;
  icon: LucideIcon;
}

/** Station Anmeldung: Bereiche, die Module hier angemeldet haben; Starts buchen folgt noch. */
export function AnmeldungSeite({ station, icon: Icon }: AnmeldungSeiteProps) {
  const { t } = useTranslation();
  const bereiche = useBereiche(station);

  return (
    <div className={s.seite}>
      <section className={`panel ${s.kopf}`}>
        <div className={s.titel}>
          <span className={s.symbol}>
            <Icon aria-hidden />
          </span>
          <h1 className="h-display">{t("anmeldung:titel")}</h1>
        </div>
        <p className={s.zweck}>{t("anmeldung:zweck")}</p>
        <p className={s.hinweis}>
          <Chip ton="warn" icon={Hammer}>
            {t("in_arbeit.chip")}
          </Chip>
          <span className="gedaempft">{t("anmeldung:noch_nicht")}</span>
        </p>
      </section>

      {bereiche.length > 0 && (
        <section className={s.bereiche} aria-labelledby="anmeldung-bereiche">
          <h2 className="h-label" id="anmeldung-bereiche">
            {t("anmeldung:bereiche")}
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
    </div>
  );
}
