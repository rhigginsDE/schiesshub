import { Button } from "@mantine/core";
import { useLocalStorage } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, CheckCheck, ListChecks, type LucideIcon, Target } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../app/berechtigungen";
import { useBereiche, useModule } from "../../app/modul";
import { ExportKnoepfe } from "../../components/ExportKnoepfe";
import { MitTurnier, TurnierWechsel } from "../../components/TurnierWahl";
import { Leerzustand } from "../../components/Zustand";
import { uebersichtAbfrage } from "../turnier/abfragen";
import type { Turnier, TurnierUebersicht } from "../turnier/typen";
import { erfassungStartlisteAbfrage, prueflisteAbfrage } from "./api";
import { bestimmeStand, istOffen, naechsterOffener, namenAus } from "./auswahl";
import s from "./erfassung.module.css";
import type { ErfassungSuche } from "./pfade";
import { Startauswahl } from "./Startauswahl";
import { Terminal } from "./Terminal";

/** Gerätespeicher: je Turnier die ID des Stands, an dem dieses Terminal erfasst. */
export const ERFASSUNG_STAND_SPEICHER = "schiesshub.erfassung.stand";

interface ErfassungSeiteProps {
  station: string;
  icon: LucideIcon;
  suche: ErfassungSuche;
  onSuche: (suche: ErfassungSuche) => void;
}

/** Station Erfassung: Startauswahl, Erfassungsfläche und Ziffernfeld; dazu die Bereiche der Station. */
export function ErfassungSeite({ station, icon, suche, onSuche }: ErfassungSeiteProps) {
  const { t } = useTranslation("erfassung");
  return (
    <MitTurnier
      hinweis={t("turnier_hinweis")}
      kopf={
        <header className={`panel ${s.kopf}`}>
          <Titel icon={icon} />
          <Bereiche station={station} />
        </header>
      }
    >
      {({ turnier, wechseln }) => (
        <Station
          station={station}
          icon={icon}
          turnier={turnier}
          onWechseln={wechseln}
          suche={suche}
          onSuche={onSuche}
        />
      )}
    </MitTurnier>
  );
}

function Titel({ icon: Icon }: { icon: LucideIcon }) {
  const { t } = useTranslation("erfassung");
  return (
    <div className={s.titel}>
      <span className={s.symbol}>
        <Icon aria-hidden />
      </span>
      <h1 className="h-display">{t("titel")}</h1>
    </div>
  );
}

/** Bereiche, die andere Module für diese Station angemeldet haben (z. B. „Stand“). */
function Bereiche({ station }: { station: string }) {
  const { t } = useTranslation("erfassung");
  const bereiche = useBereiche(station);
  if (bereiche.length === 0) return null;
  return (
    <nav className={s.bereiche} aria-label={t("bereiche")}>
      {bereiche.map((modul) => {
        const Icon = modul.navigation.icon;
        return (
          <Link
            key={modul.id}
            to={modul.navigation.pfad}
            className={s.bereich}
            title={t(`${modul.namensraum}:zweck`)}
          >
            <Icon aria-hidden />
            <span>{t(`${modul.namensraum}:titel`)}</span>
          </Link>
        );
      })}
    </nav>
  );
}

interface StationProps extends ErfassungSeiteProps {
  turnier: Turnier;
  onWechseln: () => void;
}

function Station({ station, icon, turnier, onWechseln, suche, onSuche }: StationProps) {
  const { t } = useTranslation("erfassung");
  const uebersicht = useQuery(uebersichtAbfrage(turnier.id));
  // Volle Namen liefert der Server in der Startliste mit, wenn die Person sie sehen darf.
  const volleNamen = useDarf(["start.call", "result.capture", "entry.read"]);
  const startliste = useQuery(erfassungStartlisteAbfrage(turnier.id, volleNamen));
  const pruefliste = useQuery(prueflisteAbfrage(turnier.id));
  const [wahl, setWahl] = useLocalStorage<Record<string, string>>({
    key: ERFASSUNG_STAND_SPEICHER,
    defaultValue: {},
    getInitialValueInEffect: false,
  });
  const [auswahlOffen, setAuswahlOffen] = useState(false);

  const staende = uebersicht.data?.ranges ?? [];
  const standId = bestimmeStand(staende, wahl, turnier.id);
  const stand = staende.find((r) => r.id === standId) ?? null;
  const starts = startliste.data ?? [];
  const namen = useMemo(() => namenAus(startliste.data), [startliste.data]);
  const kennziffern = useMemo(
    () =>
      new Map(
        (uebersicht.data?.competitions ?? []).map((w) => [w.id, w.catalog_code ?? null] as const),
      ),
    [uebersicht.data],
  );
  const startId = suche.start ?? null;
  // Alles erledigt und nichts zu prüfen: Abschluss statt „Start wählen“.
  const alleErledigt =
    startliste.isSuccess &&
    starts.length > 0 &&
    !starts.some(istOffen) &&
    (pruefliste.data?.length ?? 0) === 0;

  const oeffnen = (id: string) => {
    setAuswahlOffen(false);
    // Ein anderer Start beginnt mit der Erfassungsart seines Wettbewerbs; eine Umstellung gilt
    // nur für den Start, an dem sie gewählt wurde.
    onSuche(id === suche.start ? { start: id, art: suche.art } : { start: id });
  };
  // Vorschlag am Stand des gerade erfassten Starts (sonst am gewählten Stand).
  const vorschlag = (ohne: string | null) => {
    const standDesStarts = staende.find(
      (r) => r.id === starts.find((st) => st.start_id === ohne)?.range_id,
    );
    const ziel = standDesStarts ?? stand;
    return ziel ? naechsterOffener(starts, ziel.id, ziel.lane_count, ohne) : null;
  };

  return (
    <div
      className={s.seite}
      data-layout="fenster"
      data-start={startId ? "offen" : "zu"}
      data-auswahl={auswahlOffen ? "offen" : "zu"}
    >
      <header className={`panel ${s.kopf}`}>
        <Titel icon={icon} />
        <TurnierWechsel turnier={turnier} onWechseln={onWechseln} />
        {startId && (
          <Button
            className={s.auswahlKnopf}
            variant="default"
            leftSection={<ListChecks aria-hidden />}
            onClick={() => setAuswahlOffen((offen) => !offen)}
            aria-expanded={auswahlOffen}
          >
            {auswahlOffen ? t("auswahl.zurueck") : t("auswahl.oeffnen")}
          </Button>
        )}
        <Bereiche station={station} />
      </header>

      <div className={s.spalten}>
        <Startauswahl
          turnier={turnier}
          uebersicht={uebersicht}
          startliste={startliste}
          staende={staende}
          stand={stand}
          onStand={(id) => setWahl((alt) => ({ ...(alt ?? {}), [turnier.id]: id }))}
          namen={namen}
          kennziffern={kennziffern}
          pruefliste={pruefliste.data ?? []}
          alleErledigt={alleErledigt}
          offenId={startId}
          onWahl={oeffnen}
        />
        {startId ? (
          <Terminal
            key={startId}
            turnierId={turnier.id}
            startId={startId}
            art={suche.art ?? null}
            onArt={(art) => onSuche({ start: startId, art })}
            kennziffern={kennziffern}
            vorschlag={() => vorschlag(startId)}
            namen={namen}
            onOeffnen={oeffnen}
          />
        ) : alleErledigt ? (
          <AlleErfasst turnier={turnier} anzahl={starts.length} uebersicht={uebersicht.data} />
        ) : (
          <section className={`panel ${s.leer}`} aria-label={t("leer.titel")}>
            <Leerzustand icon={Target} titel={t("leer.titel")} text={t("leer.text")} />
          </section>
        )}
      </div>
    </div>
  );
}

/** Alle Starts erledigt: das sagen und den nächsten Schritt anbieten (Ergebnisse zeigen, drucken). */
function AlleErfasst({
  turnier,
  anzahl,
  uebersicht,
}: {
  turnier: Turnier;
  anzahl: number;
  uebersicht: TurnierUebersicht | undefined;
}) {
  const { t } = useTranslation("erfassung");
  const anzeige = useModule().some((modul) => modul.id === "anzeige");
  return (
    <section className={`panel ${s.leer}`} aria-labelledby="erf-fertig-titel">
      <div className={s.fertig} role="status">
        <span className={s.fertigSymbol}>
          <CheckCheck aria-hidden />
        </span>
        <h2 className="h-section" id="erf-fertig-titel">
          {t("fertig.titel", { count: anzahl })}
        </h2>
        <p className="gedaempft">{t("fertig.text")}</p>
        <div className={s.fertigAktionen}>
          {anzeige && (
            <Button
              rightSection={<ArrowRight aria-hidden />}
              renderRoot={(props) => (
                <Link {...props} to="/anzeige" search={{ turnier: turnier.id }} />
              )}
            >
              {t("fertig.zeigen")}
            </Button>
          )}
          <ExportKnoepfe
            turnierId={turnier.id}
            uebersicht={uebersicht}
            knopfText={t("fertig.drucken")}
            nur="winners"
          />
        </div>
      </div>
    </section>
  );
}
