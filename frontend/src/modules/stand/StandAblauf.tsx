import { Button, Skeleton, Textarea } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowRight, CalendarClock, PlayCircle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../app/berechtigungen";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { Fehlerzustand } from "../../components/Zustand";
import { formatUhrzeit } from "../../lib/format";
import {
  ABBRUCH_BEMERKUNG_MAX,
  type Abbruchgrund,
  type Durchgang,
  type DurchgangVorhalt,
  durchgaengeAbfrage,
  istDurchgangKonflikt,
  type NaechsteErgebnis,
  type StationStart,
  useDurchgangAufrufen,
  useDurchgangLoeschen,
  useNaechsteAufrufen,
  usePlatzEntfernen,
  useStartAbbrechen,
  useStartAufrufen,
  useStartVerschieben,
  useStartZurueckstellen,
  type Verschiebung,
} from "../anmeldung/api";
import { maskeAbfrage } from "../erfassung/api";
import { offeneSerien } from "../erfassung/aufgeben";
import { OffeneSerienHinweis } from "../erfassung/Dialoge";
import { ERFASSUNG_PFAD } from "../erfassung/pfade";
import type { TurnierUebersicht } from "../turnier/typen";
import {
  standStartlisteAbfrage,
  standWarteschlangeAbfrage,
  useAnzeigename,
  useBahnFreigeben,
  useFehlerMelden,
  useStandRechte,
  useVolleNamen,
} from "./aktionen";
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
import { wettbewerbText } from "./Wettbewerb";
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
  const rechte = useStandRechte();
  const anzeigename = useAnzeigename();

  const volleNamen = useVolleNamen();
  const warteschlange = useQuery(standWarteschlangeAbfrage(turnierId, standId, volleNamen));
  const durchgaenge = useQuery(durchgaengeAbfrage(turnierId, standId));
  const startliste = useQuery(standStartlisteAbfrage(turnierId, { stand: standId }, volleNamen));

  const naechste = useNaechsteAufrufen(turnierId);
  const aufrufen = useStartAufrufen(turnierId);
  const zurueck = useStartZurueckstellen(turnierId);
  const verschieben = useStartVerschieben(turnierId);
  const abbrechen = useStartAbbrechen(turnierId);
  const durchgangAufrufen = useDurchgangAufrufen(turnierId, standId);
  const durchgangLoeschen = useDurchgangLoeschen(turnierId, standId);
  const herausnehmen = usePlatzEntfernen(turnierId);
  const freigeben = useBahnFreigeben(turnierId);

  const [freigabe, setFreigabe] = useState<{ start: StationStart; bahn: number } | null>(null);
  const [abbruch, setAbbruch] = useState<{ start: StationStart; grund: Abbruchgrund } | null>(null);
  const [bemerkung, setBemerkung] = useState("");
  const [loeschen, setLoeschen] = useState<Durchgang | null>(null);
  const [serieOffen, setSerieOffen] = useState(false);
  const [aendern, setAendern] = useState<Durchgang | null>(null);
  const [platz, setPlatz] = useState<StationStart | null>(null);
  /** Rückfrage bei 409 `heat_imminent`: Text des Servers und der Aufruf mit Bestätigung */
  const [rueckfrage, setRueckfrage] = useState<{ text: string; bestaetigen: () => void } | null>(
    null,
  );

  // Aufgeben mit angefangener Serie (erfassung/aufgeben.ts): Ist eine Serie nur halb erfasst,
  // stünde der Start ohne Platz da. Die Erfassung trägt „Abbruch durch den Schützen“ ein.
  const navigate = useNavigate();
  const darfErgebnisLesen = useDarf("result.read");
  const serienPruefen =
    abbruch?.grund === "dnf" && abbruch.start.status === "captured" && darfErgebnisLesen;
  const abbruchMaske = useQuery({
    ...maskeAbfrage(turnierId, abbruch?.start.start_id ?? "", null),
    enabled: serienPruefen,
  });
  const abbruchOffene =
    serienPruefen && abbruchMaske.data
      ? offeneSerien(abbruchMaske.data.form, abbruchMaske.data.current.computed)
      : [];
  const abbruchStatus = abbruchOffene.every((o) => o.abbruchStatus)
    ? (abbruchOffene[0]?.abbruchStatus ?? null)
    : null;

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
    herausnehmen.isPending ||
    freigeben.isPending;

  /** Meldung nach dem Aufrufen; `hinweis` ist der Text des Servers (Übersprungene, freigehaltene Bahnen). */
  const aufgerufenMelden = (anzahl: number, hinweis?: string | null) => {
    if (anzahl === 0) {
      zeigeMeldung({
        ton: "info",
        titel: t("aktion.niemand_aufgerufen"),
        text: hinweis || t("aktion.niemand_aufgerufen_text"),
      });
    } else {
      zeigeMeldung({
        ton: hinweis ? "info" : "erfolg",
        titel: t("aktion.aufgerufen", { count: anzahl }),
        ...(hinweis ? { text: hinweis } : {}),
      });
    }
  };
  /**
   * Fehler eines Aufrufs: Braucht ein bald beginnender Durchgang die Bahn (409 `heat_imminent`),
   * fragt die Oberfläche mit dem Text des Servers zurück; sonst die übliche Meldung.
   */
  const aufrufFehler = (nochmalBestaetigt: () => void) => (fehler: unknown) => {
    if (istDurchgangKonflikt(fehler)) {
      setRueckfrage({
        text: fehler.detail ?? t("rueckfrage.text"),
        bestaetigen: nochmalBestaetigt,
      });
    } else {
      fehlerMelden(fehler);
    }
  };

  const naechsteRufen = (bahn?: number, bestaetigt = false) =>
    naechste.mutate(
      { standId, bahn, bestaetigt },
      {
        onSuccess: (ergebnis: NaechsteErgebnis) =>
          aufgerufenMelden(ergebnis.called.length, ergebnis.message),
        onError: bestaetigt ? fehlerMelden : aufrufFehler(() => naechsteRufen(bahn, true)),
      },
    );
  const naechsteAufrufen = () => naechsteRufen();
  const durchgangRufen = (durchgang: Durchgang) =>
    durchgangAufrufen.mutate(durchgang.id, {
      onSuccess: (neu) => aufgerufenMelden(neu.length),
      onError: fehlerMelden,
    });
  const startRufen = (start: StationStart, bahn?: number, bestaetigt = false) =>
    aufrufen.mutate(
      { startId: start.start_id, bahn, bestaetigt },
      {
        onSuccess: () => aufgerufenMelden(1),
        onError: bestaetigt ? fehlerMelden : aufrufFehler(() => startRufen(start, bahn, true)),
      },
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
  /** „Startnummer 7 · Karl Weiß“ (ohne Namen nur die Startnummer) */
  const werText = (start: StationStart) => {
    const name = anzeigename(start);
    return name.ohne
      ? t("abbruch.wer_nr", { nr: start.start_number })
      : t("abbruch.wer", { nr: start.start_number, name: name.text });
  };
  const abbruchSenden = (start: StationStart, grund: Abbruchgrund) =>
    abbrechen.mutate(
      { startId: start.start_id, grund, bemerkung },
      {
        onSuccess: () => {
          setAbbruch(null);
          setBemerkung("");
          zeigeMeldung({
            ton: "erfolg",
            titel: t("abbruch.gemacht", {
              wer: werText(start),
              grund: t(`abbruch.grund.${grund}`),
            }),
          });
        },
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
            {!rechte.aufrufen && <span className="gedaempft">{t("rechte.nur_ansehen")}</span>}
            {rechte.aufrufen && hauptHilfe && <span className="gedaempft">{hauptHilfe}</span>}
            {rechte.aufrufen && haupt.art === "naechste" && (
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
            {rechte.aufrufen && haupt.art === "durchgang" && (
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
        {warteschlange.data.upcoming_heat && (
          <VorhaltHinweis vorhalt={warteschlange.data.upcoming_heat} />
        )}
        <ul className={s.bahnen} data-anzahl={bahnen.length}>
          {bahnen.map((bahn) => (
            <BahnKachel
              key={bahn.lane}
              bahn={bahn}
              onFreigeben={(start) => {
                freigeben.reset();
                setFreigabe({ start, bahn: bahn.lane });
              }}
              planung={bahn.start ? (planungVon.get(bahn.start.competition_id) ?? null) : null}
              beschaeftigt={beschaeftigt}
              rechte={rechte}
              onNaechsten={
                // Der Server nimmt den Ersten, der nicht schon auf einer Bahn steht (auch an einem
                // anderen Stand), und überspringt die anderen.
                rechte.aufrufen && naechsterAufrufbar ? () => naechsteRufen(bahn.lane) : undefined
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
              rechte={rechte}
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
              hauptDurchgangId={
                rechte.aufrufen && haupt.art === "durchgang" ? haupt.durchgang.id : null
              }
              beschaeftigt={beschaeftigt}
              rechte={rechte}
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
                wer: werText(abbruch.start),
                grund: t(`abbruch.grund.${abbruch.grund}`),
              })
            : ""
        }
        text={
          abbruch
            ? t("abbruch.text", {
                wettbewerb: wettbewerbText(
                  abbruch.start.competition_code,
                  abbruch.start.competition_name,
                ),
                versuch: abbruch.start.attempt,
              })
            : ""
        }
        bestaetigen={
          abbruchOffene.length > 0 ? t("abbruch.zur_erfassung") : t("abbruch.bestaetigen")
        }
        abbrechen={t("abbruch.zurueck")}
        ton={abbruchOffene.length > 0 ? "normal" : "gefahr"}
        laedt={abbrechen.isPending}
        gesperrt={serienPruefen && abbruchMaske.isPending}
        fehler={abbrechen.isError ? fehlerText(abbrechen.error) : undefined}
        onSchliessen={() => {
          setAbbruch(null);
          setBemerkung("");
          abbrechen.reset();
        }}
        onBestaetigen={() => {
          if (!abbruch) return;
          if (abbruchOffene.length > 0) {
            // In der Erfassung öffnet sich die Rückfrage „aufgegeben“ mit dem Weg zur Serie.
            const startId = abbruch.start.start_id;
            setAbbruch(null);
            setBemerkung("");
            void navigate({ to: ERFASSUNG_PFAD, search: { start: startId, aufgeben: true } });
            return;
          }
          abbruchSenden(abbruch.start, abbruch.grund);
        }}
      >
        {abbruch && abbruchOffene.length > 0 && (
          <OffeneSerienHinweis
            liste={abbruchOffene}
            name={anzeigename(abbruch.start).text}
            status={abbruchStatus}
            trotzdemGesperrt={abbrechen.isPending}
            onTrotzdem={() => abbruchSenden(abbruch.start, abbruch.grund)}
          />
        )}
        {serienPruefen && abbruchMaske.isPending && (
          <p className="gedaempft" role="status">
            {t("abbruch.pruefe")}
          </p>
        )}
        <Textarea
          label={t("abbruch.bemerkung")}
          description={t("abbruch.bemerkung_hilfe", {
            anzahl: bemerkung.length,
            max: ABBRUCH_BEMERKUNG_MAX,
          })}
          value={bemerkung}
          onChange={(ereignis) => setBemerkung(ereignis.currentTarget.value)}
          maxLength={ABBRUCH_BEMERKUNG_MAX}
          rows={2}
          disabled={abbrechen.isPending}
        />
      </Bestaetigung>

      <Bestaetigung
        offen={freigabe !== null}
        titel={freigabe ? t("freigabe.titel", { bahn: freigabe.bahn }) : ""}
        text={freigabe ? t("freigabe.text", { nr: freigabe.start.start_number }) : ""}
        bestaetigen={t("freigabe.bestaetigen")}
        abbrechen={t("freigabe.zurueck")}
        laedt={freigeben.isPending}
        fehler={freigeben.isError ? fehlerText(freigeben.error) : undefined}
        onSchliessen={() => {
          setFreigabe(null);
          freigeben.reset();
        }}
        onBestaetigen={() => {
          if (!freigabe) return;
          const { start, bahn } = freigabe;
          freigeben.mutate(start.start_id, {
            onSuccess: () => {
              setFreigabe(null);
              zeigeMeldung({
                ton: "erfolg",
                titel: t("freigabe.gemacht", { bahn, nr: start.start_number }),
              });
            },
          });
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

      <Bestaetigung
        offen={rueckfrage !== null}
        titel={t("rueckfrage.titel")}
        text={rueckfrage?.text ?? ""}
        bestaetigen={t("rueckfrage.bestaetigen")}
        abbrechen={t("rueckfrage.zurueck")}
        onSchliessen={() => setRueckfrage(null)}
        onBestaetigen={() => {
          const bestaetigen = rueckfrage?.bestaetigen;
          setRueckfrage(null);
          bestaetigen?.();
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

/**
 * Ruhiger Hinweis über den Bahnen: Ein geplanter Durchgang beginnt bald und braucht Bahnen dieses
 * Stands; „Nächste aufrufen“ hält sie ab `reserved_from` frei (Uhrzeiten in Ortszeit des Geräts).
 */
function VorhaltHinweis({ vorhalt }: { vorhalt: DurchgangVorhalt }) {
  const { t, i18n } = useTranslation("stand");
  if (vorhalt.lanes.length === 0) return null;
  const uhr = (iso: string) => formatUhrzeit(new Date(iso), i18n.language);
  const bahnen = t("vorhalt.bahnen", {
    count: vorhalt.lanes.length,
    liste: new Intl.ListFormat(i18n.language, { type: "conjunction" }).format(
      vorhalt.lanes.map(String),
    ),
  });
  const werte = { nummer: vorhalt.number, zeit: uhr(vorhalt.starts_at), bahnen };
  const text = vorhalt.active
    ? t("vorhalt.aktiv", { ...werte, count: vorhalt.lanes.length })
    : vorhalt.reserved_from
      ? t("vorhalt.kommt", { ...werte, ab: uhr(vorhalt.reserved_from) })
      : t("vorhalt.kommt_ohne_ab", werte);
  return (
    <p className={s.vorhalt} data-aktiv={vorhalt.active || undefined}>
      <CalendarClock aria-hidden />
      <span>{text}</span>
    </p>
  );
}
