import { useTranslation } from "react-i18next";
import { Kachel, KachelRaster } from "../components/Kachel";
import { useStationen } from "./modul";
import s from "./Startseite.module.css";

/** Stationsauswahl: eine große Kachel je Station, gebaut aus der Modul-Liste. */
export function Startseite() {
  const { t } = useTranslation();
  const stationen = useStationen();

  return (
    <>
      <div className={s.kopf}>
        <h1 className="h-display">{t("shell:start.ueberschrift")}</h1>
        <p className="gedaempft">{t("shell:start.einleitung")}</p>
      </div>
      <KachelRaster gross>
        {stationen.map((modul) => (
          <Kachel
            key={modul.id}
            gross
            pfad={modul.navigation.pfad}
            icon={modul.navigation.icon}
            titel={t(`${modul.namensraum}:titel`)}
            text={t(`${modul.namensraum}:zweck`)}
          />
        ))}
      </KachelRaster>
    </>
  );
}
