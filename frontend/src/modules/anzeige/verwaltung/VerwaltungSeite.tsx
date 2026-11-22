import { Button, Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { MonitorPlay, ShieldAlert } from "lucide-react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../../app/berechtigungen";
import { Bestaetigung } from "../../../components/Bestaetigung";
import { sortiereTurniere } from "../../../components/useAktivesTurnier";
import { Fehlerzustand, Leerzustand } from "../../../components/Zustand";
import { turnierListeAbfrage } from "../../turnier/abfragen";
import { anzeigenAbfrage, schirmPfad } from "../api";
import { AnzeigeListe, KeineAnzeige } from "./AnzeigeListe";
import { Bearbeiten } from "./Bearbeiten";
import s from "./verwaltung.module.css";

interface VerwaltungSeiteProps {
  auswahl?: string;
  onAuswahl: (id: string) => void;
}

/** Station Anzeige: Liste der Anzeigen, Einstellungen, Live-Vorschau (Fenster-Layout). */
export function VerwaltungSeite({ auswahl, onAuswahl }: VerwaltungSeiteProps) {
  const { t } = useTranslation("anzeige");
  const darf = useDarf("display.control");
  const liste = useQuery({ ...anzeigenAbfrage(), enabled: darf });
  const turnierListe = useQuery({ ...turnierListeAbfrage(), enabled: darf });
  const [geaendert, setGeaendert] = useState(false);
  const [wechselZu, setWechselZu] = useState<string | null>(null);
  const meldeGeaendert = useCallback((wert: boolean) => setGeaendert(wert), []);

  if (!darf) {
    return (
      <div className="panel">
        <Leerzustand icon={ShieldAlert} titel={t("ohne_recht.titel")} text={t("ohne_recht.text")}>
          <Button component={Link} to={schirmPfad()} leftSection={<MonitorPlay aria-hidden />}>
            {t("ohne_recht.schirm")}
          </Button>
        </Leerzustand>
      </div>
    );
  }

  if (liste.isPending) return <Skeleton height={320} radius="md" />;
  if (liste.isError) {
    return (
      <div className="panel">
        <Fehlerzustand fehler={liste.error} onErneut={() => void liste.refetch()} />
      </div>
    );
  }

  const anzeigen = liste.data;
  const turniere = sortiereTurniere(turnierListe.data ?? []);
  const gewaehlt = anzeigen.find((anzeige) => anzeige.id === auswahl) ?? anzeigen[0];
  const waehlen = (id: string) => {
    if (id === gewaehlt?.id) return;
    if (geaendert) setWechselZu(id);
    else onAuswahl(id);
  };

  if (!gewaehlt) {
    return (
      <div className="panel">
        <Leerzustand icon={MonitorPlay} titel={t("leer.titel")} text={t("leer.text")}>
          <KeineAnzeige onWahl={onAuswahl} />
        </Leerzustand>
      </div>
    );
  }

  return (
    <div className={s.seite} data-layout="fenster">
      <div className={s.spalten}>
        <AnzeigeListe
          anzeigen={anzeigen}
          aktivId={gewaehlt.id}
          turniere={turniere}
          onWahl={waehlen}
        />
        <Bearbeiten
          key={gewaehlt.id}
          anzeige={gewaehlt}
          anzeigen={anzeigen}
          turniere={turniere}
          onGeaendert={meldeGeaendert}
        />
      </div>
      <Bestaetigung
        offen={wechselZu !== null}
        titel={t("bearbeiten.verwerfen_titel")}
        text={t("bearbeiten.verwerfen_text")}
        bestaetigen={t("bearbeiten.verwerfen")}
        abbrechen={t("aktion.abbrechen")}
        ton="gefahr"
        onSchliessen={() => setWechselZu(null)}
        onBestaetigen={() => {
          if (wechselZu) onAuswahl(wechselZu);
          setGeaendert(false);
          setWechselZu(null);
        }}
      />
    </div>
  );
}
