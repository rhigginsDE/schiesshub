import { Button, SegmentedControl, Select, Skeleton } from "@mantine/core";
import { useLocalStorage } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, LayoutGrid, MapPin } from "lucide-react";
import { useTranslation } from "react-i18next";
import { MitTurnier, TurnierWechsel } from "../../components/TurnierWahl";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { uebersichtAbfrage } from "../turnier/abfragen";
import type { Turnier, TurnierUebersicht } from "../turnier/typen";
import { bestimmeStand, type StandWahl } from "./logik";
import type { StandSuche } from "./pfade";
import { StandAblauf } from "./StandAblauf";
import { Startliste } from "./Startliste";
import s from "./stand.module.css";

/** Gerätespeicher: je Turnier die ID des gewählten Stands. */
export const STAND_SPEICHER = "schiesshub.stand";

interface StandSeiteProps {
  suche: StandSuche;
  onSuche: (suche: StandSuche) => void;
}

/** Ablaufsteuerung am Stand: Bahnen, Reihenfolge, Durchgänge und die Startliste. */
export function StandSeite({ suche, onSuche }: StandSeiteProps) {
  const { t } = useTranslation("stand");
  return (
    <MitTurnier
      hinweis={t("turnier_hinweis")}
      kopf={
        <header className={`panel ${s.kopf}`}>
          <Titel />
        </header>
      }
    >
      {({ turnier, wechseln }) => (
        <StandMitTurnier turnier={turnier} onWechseln={wechseln} suche={suche} onSuche={onSuche} />
      )}
    </MitTurnier>
  );
}

function Titel() {
  const { t } = useTranslation("stand");
  return (
    <div className={s.titel}>
      <span className={s.symbol}>
        <LayoutGrid aria-hidden />
      </span>
      <h1 className="h-display">{t("titel")}</h1>
    </div>
  );
}

interface StandMitTurnierProps extends StandSeiteProps {
  turnier: Turnier;
  onWechseln: () => void;
}

function StandMitTurnier({ turnier, onWechseln, suche, onSuche }: StandMitTurnierProps) {
  const { t } = useTranslation("stand");
  const uebersicht = useQuery(uebersichtAbfrage(turnier.id));
  const [wahl, setWahl] = useLocalStorage<StandWahl>({
    key: STAND_SPEICHER,
    defaultValue: {},
    getInitialValueInEffect: false,
  });
  const staende = uebersicht.data?.ranges ?? [];
  const standId = bestimmeStand(staende, wahl, turnier.id);
  const waehlen = (id: string) => setWahl((alt) => ({ ...(alt ?? {}), [turnier.id]: id }));
  const startliste = suche.ansicht === "startliste";

  return (
    <div className={s.seite}>
      <header className={`panel ${s.kopf}`}>
        <div className={s.kopfZeile}>
          <Titel />
          <TurnierWechsel turnier={turnier} onWechseln={onWechseln} />
        </div>
        {!startliste && <p className={s.anleitung}>{t("anleitung")}</p>}
        <div className={s.kopfZeile}>
          <SegmentedControl
            size="md"
            aria-label={t("ansicht.beschriftung")}
            value={startliste ? "startliste" : "bahnen"}
            onChange={(wert) =>
              onSuche(wert === "startliste" ? { ...suche, ansicht: "startliste" } : {})
            }
            data={[
              { value: "bahnen", label: t("ansicht.bahnen") },
              { value: "startliste", label: t("ansicht.startliste") },
            ]}
          />
          {!startliste && staende.length > 1 && standId && (
            <Select
              size="md"
              className={s.standSelect}
              aria-label={t("stand_wahl.beschriftung")}
              leftSection={<MapPin aria-hidden />}
              allowDeselect={false}
              value={standId}
              onChange={(wert) => wert && waehlen(wert)}
              data={staende.map((stand) => ({ value: stand.id, label: stand.name }))}
            />
          )}
        </div>
      </header>

      {uebersicht.isPending ? (
        <Skeleton height={240} radius="md" />
      ) : uebersicht.isError ? (
        <div className="panel">
          <Fehlerzustand fehler={uebersicht.error} onErneut={() => void uebersicht.refetch()} />
        </div>
      ) : startliste ? (
        <Startliste uebersicht={uebersicht.data} suche={suche} onSuche={onSuche} />
      ) : standId ? (
        <StandAblauf key={standId} uebersicht={uebersicht.data} standId={standId} />
      ) : (
        <StandAuswahl uebersicht={uebersicht.data} onWahl={waehlen} />
      )}
    </div>
  );
}

function StandAuswahl({
  uebersicht,
  onWahl,
}: {
  uebersicht: TurnierUebersicht;
  onWahl: (id: string) => void;
}) {
  const { t } = useTranslation("stand");
  if (uebersicht.ranges.length === 0) {
    return (
      <div className="panel">
        <Leerzustand
          icon={MapPin}
          titel={t("stand_wahl.leer_titel")}
          text={t("stand_wahl.leer_text")}
        >
          <Button
            renderRoot={(props) => (
              <Link {...props} to={`/turnier/${uebersicht.id}`} search={{ bereich: "staende" }} />
            )}
            variant="default"
          >
            {t("stand_wahl.leer_link")}
          </Button>
        </Leerzustand>
      </div>
    );
  }
  return (
    <section className={`panel ${s.standAuswahl}`} aria-labelledby="stand-wahl-titel">
      <h2 className="h-section" id="stand-wahl-titel">
        {t("stand_wahl.titel")}
      </h2>
      <p className="gedaempft">{t("stand_wahl.text")}</p>
      <ul className={s.standListe}>
        {uebersicht.ranges.map((stand) => (
          <li key={stand.id}>
            <button type="button" className={s.standKnopf} onClick={() => onWahl(stand.id)}>
              <MapPin aria-hidden />
              <span>
                <strong>{stand.name}</strong>
                <span className="gedaempft">
                  {t("stand_wahl.bahnen", { count: stand.lane_count })}
                </span>
              </span>
              <ArrowRight aria-hidden className={s.pfeil} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
