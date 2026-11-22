import { Button, Skeleton } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, MonitorPlay, ShieldAlert } from "lucide-react";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../../app/berechtigungen";
import { Bestaetigung } from "../../../components/Bestaetigung";
import { ExportKnoepfe } from "../../../components/ExportKnoepfe";
import { FehlerHinweis } from "../../../components/FehlerHinweis";
import { sortiereTurniere } from "../../../components/useAktivesTurnier";
import { Fehlerzustand, Leerzustand } from "../../../components/Zustand";
import { turnierListeAbfrage, uebersichtAbfrage } from "../../turnier/abfragen";
import type { Turnier } from "../../turnier/typen";
import { anzeigeFuerTurnierAnlegen, anzeigenAbfrage, anzeigeSchluessel, schirmPfad } from "../api";
import { AnzeigeListe, KeineAnzeige } from "./AnzeigeListe";
import { Bearbeiten } from "./Bearbeiten";
import s from "./verwaltung.module.css";

interface VerwaltungSeiteProps {
  auswahl?: string;
  /** Einstieg für ein Turnier: dessen Anzeige öffnen oder anbieten, eine einzurichten */
  turnierId?: string;
  onAuswahl: (id: string) => void;
}

/** Station Anzeige: Liste der Anzeigen, Einstellungen, Live-Vorschau (Fenster-Layout). */
export function VerwaltungSeite({ auswahl, turnierId, onAuswahl }: VerwaltungSeiteProps) {
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
  // Für ein Turnier: die Anzeige, die fest auf dieses Turnier steht; gibt es keine, wird keine
  // fremde geöffnet, sondern angeboten, eine einzurichten.
  const fuerTurnier = turnierId ? turniere.find((x) => x.id === turnierId) : undefined;
  const passende = fuerTurnier
    ? anzeigen.find((anzeige) => anzeige.tournament_id === fuerTurnier.id)
    : undefined;
  const einrichten = auswahl === undefined && fuerTurnier !== undefined && !passende;
  const gewaehlt = einrichten
    ? undefined
    : (anzeigen.find((anzeige) => anzeige.id === auswahl) ?? passende ?? anzeigen[0]);
  const waehlen = (id: string) => {
    if (id === gewaehlt?.id) return;
    if (geaendert) setWechselZu(id);
    else onAuswahl(id);
  };

  if (einrichten && fuerTurnier) {
    return (
      <div className={s.seite}>
        <div className={s.einrichtenSpalten}>
          {anzeigen.length > 0 && (
            <AnzeigeListe
              anzeigen={anzeigen}
              aktivId={null}
              turniere={turniere}
              onWahl={onAuswahl}
            />
          )}
          <TurnierEinrichten turnier={fuerTurnier} sort={anzeigen.length} onFertig={onAuswahl} />
        </div>
      </div>
    );
  }

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

/**
 * Einstieg „Ergebnisse zeigen“ für ein Turnier ohne eigene Anzeige: eine Anzeige dafür einrichten
 * (Live-Wertung, Startliste, Siegerliste) oder die Siegerliste drucken.
 */
function TurnierEinrichten({
  turnier,
  sort,
  onFertig,
}: {
  turnier: Turnier;
  sort: number;
  onFertig: (id: string) => void;
}) {
  const { t } = useTranslation("anzeige");
  const queryClient = useQueryClient();
  const uebersicht = useQuery(uebersichtAbfrage(turnier.id));
  const anlegen = useMutation({
    mutationFn: () => anzeigeFuerTurnierAnlegen(turnier.name, turnier.id, sort),
    onSuccess: (neu) => {
      void queryClient.invalidateQueries({ queryKey: anzeigeSchluessel.alle });
      onFertig(neu.id);
    },
  });
  return (
    <section className={`panel ${s.einrichten}`} aria-labelledby="einrichten-titel">
      <h2 className="h-section" id="einrichten-titel">
        {t("einrichten.titel", { name: turnier.name })}
      </h2>
      <p className={s.hilfe}>{t("einrichten.text")}</p>
      <div className={s.einrichtenAktionen}>
        <Button
          size="md"
          rightSection={<ArrowRight aria-hidden />}
          loading={anlegen.isPending}
          onClick={() => anlegen.mutate()}
        >
          {t("einrichten.knopf", { name: turnier.name })}
        </Button>
        <ExportKnoepfe
          turnierId={turnier.id}
          uebersicht={uebersicht.data}
          knopfText={t("einrichten.drucken")}
          nur="winners"
        />
      </div>
      <FehlerHinweis fehler={anlegen.error} />
    </section>
  );
}
