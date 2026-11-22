import { Button, Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, PlayCircle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { Fehlerzustand } from "../../components/Zustand";
import { formatUhrzeit } from "../../lib/format";
import {
  type Abbruchgrund,
  type Durchgang,
  durchgaengeAbfrage,
  type StationStart,
  startlisteAbfrage,
  useDurchgangAufrufen,
  useDurchgangLoeschen,
  useNaechsteAufrufen,
  usePlatzEntfernen,
  useStartAbbrechen,
  useStartAufrufen,
  useStartVerschieben,
  useStartZurueckstellen,
  type Verschiebung,
  warteschlangeAbfrage,
} from "../anmeldung/api";
import type { TurnierUebersicht } from "../turnier/typen";
import { useFehlerMelden } from "./aktionen";
import { BahnKachel } from "./Bahnen";
import { DurchgangDialog, PlatzDialog, SerieDialog } from "./Dialoge";
import {
  besetzteAnmeldungen,
  ersterAufrufbarer,
  freieBahnen,
  hauptAktion,
  naechsterWartenderDurchgang,
  sortiereDurchgaenge,
} from "./logik";
import s from "./stand.module.css";
import { Warteliste } from "./Warteliste";
import { Zeitplan } from "./Zeitplan";

interface StandAblaufProps {
  uebersicht: TurnierUebersicht;
  standId: string;
}

/** Ablauf an einem Stand: Bahnkacheln oben, darunter Reihenfolge und Durchgänge. */
export function StandAblauf({ uebersicht, standId }: StandAblaufProps) {
  const { t, i18n } = useTranslation("stand");
  const turnierId = uebersicht.id;
  const fehlerMelden = useFehlerMelden();
  const fehlerText = useFehlerText();

  const stand = uebersicht.ranges.find((r) => r.id === standId);
  const wettbewerbe = uebersicht.competitions.filter((w) => w.range_id === standId);
  const mitReihenfolge = wettbewerbe.filter((w) => w.planning === "queue");
  const mitZeitplan = wettbewerbe.filter((w) => w.planning === "schedule");
  const planungVon = new Map(wettbewerbe.map((w) => [w.id, w.planning]));
  const zeitplanIds = new Set(mitZeitplan.map((w) => w.id));

  const warteschlange = useQuery(warteschlangeAbfrage(turnierId, standId));
  const durchgaenge = useQuery(durchgaengeAbfrage(turnierId, standId));
  const startliste = useQuery(startlisteAbfrage(turnierId, { stand: standId }));

  const naechste = useNaechsteAufrufen(turnierId);
  const aufrufen = useStartAufrufen(turnierId);
  const zurueck = useStartZurueckstellen(turnierId);
  const verschieben = useStartVerschieben(turnierId);
  const abbrechen = useStartAbbrechen(turnierId);
  const durchgangAufrufen = useDurchgangAufrufen(turnierId, standId);
  const durchgangLoeschen = useDurchgangLoeschen(turnierId, standId);
  const herausnehmen = usePlatzEntfernen(turnierId);

  const [abbruch, setAbbruch] = useState<{ start: StationStart; grund: Abbruchgrund } | null>(null);
  const [loeschen, setLoeschen] = useState<Durchgang | null>(null);
  const [serieOffen, setSerieOffen] = useState(false);
  const [aendern, setAendern] = useState<Durchgang | null>(null);
  const [platz, setPlatz] = useState<StationStart | null>(null);

  if (warteschlange.isPending || durchgaenge.isPending || startliste.isPending) {
    return <Skeleton height={320} radius="md" />;
  }
  const ladeFehler = warteschlange.error ?? durchgaenge.error ?? startliste.error;
  if (ladeFehler || !warteschlange.data || !durchgaenge.data || !startliste.data) {
    return (
      <div className="panel">
        <Fehlerzustand
          fehler={ladeFehler}
          onErneut={() => {
            void warteschlange.refetch();
            void durchgaenge.refetch();
            void startliste.refetch();
          }}
        />
      </div>
    );
  }

  const bahnen = warteschlange.data.lanes;
  const wartende = warteschlange.data.waiting;
  const frei = freieBahnen(bahnen);
  const besetzt = besetzteAnmeldungen(bahnen);
  const zeitplanStarts = startliste.data.filter((st) => zeitplanIds.has(st.competition_id));
  const naechsterDurchgang = naechsterWartenderDurchgang(durchgaenge.data, zeitplanStarts);
  const haupt = hauptAktion(mitReihenfolge.length > 0, naechsterDurchgang);
  const beschaeftigt =
    naechste.isPending ||
    aufrufen.isPending ||
    zurueck.isPending ||
    verschieben.isPending ||
    durchgangAufrufen.isPending ||
    herausnehmen.isPending;

  const aufgerufenMelden = (anzahl: number) => {
    if (anzahl === 0) {
      zeigeMeldung({
        ton: "info",
        titel: t("aktion.niemand_aufgerufen"),
        text: t("aktion.niemand_aufgerufen_text"),
      });
    } else {
      zeigeMeldung({ ton: "erfolg", titel: t("aktion.aufgerufen", { count: anzahl }) });
    }
  };

  const naechsteAufrufen = () =>
    naechste.mutate(standId, {
      onSuccess: (neu) => aufgerufenMelden(neu.length),
      onError: fehlerMelden,
    });
  const durchgangRufen = (durchgang: Durchgang) =>
    durchgangAufrufen.mutate(durchgang.id, {
      onSuccess: (neu) => aufgerufenMelden(neu.length),
      onError: fehlerMelden,
    });
  const startRufen = (start: StationStart, bahn?: number) =>
    aufrufen.mutate(
      { startId: start.start_id, bahn },
      { onSuccess: () => aufgerufenMelden(1), onError: fehlerMelden },
    );
  const zurueckstellen = (start: StationStart, position: "front" | "back") =>
    zurueck.mutate(
      { startId: start.start_id, position },
      {
        onSuccess: () =>
          zeigeMeldung({
            ton: "erfolg",
            titel: t("bahn.zurueck_gemacht", { nr: start.start_number }),
          }),
        onError: fehlerMelden,
      },
    );
  const verschiebe = (start: StationStart, wohin: Verschiebung) =>
    verschieben.mutate({ startId: start.start_id, wohin }, { onError: fehlerMelden });

  const hauptHilfe =
    haupt.art === "naechste"
      ? wartende.length === 0
        ? t("aktion.naechste_hilfe_leer")
        : frei.length === 0
          ? t("aktion.naechste_hilfe_voll")
          : null
      : haupt.art === "keine"
        ? t("aktion.keine_hilfe")
        : null;
  const naechsterAufrufbar = ersterAufrufbarer(wartende, besetzt);
  const sortierteDurchgaenge = sortiereDurchgaenge(durchgaenge.data);
  const letzterDurchgang = sortierteDurchgaenge[sortierteDurchgaenge.length - 1];

  return (
    <div className={s.ablauf}>
      <section className={`panel ${s.bahnenPanel}`} aria-labelledby="bahnen-titel">
        <div className="panel-kopf">
          <h2 className="h-section" id="bahnen-titel">
            {stand?.name ?? t("bahn.bereich")}
          </h2>
          <div className={s.haupt}>
            {hauptHilfe && <span className="gedaempft">{hauptHilfe}</span>}
            {haupt.art === "naechste" && (
              <Button
                size="lg"
                leftSection={<PlayCircle aria-hidden />}
                loading={naechste.isPending}
                disabled={beschaeftigt || wartende.length === 0 || frei.length === 0}
                onClick={naechsteAufrufen}
              >
                {t("aktion.naechste")}
              </Button>
            )}
            {haupt.art === "durchgang" && (
              <Button
                size="lg"
                leftSection={<PlayCircle aria-hidden />}
                loading={durchgangAufrufen.isPending}
                disabled={beschaeftigt}
                onClick={() => durchgangRufen(haupt.durchgang)}
              >
                {t("aktion.durchgang_aufrufen", { nummer: haupt.durchgang.number })}
                <span className={`num ${s.hauptZeit}`}>
                  {formatUhrzeit(new Date(haupt.durchgang.starts_at), i18n.language)}
                </span>
              </Button>
            )}
          </div>
        </div>
        <ul className={s.bahnen} data-anzahl={bahnen.length}>
          {bahnen.map((bahn) => (
            <BahnKachel
              key={bahn.lane}
              bahn={bahn}
              planung={bahn.start ? (planungVon.get(bahn.start.competition_id) ?? null) : null}
              beschaeftigt={beschaeftigt}
              onNaechsten={
                naechsterAufrufbar ? () => startRufen(naechsterAufrufbar, bahn.lane) : undefined
              }
              onZurueck={zurueckstellen}
              onAbbrechen={(start, grund) => setAbbruch({ start, grund })}
            />
          ))}
        </ul>
      </section>

      <div
        className={s.unten}
        data-beide={(mitReihenfolge.length > 0 && mitZeitplan.length > 0) || undefined}
      >
        {(mitReihenfolge.length > 0 || wartende.length > 0) && (
          <section className="panel" aria-labelledby="warten-titel">
            <div className="panel-kopf">
              <h2 className="h-section" id="warten-titel">
                {t("warten.titel")}
              </h2>
              <Chip>
                <span className="num">{t("warten.anzahl", { count: wartende.length })}</span>
              </Chip>
            </div>
            <Warteliste
              wartende={wartende}
              bahnen={bahnen}
              beschaeftigt={beschaeftigt}
              onVerschieben={verschiebe}
              onAufrufen={startRufen}
              onAbbrechen={(start, grund) => setAbbruch({ start, grund })}
            />
          </section>
        )}

        {(mitZeitplan.length > 0 || durchgaenge.data.length > 0) && (
          <section className="panel" aria-labelledby="zeitplan-titel">
            <div className="panel-kopf">
              <h2 className="h-section" id="zeitplan-titel">
                {t("zeitplan.titel")}
              </h2>
            </div>
            <Zeitplan
              durchgaenge={durchgaenge.data}
              starts={zeitplanStarts}
              hauptDurchgangId={haupt.art === "durchgang" ? haupt.durchgang.id : null}
              beschaeftigt={beschaeftigt}
              onSerie={() => setSerieOffen(true)}
              onDurchgangAufrufen={durchgangRufen}
              onDurchgangAendern={setAendern}
              onDurchgangLoeschen={(d) => {
                durchgangLoeschen.reset();
                setLoeschen(d);
              }}
              onPlatz={setPlatz}
              onHerausnehmen={(start) =>
                herausnehmen.mutate(start.start_id, {
                  onSuccess: () =>
                    zeigeMeldung({
                      ton: "erfolg",
                      titel: t("zeitplan.herausgenommen", { nr: start.start_number }),
                    }),
                  onError: fehlerMelden,
                })
              }
              onAufrufen={(start) => startRufen(start)}
              onAbbrechen={(start, grund) => setAbbruch({ start, grund })}
            />
          </section>
        )}

        {mitReihenfolge.length === 0 && mitZeitplan.length === 0 && wartende.length === 0 && (
          <div className={`panel ${s.leerHinweis}`}>
            <p className="gedaempft">{t("warten.keine_reihenfolge")}</p>
            <Button
              renderRoot={(props) => (
                <Link {...props} to={`/turnier/${turnierId}`} search={{ bereich: "wettbewerbe" }} />
              )}
              variant="default"
              rightSection={<ArrowRight aria-hidden />}
            >
              {t("warten.keine_link")}
            </Button>
          </div>
        )}
      </div>

      <Bestaetigung
        offen={abbruch !== null}
        titel={
          abbruch
            ? t("abbruch.titel", {
                nr: abbruch.start.start_number,
                grund: t(`abbruch.grund.${abbruch.grund}`),
              })
            : ""
        }
        text={
          abbruch
            ? t("abbruch.text", {
                wettbewerb: abbruch.start.competition_name,
                versuch: abbruch.start.attempt,
              })
            : ""
        }
        bestaetigen={t("abbruch.bestaetigen")}
        abbrechen={t("abbruch.zurueck")}
        ton="gefahr"
        laedt={abbrechen.isPending}
        fehler={abbrechen.isError ? fehlerText(abbrechen.error) : undefined}
        onSchliessen={() => {
          setAbbruch(null);
          abbrechen.reset();
        }}
        onBestaetigen={() => {
          if (!abbruch) return;
          const { start, grund } = abbruch;
          abbrechen.mutate(
            { startId: start.start_id, grund },
            {
              onSuccess: () => {
                setAbbruch(null);
                zeigeMeldung({
                  ton: "erfolg",
                  titel: t("abbruch.gemacht", {
                    nr: start.start_number,
                    grund: t(`abbruch.grund.${grund}`),
                  }),
                });
              },
            },
          );
        }}
      />

      <Bestaetigung
        offen={loeschen !== null}
        titel={loeschen ? t("zeitplan.loeschen_titel", { nummer: loeschen.number }) : ""}
        text={
          loeschen
            ? t("zeitplan.loeschen_text", {
                zeit: formatUhrzeit(new Date(loeschen.starts_at), i18n.language),
              })
            : ""
        }
        bestaetigen={t("zeitplan.loeschen_bestaetigen")}
        abbrechen={t("zeitplan.abbrechen")}
        ton="gefahr"
        laedt={durchgangLoeschen.isPending}
        fehler={durchgangLoeschen.isError ? fehlerText(durchgangLoeschen.error) : undefined}
        onSchliessen={() => setLoeschen(null)}
        onBestaetigen={() => {
          if (!loeschen) return;
          const nummer = loeschen.number;
          durchgangLoeschen.mutate(loeschen.id, {
            onSuccess: () => {
              setLoeschen(null);
              zeigeMeldung({ ton: "erfolg", titel: t("zeitplan.geloescht", { nummer }) });
            },
          });
        }}
      />

      <SerieDialog
        offen={serieOffen}
        turnier={uebersicht}
        standId={standId}
        wettbewerbe={mitZeitplan}
        ab={letzterDurchgang?.ends_at ?? null}
        onSchliessen={() => setSerieOffen(false)}
      />
      <DurchgangDialog
        turnierId={turnierId}
        standId={standId}
        durchgang={aendern}
        onSchliessen={() => setAendern(null)}
      />
      <PlatzDialog
        turnierId={turnierId}
        start={platz}
        durchgaenge={durchgaenge.data}
        starts={zeitplanStarts}
        onSchliessen={() => setPlatz(null)}
      />
    </div>
  );
}
