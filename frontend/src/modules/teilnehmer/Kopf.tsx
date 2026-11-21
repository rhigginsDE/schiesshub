import { Link } from "@tanstack/react-router";
import { ChevronRight, FileSpreadsheet, Shield, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useModule } from "../../app/modul";
import { IMPORT_PFAD, TEILNEHMER_PFAD, VEREINE_PFAD } from "./pfade";
import s from "./teilnehmer.module.css";

export type Reiter = "personen" | "vereine" | "import";

const REITER = [
  { id: "personen", pfad: TEILNEHMER_PFAD, icon: Users },
  { id: "vereine", pfad: VEREINE_PFAD, icon: Shield },
  { id: "import", pfad: IMPORT_PFAD, icon: FileSpreadsheet },
] as const;

/** Kopf aller Teilnehmer-Ansichten: Pfad zur Station, Überschrift, Reiter. */
export function Kopf({ aktiv }: { aktiv: Reiter }) {
  const { t } = useTranslation();
  const module = useModule();
  const navigation = module.find((modul) => modul.id === "teilnehmer")?.navigation;
  const stationId = navigation?.art === "bereich" ? navigation.station : undefined;
  const station = module.find((modul) => modul.id === stationId);

  return (
    <header className={s.kopf}>
      {station && (
        <nav className={s.pfad} aria-label={t("shell:navigation.stationen")}>
          <Link to={station.navigation.pfad}>{t(`${station.namensraum}:titel`)}</Link>
          <ChevronRight aria-hidden />
        </nav>
      )}
      <div className={s.kopfzeile}>
        <h1 className="h-display">{t("teilnehmer:titel")}</h1>
        <nav className={s.reiter} aria-label={t("teilnehmer:reiter.beschriftung")}>
          {REITER.map(({ id, pfad, icon: Icon }) => (
            <Link
              key={id}
              to={pfad}
              className={s.reiterLink}
              activeOptions={{ exact: true, includeSearch: false }}
              data-aktiv={id === aktiv || undefined}
            >
              <Icon aria-hidden />
              {t(`teilnehmer:reiter.${id}`)}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
