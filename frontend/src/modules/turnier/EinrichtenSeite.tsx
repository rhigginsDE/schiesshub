import { Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  CircleAlert,
  ClipboardList,
  FileSignature,
  FileText,
  LandPlot,
  type LucideIcon,
  Settings2,
  Target,
  Users,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../app/berechtigungen";
import { Fehlerzustand } from "../../components/Zustand";
import { uebersichtAbfrage } from "./abfragen";
import { Ausschreibung } from "./ausschreibung/Ausschreibung";
import { ausschreibungAbfrage } from "./ausschreibung/abfragen";
import { Einstellungen } from "./bereiche/Einstellungen";
import { Klassen } from "./bereiche/Klassen";
import { Staende } from "./bereiche/Staende";
import { Stammdaten } from "./bereiche/Stammdaten";
import { Zusammenfassung } from "./bereiche/Zusammenfassung";
import { zeitraum } from "./klartext";
import { type EinrichtenSuche, TURNIER_PFAD } from "./pfade";
import { StatusAktionen, StatusChip } from "./Status";
import s from "./turnier.module.css";
import { BEREICHE, type Bereich, offenePunkte, unvollstaendigeBereiche } from "./vollstaendigkeit";
import { Wettbewerbe } from "./wettbewerbe/Wettbewerbe";

const SYMBOL: Record<Bereich, LucideIcon> = {
  stammdaten: FileText,
  staende: LandPlot,
  klassen: Users,
  wettbewerbe: Target,
  ausschreibung: FileSignature,
  einstellungen: Settings2,
  zusammenfassung: ClipboardList,
};

interface EinrichtenSeiteProps {
  turnierId: string;
  suche: EinrichtenSuche;
  onSuche: (suche: EinrichtenSuche) => void;
}

/** Turnier einrichten: links die Bereiche, rechts der gewählte Bereich (Fenster-Layout). */
export function EinrichtenSeite({ turnierId, suche, onSuche }: EinrichtenSeiteProps) {
  const { t, i18n } = useTranslation("turnier");
  const abfrage = useQuery(uebersichtAbfrage(turnierId));
  const darfBearbeiten = useDarf("tournament.edit");
  // Kennt das Backend die Ausschreibung nicht (404), fehlt der Bereich.
  const ausschreibung = useQuery(ausschreibungAbfrage(turnierId));
  const mitAusschreibung = ausschreibung.data !== null;
  const bereich: Bereich = suche.bereich ?? "stammdaten";

  if (abfrage.isPending) {
    return (
      <div className={s.einrichten} aria-busy="true">
        <Skeleton height={72} radius="lg" />
        <div className={s.einrichtenSpalten}>
          <Skeleton height={320} radius="lg" />
          <Skeleton height={480} radius="lg" />
        </div>
      </div>
    );
  }
  if (abfrage.isError) {
    return (
      <div className="panel">
        <Fehlerzustand
          fehler={abfrage.error}
          onErneut={() => void abfrage.refetch()}
          eigene={{
            nicht_gefunden: {
              titel: t("einrichten.nicht_gefunden_titel"),
              text: t("einrichten.nicht_gefunden_text"),
            },
          }}
        >
          <Link to={TURNIER_PFAD} className={s.textLink}>
            {t("einrichten.zur_liste")}
          </Link>
        </Fehlerzustand>
      </div>
    );
  }

  const turnier = abfrage.data;
  // Abgeschlossen oder ohne Recht: nur ansehen. Der Server prüft trotzdem selbst.
  const gesperrt = turnier.status === "closed" || !darfBearbeiten;
  const punkte = offenePunkte(turnier);
  const unvollstaendig = unvollstaendigeBereiche(punkte);
  const wechsel = (neu: Bereich) => onSuche({ bereich: neu });

  return (
    <div className={s.einrichten} data-layout="fenster" data-bereich={bereich}>
      <header className={s.einrichtenKopf}>
        <div className={s.einrichtenTitel}>
          <Link to={TURNIER_PFAD} className={s.pfad}>
            {t("titel")}
          </Link>
          <div className={s.kopfZeile}>
            <h1 className="h-display">{turnier.name}</h1>
            <StatusChip status={turnier.status} />
          </div>
          <p className="gedaempft">
            <span className="num">{zeitraum(turnier, i18n.language)}</span>
            {turnier.organizer && ` · ${turnier.organizer}`}
          </p>
        </div>
        {bereich !== "zusammenfassung" && (
          <StatusAktionen
            turnier={turnier}
            darstellung="knoepfe"
            hinweiseVorStart={punkte.map((p) => t(`offen.${p.schluessel}`, p.werte ?? {}))}
          />
        )}
      </header>

      {turnier.status === "closed" && (
        <p className={s.warnBanner} role="status">
          <CircleAlert aria-hidden />
          {t("einrichten.abgeschlossen")}
        </p>
      )}

      <div className={s.einrichtenSpalten}>
        <nav className={s.bereichNav} aria-label={t("einrichten.bereiche")}>
          <ul>
            {BEREICHE.filter((b) => b !== "ausschreibung" || mitAusschreibung).map((eintrag) => {
              const Icon = SYMBOL[eintrag];
              const offen = unvollstaendig.has(eintrag);
              return (
                <li key={eintrag}>
                  <button
                    type="button"
                    aria-current={eintrag === bereich ? "page" : undefined}
                    onClick={() => wechsel(eintrag)}
                  >
                    <Icon aria-hidden />
                    <span className={s.navText}>{t(`bereich.${eintrag}.titel`)}</span>
                    {offen && (
                      <span className={s.unvollstaendig} title={t("einrichten.unvollstaendig")}>
                        <span className={s.punkt} aria-hidden />
                        <span className={s.navHinweis}>{t("einrichten.unvollstaendig")}</span>
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div
          className={s.bereichInhalt}
          data-geteilt={
            bereich === "wettbewerbe" ? "zwei" : bereich === "ausschreibung" ? "voll" : undefined
          }
        >
          {bereich === "stammdaten" && <Stammdaten turnier={turnier} gesperrt={gesperrt} />}
          {bereich === "staende" && <Staende turnier={turnier} gesperrt={gesperrt} />}
          {bereich === "klassen" && <Klassen turnier={turnier} gesperrt={gesperrt} />}
          {bereich === "wettbewerbe" && (
            <Wettbewerbe
              turnier={turnier}
              gesperrt={gesperrt}
              offen={suche.wettbewerb}
              onOffen={(id) => onSuche({ bereich, wettbewerb: id })}
            />
          )}
          {bereich === "ausschreibung" && <Ausschreibung turnier={turnier} gesperrt={gesperrt} />}
          {bereich === "einstellungen" && <Einstellungen turnier={turnier} gesperrt={gesperrt} />}
          {bereich === "zusammenfassung" && (
            <Zusammenfassung turnier={turnier} punkte={punkte} onBereich={wechsel} />
          )}
        </div>
      </div>
    </div>
  );
}
