import { Button, Collapse, Loader, SegmentedControl, Skeleton } from "@mantine/core";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useBlocker } from "@tanstack/react-router";
import {
  ArrowRight,
  Ban,
  CheckCheck,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  Clock,
  CloudOff,
  LockOpen,
  PencilLine,
  RefreshCw,
  TriangleAlert,
  Undo2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../app/berechtigungen";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { Fehlerzustand } from "../../components/Zustand";
import { formatUhrzeit } from "../../lib/format";
import type { StationStart } from "../anmeldung/api";
import { formatWert, formatZeit, fortschrittText, restText } from "./anzeige";
import {
  type Abbruchgrund,
  type AbschnittForm,
  type Erfassungsart,
  type ErgebnisStand,
  erfassungSchluessel,
  ergebnisApi,
  type Maske as MaskeDaten,
  maskeAbfrage,
  neuerSchluessel,
  type SerieForm,
} from "./api";
import { type Namen, nameVon } from "./auswahl";
import { AbbruchDialog, AbschlussDialog, GrundDialog } from "./Dialoge";
import {
  FRISCH,
  schussPufferAbschliessen,
  schussTaste,
  type Taste,
  tasteAusTastatur,
  type ZahlEingabe,
  zahlTaste,
} from "./eingabe";
import s from "./erfassung.module.css";
import { Maske } from "./Maske";
import {
  type Entwurf,
  erreichbar,
  erstesOffenes,
  type FeldRef,
  naechstes,
  normalerPfad,
  type PfadMeldung,
  reihenfolge,
  rohwerteAus,
  type Schusswert,
  schuesseAus,
  serieAus,
  setzeWert,
  uebrigeMeldungen,
  voriges,
  wertAus,
} from "./rohwerte";
import { Sitzung, type SitzungsZustand } from "./sitzung";
import { Tastenfeld } from "./Tastenfeld";
import { Verlauf } from "./Verlauf";

/** Wie lange „1“ auf eine „0“ wartet, bevor sie als 1 gilt. */
const SCHUSS_WARTEN_MS = 900;

interface TerminalProps {
  turnierId: string;
  startId: string;
  art: Erfassungsart | null;
  onArt: (art: Erfassungsart) => void;
  kennziffern: ReadonlyMap<string, string | null>;
  /** Nächster offener Start des Stands (ohne diesen) */
  vorschlag: () => StationStart | null;
  namen: Namen;
  onOeffnen: (startId: string) => void;
}

/** Mitte und rechte Spalte: Erfassungsfläche eines Starts mit Ziffernfeld und Aktionen. */
export function Terminal(props: TerminalProps) {
  const { t } = useTranslation("erfassung");
  const maske = useQuery({
    ...maskeAbfrage(props.turnierId, props.startId, props.art),
    placeholderData: keepPreviousData,
  });

  if (maske.isPending) {
    return (
      <>
        <section className={`panel ${s.flaeche}`} aria-busy="true" aria-label={t("flaeche")}>
          <Skeleton height={72} radius="md" />
          <Skeleton height={260} radius="md" />
        </section>
        <aside className={s.eingabe} aria-busy="true">
          <Skeleton height={380} radius="lg" />
        </aside>
      </>
    );
  }
  if (maske.isError && !maske.data) {
    return (
      <section className={`panel ${s.flaeche} ${s.flaecheVoll}`} aria-label={t("flaeche")}>
        <Fehlerzustand fehler={maske.error} onErneut={() => void maske.refetch()} />
      </section>
    );
  }
  return <Flaeche {...props} maske={maske.data} wechselt={maske.isPlaceholderData} />;
}

type Dialog = null | "abschluss" | "abbruch" | "oeffnen" | "korrektur";

interface FlaecheProps extends TerminalProps {
  maske: MaskeDaten;
  /** Andere Erfassungsart wird geladen */
  wechselt: boolean;
}

function Flaeche({
  turnierId,
  startId,
  onArt,
  kennziffern,
  vorschlag,
  namen,
  onOeffnen,
  maske,
  wechselt,
}: FlaecheProps) {
  const { t } = useTranslation("erfassung");
  const fehlerText = useFehlerText();
  const queryClient = useQueryClient();
  const darfErfassen = useDarf("result.capture");
  const darfKorrigieren = useDarf("result.correct");
  const form = maske.form;
  const formRef = useRef(form);
  formRef.current = form;

  const [sitzung] = useState(
    () =>
      new Sitzung({
        basis: maske.current,
        rohwerte: (entwurf) => rohwerteAus(formRef.current, entwurf),
        senden: (raw, baseSeq, schluessel) =>
          ergebnisApi.rohwerte(turnierId, startId, raw, baseSeq, schluessel),
      }),
  );
  useEffect(() => {
    sitzung.starten();
    return () => sitzung.beenden();
  }, [sitzung]);
  const zustand: SitzungsZustand = useSyncExternalStore(sitzung.abonnieren, sitzung.lesen);
  const { entwurf, basis, phase } = zustand;

  // Neue Formularbeschreibung (andere Erfassungsart): bestimmt, was gesendet wird.
  useEffect(() => {
    sitzung.setzeRohwerte((e) => rohwerteAus(form, e));
  }, [sitzung, form]);

  // Stand nach einem Server-Ereignis: fremde Änderungen erkennen.
  useEffect(() => {
    sitzung.serverStand(maske.current);
  }, [sitzung, maske.current]);

  const fremd = zustand.fremdUebernommen;
  useEffect(() => {
    if (fremd > 0) {
      zeigeMeldung({
        ton: "info",
        titel: t("fremd.titel"),
        text: t("fremd.text"),
        schluessel: `fremd-${startId}`,
      });
    }
  }, [fremd, startId, t]);

  // Netz wieder da: sofort erneut senden.
  useEffect(() => {
    const online = () => sitzung.erneut();
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, [sitzung]);

  const [korrektur, setKorrektur] = useState(false);
  useEffect(() => {
    sitzung.setzeAutomatisch(!korrektur);
  }, [sitzung, korrektur]);

  const status = basis.status;
  const abgeschlossen = status === "final";
  const abgebrochen = status === "aborted";
  const bearbeitbar =
    phase !== "konflikt" &&
    ((korrektur && darfKorrigieren && abgeschlossen) ||
      (!korrektur && darfErfassen && !abgeschlossen && !abgebrochen));

  // Wechsel zu einem anderen Start oder einer anderen Seite: nicht stillschweigend verwerfen.
  const blocker = useBlocker({
    shouldBlockFn: ({ current, next }) => {
      const gleicherStart =
        next.pathname === current.pathname &&
        (next.search as { start?: string }).start === (current.search as { start?: string }).start;
      if (gleicherStart) return false;
      const jetzt = sitzung.lesen();
      return jetzt.ungespeichert || jetzt.phase === "sendet";
    },
    enableBeforeUnload: () => sitzung.lesen().ungespeichert,
    withResolver: true,
  });

  // --- Aktives Feld ---

  const [aufgeklappt, setAufgeklappt] = useState<ReadonlySet<string>>(new Set());
  const refs = useMemo(
    () => reihenfolge(form, entwurf, { aufgeklappt }),
    [form, entwurf, aufgeklappt],
  );
  // Zustand der Eingabe als State (für die Anzeige) und als Ref (für schnelles Tippen: Tasten
  // kommen schneller, als React neu zeichnet).
  const [aktivId, setAktivIdState] = useState<string | null>(null);
  const [eingabe, setEingabeState] = useState<ZahlEingabe>(FRISCH);
  const [schussPuffer, setSchussPufferState] = useState("");
  const aktivRef = useRef<string | null>(null);
  const eingabeRef = useRef<ZahlEingabe>(FRISCH);
  const pufferRef = useRef("");
  const bearbeitbarRef = useRef(bearbeitbar);
  bearbeitbarRef.current = bearbeitbar;
  const setAktivId = useCallback((id: string | null) => {
    aktivRef.current = id;
    setAktivIdState(id);
  }, []);
  const setEingabe = useCallback((wert: ZahlEingabe) => {
    eingabeRef.current = wert;
    setEingabeState(wert);
  }, []);
  const setSchussPuffer = useCallback((wert: string) => {
    pufferRef.current = wert;
    setSchussPufferState(wert);
  }, []);
  const schussTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const gestartet = useRef(false);

  const aktiv = bearbeitbar ? (refs.find((ref) => ref.id === aktivId) ?? null) : null;

  const gehe = useCallback(
    (ref: FeldRef | null) => {
      setAktivId(ref?.id ?? null);
      setEingabe(FRISCH);
      setSchussPuffer("");
      if (schussTimer.current) clearTimeout(schussTimer.current);
    },
    [setAktivId, setEingabe, setSchussPuffer],
  );

  // Beim Öffnen (und wenn das aktive Feld wegfällt, z. B. durch den Status) das erste offene Feld.
  useEffect(() => {
    if (!bearbeitbar) return;
    if (aktivId !== null && refs.some((ref) => ref.id === aktivId)) return;
    if (aktivId === null && gestartet.current) return;
    gestartet.current = true;
    gehe(erstesOffenes(refs, entwurf));
  }, [bearbeitbar, aktivId, refs, entwurf, gehe]);

  // Konflikt: die Frage muss sichtbar sein, auch wenn weiter unten erfasst wurde.
  const konfliktDa = phase === "konflikt";
  useEffect(() => {
    if (konfliktDa)
      document.querySelector("[data-konflikt]")?.scrollIntoView?.({ block: "center" });
  }, [konfliktDa]);

  // Aktives Feld in den sichtbaren Bereich holen (automatische Weiterschaltung).
  const sichtbarId = aktiv?.id ?? null;
  useEffect(() => {
    if (!sichtbarId) return;
    const element = document.querySelector(`[data-feld="${sichtbarId}"]`);
    element?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [sichtbarId]);

  const liste = useCallback(
    (e: Entwurf) => reihenfolge(formRef.current, e, { aufgeklappt }),
    [aufgeklappt],
  );

  const weiterVon = useCallback(
    (id: string, e: Entwurf) => {
      gehe(naechstes(liste(e), id));
    },
    [gehe, liste],
  );

  const schussEintragen = useCallback(
    (start: FeldRef, werte: readonly Schusswert[]): FeldRef | null => {
      let ref: FeldRef | null = start;
      let e = sitzung.lesen().entwurf;
      for (const wert of werte) {
        if (ref?.key !== "shots") break;
        const ziel: FeldRef = erreichbar(e, ref);
        e = setzeWert(e, ziel, wert);
        ref = naechstes(liste(e), ziel.id);
      }
      sitzung.aendern(e);
      return ref;
    },
    [sitzung, liste],
  );

  const schussLoeschen = useCallback(
    (ref: FeldRef) => {
      if (ref.serie === null || ref.schuss === undefined) return;
      const e = sitzung.lesen().entwurf;
      const anzahl = schuesseAus(serieAus(e, ref.abschnitt, ref.serie)).length;
      if (ref.schuss === anzahl - 1) {
        sitzung.aendern(setzeWert(e, ref, undefined));
        return;
      }
      if (ref.schuss >= anzahl && anzahl > 0) {
        const vorher = {
          ...ref,
          schuss: anzahl - 1,
          id: ref.id.replace(/\d+$/, String(anzahl - 1)),
        };
        sitzung.aendern(setzeWert(e, vorher, undefined));
        gehe(vorher);
        return;
      }
      if (anzahl === 0) gehe(voriges(liste(e), ref.id));
    },
    [sitzung, gehe, liste],
  );

  const taste = useCallback(
    (eingang: Taste | { art: "zeichen"; zeichen: string }) => {
      if (!bearbeitbarRef.current) return;
      const refs = liste(sitzung.lesen().entwurf);
      const aktiv = refs.find((ref) => ref.id === aktivRef.current);
      if (!aktiv) return;
      const schussPuffer = pufferRef.current;
      const eingabe = eingabeRef.current;
      if (aktiv.feld.kind === "shots") {
        const erlaubt = aktiv.feld.allowed_values ?? [];
        if (schussTimer.current) clearTimeout(schussTimer.current);
        if (eingang.art === "ziffer" || eingang.art === "zeichen") {
          const zeichen = eingang.art === "ziffer" ? eingang.ziffer : eingang.zeichen;
          const ergebnis = schussTaste(erlaubt, schussPuffer, zeichen);
          const naechster =
            ergebnis.werte.length > 0 ? schussEintragen(aktiv, ergebnis.werte) : aktiv;
          if (naechster?.id !== aktiv.id) gehe(naechster);
          setSchussPuffer(ergebnis.puffer);
          if (ergebnis.puffer && naechster) {
            const puffer = ergebnis.puffer;
            const ziel = naechster;
            schussTimer.current = setTimeout(() => {
              const wert = schussPufferAbschliessen(erlaubt, puffer);
              setSchussPuffer("");
              if (wert !== undefined) gehe(schussEintragen(ziel, [wert]));
            }, SCHUSS_WARTEN_MS);
          }
          return;
        }
        if (eingang.art === "weiter") {
          const wert = schussPufferAbschliessen(erlaubt, schussPuffer);
          if (wert !== undefined) gehe(schussEintragen(aktiv, [wert]));
          else gehe(naechstes(refs, aktiv.id));
          return;
        }
        if (eingang.art === "zurueck") {
          gehe(voriges(refs, aktiv.id));
          return;
        }
        if (eingang.art === "loeschen") {
          if (schussPuffer) setSchussPuffer("");
          else schussLoeschen(aktiv);
        }
        return;
      }
      if (eingang.art === "zeichen") return;
      const e = sitzung.lesen().entwurf;
      const aktuell = wertAus(e, aktiv);
      const ergebnis = zahlTaste(
        aktiv.feld,
        eingabe,
        typeof aktuell === "number" ? aktuell : undefined,
        eingang,
      );
      if (ergebnis.abgelehnt) return;
      let neu = e;
      if (ergebnis.geaendert) {
        neu = setzeWert(e, aktiv, ergebnis.wert);
        sitzung.aendern(neu);
      }
      setEingabe(ergebnis.eingabe);
      if (ergebnis.weiter) weiterVon(aktiv.id, neu);
      else if (ergebnis.zurueck) gehe(voriges(refs, aktiv.id));
    },
    [liste, sitzung, gehe, weiterVon, schussEintragen, schussLoeschen, setEingabe, setSchussPuffer],
  );

  const [dialog, setDialog] = useState<Dialog>(null);

  // Hardware-Tastatur: Ziffern, Komma, Enter = weiter, Rück = löschen.
  useEffect(() => {
    const beiTaste = (ereignis: KeyboardEvent) => {
      if (ereignis.ctrlKey || ereignis.metaKey || ereignis.altKey || dialog !== null) return;
      const ziel = ereignis.target as HTMLElement | null;
      if (
        ziel?.closest(
          "input, textarea, select, [contenteditable='true'], [role='dialog'], [role='listbox']",
        )
      ) {
        return;
      }
      const eingang = tasteAusTastatur(ereignis.key);
      if (!eingang || !aktivRef.current) return;
      // Enter auf einem Knopf löst den Knopf aus, nicht „weiter“.
      if (
        ereignis.key === "Enter" &&
        ziel?.closest("button, a") &&
        !ziel.closest(`.${s.flaeche}`)
      ) {
        return;
      }
      ereignis.preventDefault();
      taste(eingang);
    };
    window.addEventListener("keydown", beiTaste);
    return () => window.removeEventListener("keydown", beiTaste);
  }, [taste, dialog]);

  useEffect(
    () => () => {
      if (schussTimer.current) clearTimeout(schussTimer.current);
    },
    [],
  );

  const feldWaehlen = (ref: FeldRef) => {
    if (!bearbeitbar) return;
    gehe(erreichbar(sitzung.lesen().entwurf, ref));
  };

  const statusSetzen = (abschnitt: AbschnittForm, serie: SerieForm, wert: string) => {
    const e = setzeWert(
      sitzung.lesen().entwurf,
      { abschnitt: abschnitt.id, serie: serie.index, key: "status" },
      wert,
    );
    sitzung.aendern(e);
    const neueListe = liste(e);
    if (aktivId && !neueListe.some((ref) => ref.id === aktivId)) {
      const inSerie = neueListe.find(
        (ref) => ref.abschnitt === abschnitt.id && ref.serie === serie.index,
      );
      gehe(inSerie ?? erstesOffenes(neueListe, e));
    }
  };

  // --- Vorgänge ---

  const [laedt, setLaedt] = useState(false);
  const [vorgangFehler, setVorgangFehler] = useState<unknown>(null);
  const vorgangSchluessel = useRef<string>(neuerSchluessel());
  const [vorgeschlagen, setVorgeschlagen] = useState<StationStart | null>(null);

  const oeffneDialog = (art: Dialog) => {
    vorgangSchluessel.current = neuerSchluessel();
    setVorgangFehler(null);
    setDialog(art);
  };

  const neuLaden = () => {
    void queryClient.invalidateQueries({ queryKey: erfassungSchluessel.alle });
    void queryClient.invalidateQueries({ queryKey: ["starts"] });
  };

  const vorgang = async (
    ausfuehren: (schluessel: string) => Promise<ErgebnisStand>,
    danach?: (stand: ErgebnisStand) => void,
  ) => {
    setLaedt(true);
    setVorgangFehler(null);
    try {
      const stand = await ausfuehren(vorgangSchluessel.current);
      sitzung.uebernehmen(stand);
      setDialog(null);
      danach?.(stand);
      neuLaden();
    } catch (fehler) {
      sitzung.vorgangFehler(fehler);
      if (sitzung.lesen().phase === "konflikt") setDialog(null);
      else setVorgangFehler(fehler);
    } finally {
      setLaedt(false);
    }
  };

  const kopf = maske.header;
  const wer = `${kopf.start_number} · ${kopf.display_name ?? t("auswahl.ohne_name")}`;
  const wertung = basis.computed;
  const ergebnisText = wertung
    ? `${formatWert(wertung.score)} ${wertung.unit}`
    : formatWert(basis.score);

  const abschliessen = () =>
    vorgang(
      (schluessel) => ergebnisApi.abschliessen(turnierId, startId, basis.seq, schluessel),
      (stand) => {
        zeigeMeldung({
          ton: "erfolg",
          titel: t("abschluss.erledigt", { wer }),
          text: stand.computed
            ? `${formatWert(stand.computed.score)} ${stand.computed.unit}`
            : undefined,
        });
        setVorgeschlagen(vorschlag());
      },
    );

  const abbrechen = (grund: Abbruchgrund, text: string | null) =>
    vorgang(
      (schluessel) => ergebnisApi.abbrechen(turnierId, startId, grund, text, schluessel),
      () => {
        zeigeMeldung({ ton: "info", titel: t("abbruch.erledigt", { wer }) });
        setVorgeschlagen(vorschlag());
      },
    );

  const wiederOeffnen = (grund: string) =>
    vorgang(
      (schluessel) => ergebnisApi.wiederOeffnen(turnierId, startId, grund, basis.seq, schluessel),
      () => {
        gestartet.current = false;
        setAktivId(null);
        zeigeMeldung({ ton: "info", titel: t("oeffnen.erledigt") });
      },
    );

  const korrekturSpeichern = (grund: string) =>
    vorgang(
      (schluessel) =>
        ergebnisApi.korrigieren(
          turnierId,
          startId,
          rohwerteAus(form, sitzung.lesen().entwurf),
          grund,
          basis.seq,
          schluessel,
        ),
      (stand) => {
        setKorrektur(false);
        zeigeMeldung({
          ton: "erfolg",
          titel: t("korrektur.erledigt"),
          text: stand.computed
            ? `${formatWert(stand.computed.score)} ${stand.computed.unit}`
            : undefined,
        });
      },
    );

  const korrekturBeginnen = () => {
    setKorrektur(true);
    setVorgeschlagen(null);
    gestartet.current = false;
    setAktivId(null);
  };
  const korrekturVerwerfen = () => {
    sitzung.uebernehmen(basis);
    setKorrektur(false);
    gehe(null);
  };

  // --- Anzeige ---

  const fehler: PfadMeldung[] = zustand.feldFehler;
  const warnungen: PfadMeldung[] = (wertung?.warnings ?? []).map((w) => ({
    pfad: normalerPfad(w.path),
    meldung: w.message,
  }));
  const uebrigeFehler = uebrigeMeldungen(form, fehler);
  const uebrigeWarnungen = uebrigeMeldungen(form, warnungen);
  const berechnet = zustand.ungespeichert || phase === "wartet" || phase === "sendet";
  const vollstaendig =
    (wertung?.complete ?? false) && !zustand.ungespeichert && phase === "gespeichert";
  const ringe = form.sections.some((a) => a.series.some((serie) => serie.shots !== null));
  const titelAktiv = aktiv ? feldTitel(aktiv, form, t) : null;
  const naechsterVorschlag = vorgeschlagen ?? (abgeschlossen || abgebrochen ? vorschlag() : null);

  return (
    <>
      <section
        className={`panel ${s.flaeche}`}
        aria-label={t("flaeche")}
        data-korrektur={korrektur || undefined}
      >
        <Kopf
          maske={maske}
          basis={basis}
          kennziffer={kennziffern.get(kopf.competition_id) ?? null}
        />

        {phase === "konflikt" && zustand.konflikt && (
          <KonfliktHinweis
            aktuell={zustand.konflikt}
            onServer={() => {
              sitzung.konfliktServer();
              gestartet.current = false;
              setAktivId(null);
            }}
            onMeins={() => sitzung.konfliktMeins()}
          />
        )}
        {phase === "abgelehnt" && uebrigeFehler.length === 0 && zustand.feldFehler.length === 0 && (
          <div className={s.banner} data-ton="krit" role="alert">
            <CircleAlert aria-hidden />
            <div>
              <strong>{t("senden.abgelehnt")}</strong>
              <p>{fehlerText(zustand.fehler)}</p>
            </div>
            <Button variant="default" onClick={() => sitzung.erneut()}>
              {t("senden.erneut")}
            </Button>
          </div>
        )}
        {korrektur && (
          <div className={s.banner} data-ton="info">
            <PencilLine aria-hidden />
            <div>
              <strong>{t("korrektur.modus")}</strong>
              <p>{t("korrektur.modus_text")}</p>
            </div>
          </div>
        )}

        {(ringe || form.notes.length > 0) && (
          <div className={s.artZeile}>
            {ringe && (
              <>
                <span className="h-label">{t("art.titel")}</span>
                <SegmentedControl
                  value={form.capture_mode}
                  onChange={(wert) => onArt(wert as Erfassungsart)}
                  data={[
                    { value: "series", label: t("art.series") },
                    { value: "shot", label: t("art.shot") },
                  ]}
                  disabled={wechselt}
                  className={s.artWahl}
                  aria-label={t("art.titel")}
                />
              </>
            )}
            {form.notes.map((note) => (
              <p key={note} className={s.klein}>
                {note}
              </p>
            ))}
          </div>
        )}

        <Maske
          form={form}
          entwurf={entwurf}
          wertung={wertung}
          aktivId={aktiv?.id ?? null}
          eingabe={eingabe}
          schussPuffer={schussPuffer}
          bearbeitbar={bearbeitbar}
          fehler={fehler}
          warnungen={warnungen}
          aufgeklappt={aufgeklappt}
          onAufklappen={(pfad) =>
            setAufgeklappt((alt) => {
              const neu = new Set(alt);
              if (neu.has(pfad)) neu.delete(pfad);
              else neu.add(pfad);
              return neu;
            })
          }
          onFeld={feldWaehlen}
          onStatus={statusSetzen}
          veraltet={berechnet || korrektur}
        />

        {(uebrigeFehler.length > 0 || uebrigeWarnungen.length > 0) && (
          <ul className={s.meldungen}>
            {uebrigeFehler.map((m) => (
              <li key={`f-${m.pfad}-${m.meldung}`} className={s.meldungFehler} role="alert">
                <CircleAlert aria-hidden />
                {m.meldung}
              </li>
            ))}
            {uebrigeWarnungen.map((m) => (
              <li key={`w-${m.pfad}-${m.meldung}`} className={s.meldungWarnung}>
                <TriangleAlert aria-hidden />
                {m.meldung}
              </li>
            ))}
          </ul>
        )}

        <Gesamtstand basis={basis} berechnet={berechnet} korrektur={korrektur} />

        <Verlauf
          form={form}
          turnierId={turnierId}
          startId={startId}
          offen={abgeschlossen}
          key={`${abgeschlossen}`}
        />
      </section>

      <aside className={s.eingabe} aria-label={t("eingabe")}>
        {!(abgeschlossen && !korrektur) && !abgebrochen && (
          <Tastenfeld
            aktiv={aktiv}
            titel={titelAktiv}
            eingabe={eingabe}
            wert={aktiv ? wertAus(entwurf, aktiv) : undefined}
            schussPuffer={schussPuffer}
            gesperrt={!bearbeitbar}
            onTaste={taste}
            onSchuss={(wert) => {
              if (aktiv) gehe(schussEintragen(aktiv, [wert]));
            }}
          />
        )}

        <section className={`panel ${s.aktionen}`} aria-label={t("aktionen")}>
          {korrektur ? (
            <>
              <Button
                size="lg"
                className={s.primaer}
                leftSection={<CheckCheck aria-hidden />}
                disabled={!zustand.ungespeichert}
                onClick={() => oeffneDialog("korrektur")}
              >
                {t("korrektur.speichern")}
              </Button>
              <p className={s.aktionHinweis}>
                {zustand.ungespeichert ? t("korrektur.hinweis") : t("korrektur.unveraendert")}
              </p>
              <Button
                variant="default"
                leftSection={<Undo2 aria-hidden />}
                onClick={korrekturVerwerfen}
              >
                {t("korrektur.verwerfen")}
              </Button>
            </>
          ) : abgeschlossen || abgebrochen ? (
            <>
              <p className={s.aktionHinweis} data-erledigt>
                {abgeschlossen
                  ? t("abschluss.ist", { ergebnis: ergebnisText })
                  : t("abbruch.ist", {
                      grund: basis.abort_reason ? t(`abbruch.lang.${basis.abort_reason}`) : "",
                    })}
              </p>
              {naechsterVorschlag && (
                <Button
                  size="lg"
                  className={s.primaer}
                  rightSection={<ArrowRight aria-hidden />}
                  onClick={() => onOeffnen(naechsterVorschlag.start_id)}
                >
                  {t("naechster.knopf", {
                    nr: naechsterVorschlag.start_number,
                    name: nameVon(naechsterVorschlag, namen) ?? "",
                  })}
                </Button>
              )}
              {abgeschlossen && darfKorrigieren && (
                <>
                  <Button
                    variant="default"
                    leftSection={<PencilLine aria-hidden />}
                    onClick={korrekturBeginnen}
                  >
                    {t("korrektur.knopf")}
                  </Button>
                  <Button
                    variant="default"
                    leftSection={<LockOpen aria-hidden />}
                    onClick={() => oeffneDialog("oeffnen")}
                  >
                    {t("oeffnen.knopf")}
                  </Button>
                </>
              )}
            </>
          ) : (
            <>
              <Button
                size="lg"
                className={s.primaer}
                leftSection={<CheckCheck aria-hidden />}
                disabled={!vollstaendig || !darfErfassen}
                onClick={() => oeffneDialog("abschluss")}
              >
                {t("abschluss.knopf")}
              </Button>
              <p className={s.aktionHinweis} aria-live="polite">
                {vollstaendig
                  ? t("abschluss.bereit")
                  : wertung
                    ? (restText(wertung.progress, t) ?? t("abschluss.warten"))
                    : t("abschluss.warten")}
              </p>
              <SendeStatus zustand={zustand} onErneut={() => sitzung.erneut()} />
              <div className={s.trenner} />
              <Button
                variant="subtle"
                color="red"
                leftSection={<Ban aria-hidden />}
                disabled={!darfErfassen}
                onClick={() => oeffneDialog("abbruch")}
              >
                {t("abbruch.knopf")}
              </Button>
            </>
          )}
        </section>
      </aside>

      {dialog === "abschluss" && (
        <AbschlussDialog
          offen
          laedt={laedt}
          fehler={vorgangFehler}
          onSchliessen={() => setDialog(null)}
          onBestaetigen={() => void abschliessen()}
          ergebnis={ergebnisText}
          wer={wer}
        />
      )}
      {dialog === "abbruch" && (
        <AbbruchDialog
          offen
          laedt={laedt}
          fehler={vorgangFehler}
          onSchliessen={() => setDialog(null)}
          onBestaetigen={(grund, text) => void abbrechen(grund, text)}
          wer={wer}
        />
      )}
      {dialog === "oeffnen" && (
        <GrundDialog
          offen
          laedt={laedt}
          fehler={vorgangFehler}
          onSchliessen={() => setDialog(null)}
          onBestaetigen={(grund) => void wiederOeffnen(grund)}
          titel={t("oeffnen.titel")}
          text={t("oeffnen.text", { wer })}
          bestaetigen={t("oeffnen.bestaetigen")}
        />
      )}
      {dialog === "korrektur" && (
        <GrundDialog
          offen
          laedt={laedt}
          fehler={vorgangFehler}
          onSchliessen={() => setDialog(null)}
          onBestaetigen={(grund) => void korrekturSpeichern(grund)}
          titel={t("korrektur.titel")}
          text={t("korrektur.text", { wer })}
          bestaetigen={t("korrektur.bestaetigen")}
        />
      )}
      {blocker.status === "blocked" && (
        <Bestaetigung
          offen
          titel={t("wechsel.titel")}
          text={t("wechsel.text")}
          bestaetigen={t("wechsel.verwerfen")}
          abbrechen={t("wechsel.bleiben")}
          ton="gefahr"
          onSchliessen={() => blocker.reset()}
          onBestaetigen={() => blocker.proceed()}
        />
      )}
    </>
  );
}

function feldTitel(
  ref: FeldRef,
  form: MaskeDaten["form"],
  t: ReturnType<typeof useTranslation<"erfassung">>["t"],
): string {
  const abschnitt = form.sections.find((a) => a.id === ref.abschnitt);
  const serie = ref.serie !== null ? abschnitt?.series.find((x) => x.index === ref.serie) : null;
  const ort = serie?.label ?? abschnitt?.name ?? "";
  const was =
    ref.schuss !== undefined ? t("tasten.schuss", { nr: ref.schuss + 1 }) : ref.feld.label;
  return `${ort} · ${was}`;
}

function Kopf({
  maske,
  basis,
  kennziffer,
}: {
  maske: MaskeDaten;
  basis: ErgebnisStand;
  kennziffer: string | null;
}) {
  const { t } = useTranslation("erfassung");
  const kopf = maske.header;
  const zeile = [
    kopf.club,
    kopf.class_name,
    kopf.lane != null ? t("kopf.bahn", { bahn: kopf.lane }) : t("kopf.ohne_bahn"),
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <header className={s.wer}>
      <div className={s.werHaupt}>
        <span className={`${s.startnummer} num`}>
          <span className="nur-screenreader">{t("kopf.startnummer_kurz")} </span>
          {kopf.start_number}
        </span>
        <div className={s.werText}>
          <h2 className="h-display">{kopf.display_name ?? t("auswahl.ohne_name")}</h2>
          <p className="gedaempft">{zeile}</p>
        </div>
        <div className={s.werChips}>
          {kopf.attempts_booked > 1 && (
            <Chip ton="info">
              {t("kopf.versuch", { nr: kopf.attempt, von: kopf.attempts_booked })}
            </Chip>
          )}
          <StartStatusChip basis={basis} />
          {basis.is_provisional && basis.provisional_until && (
            <Chip ton="neutral" icon={Clock}>
              {t("kopf.vorlaeufig", { zeit: formatUhrzeit(new Date(basis.provisional_until)) })}
            </Chip>
          )}
        </div>
      </div>
      <div className={`inset ${s.wettbewerb}`}>
        {kennziffer && <span className={`${s.kennziffer} num`}>{kennziffer}</span>}
        <div className={s.wettbewerbText}>
          <strong>{kopf.competition_name}</strong>
          <span className="gedaempft">
            {maske.form.variant_name !== "Standard" ? `${maske.form.variant_name} · ` : ""}
            {maske.form.max_rings != null
              ? t("kopf.max_ringe", { max: maske.form.max_rings })
              : t(`kopf.richtung.${maske.form.direction}`)}
          </span>
        </div>
      </div>
      {basis.needs_review && (
        <div className={s.banner} data-ton="warn" role="status">
          <TriangleAlert aria-hidden />
          <div>
            <strong>{t("pruefen.chip")}</strong>
            <p>{basis.review_reason ?? t("pruefen.ohne_grund")}</p>
          </div>
        </div>
      )}
    </header>
  );
}

function StartStatusChip({ basis }: { basis: ErgebnisStand }) {
  const { t } = useTranslation("erfassung");
  switch (basis.status) {
    case "final":
      return (
        <Chip ton="gruen" icon={CheckCheck}>
          {t("kachel.abgeschlossen")}
        </Chip>
      );
    case "aborted":
      return (
        <Chip ton="krit" icon={Ban}>
          {basis.abort_reason ? t(`abbruch.kurz.${basis.abort_reason}`) : t("kachel.abgebrochen")}
        </Chip>
      );
    case "captured":
      return <Chip ton="info">{t("kachel.in_erfassung")}</Chip>;
    case "called":
      return <Chip ton="neutral">{t("status.called")}</Chip>;
    default:
      return <Chip ton="neutral">{t("status.registered")}</Chip>;
  }
}

function Gesamtstand({
  basis,
  berechnet,
  korrektur,
}: {
  basis: ErgebnisStand;
  berechnet: boolean;
  korrektur: boolean;
}) {
  const { t } = useTranslation("erfassung");
  const [wegOffen, setWegOffen] = useState(false);
  const wertung = basis.computed;
  if (!wertung) return null;
  const nebenwerte: { name: string; wert: string }[] = [];
  if (wertung.tens !== null && wertung.rings !== null) {
    nebenwerte.push({ name: t("gesamt.zehner"), wert: formatWert(wertung.tens) });
  }
  if (wertung.inner_tens !== null && wertung.rings !== null) {
    nebenwerte.push({ name: t("gesamt.innenzehner"), wert: formatWert(wertung.inner_tens) });
  }
  if (wertung.penalty_cs) {
    nebenwerte.push({ name: t("gesamt.zuschlag"), wert: formatZeit(wertung.penalty_cs) });
  }
  if (wertung.deduction !== null && Number(wertung.deduction) !== 0) {
    nebenwerte.push({ name: t("gesamt.abzug"), wert: formatWert(wertung.deduction) });
  }
  return (
    <section className={s.gesamt} aria-live="polite" aria-labelledby="erf-gesamt">
      <div className={s.gesamtZeile}>
        <div className={s.gesamtHaupt} data-veraltet={berechnet || korrektur || undefined}>
          <span className="h-label" id="erf-gesamt">
            {t("gesamt.titel")}
          </span>
          <strong className="num">{formatWert(wertung.score)}</strong>
          <span className={s.gesamtEinheit}>{wertung.unit}</span>
        </div>
        {nebenwerte.length > 0 && (
          <dl className={s.nebenwerte}>
            {nebenwerte.map((w) => (
              <div key={w.name}>
                <dt>{w.name}</dt>
                <dd className="num">{w.wert}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      <p className={s.fortschritt}>
        <span className="num">{fortschrittText(wertung.progress, t)}</span>
        {berechnet && !korrektur && (
          <span className={s.berechnet}>
            <Loader size={12} aria-hidden />
            {t("gesamt.berechnet")}
          </span>
        )}
        {korrektur && <span className={s.berechnet}>{t("korrektur.erst_danach")}</span>}
        {wertung.tie_breakers_missing.length > 0 && (
          <span className={s.klein}>
            {t("gesamt.gleichstand_fehlt", { was: wertung.tie_breakers_missing.join(", ") })}
          </span>
        )}
      </p>
      {wertung.steps.length > 0 && (
        <>
          <button
            type="button"
            className={s.aufklappen}
            onClick={() => setWegOffen((o) => !o)}
            aria-expanded={wegOffen}
          >
            {wegOffen ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />}
            {t("gesamt.rechenweg")}
          </button>
          <Collapse expanded={wegOffen}>
            <ol className={`${s.rechenweg} num`}>
              {wertung.steps.map((schritt, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: Schritte haben keine eigene Kennung
                <li key={index}>{schritt}</li>
              ))}
            </ol>
          </Collapse>
        </>
      )}
    </section>
  );
}

function SendeStatus({ zustand, onErneut }: { zustand: SitzungsZustand; onErneut: () => void }) {
  const { t } = useTranslation("erfassung");
  switch (zustand.phase) {
    case "gespeichert":
      return zustand.basis.seq > 0 ? (
        <p className={s.sendeStatus} data-ton="gruen">
          <CheckCheck aria-hidden />
          {t("senden.gespeichert")}
        </p>
      ) : null;
    case "wartet":
    case "sendet":
      return (
        <p className={s.sendeStatus}>
          <Loader size={14} aria-hidden />
          {t("senden.laeuft")}
        </p>
      );
    case "netzfehler":
      return (
        <div className={s.sendeStatus} data-ton="warn" role="status">
          <CloudOff aria-hidden />
          <span>{t("senden.netzfehler", { count: zustand.versuche })}</span>
          <Button
            size="compact-md"
            variant="default"
            leftSection={<RefreshCw aria-hidden />}
            onClick={onErneut}
          >
            {t("senden.jetzt")}
          </Button>
        </div>
      );
    case "abgelehnt":
      return (
        <p className={s.sendeStatus} data-ton="krit" role="alert">
          <CircleAlert aria-hidden />
          {t("senden.abgelehnt_kurz")}
        </p>
      );
    case "konflikt":
      return (
        <p className={s.sendeStatus} data-ton="warn">
          <TriangleAlert aria-hidden />
          {t("senden.konflikt_kurz")}
        </p>
      );
  }
}

function KonfliktHinweis({
  aktuell,
  onServer,
  onMeins,
}: {
  aktuell: ErgebnisStand;
  onServer: () => void;
  onMeins: () => void;
}) {
  const { t } = useTranslation("erfassung");
  const wertung = aktuell.computed;
  return (
    <div className={s.banner} data-ton="warn" role="alert" data-konflikt>
      <TriangleAlert aria-hidden />
      <div>
        <strong>{t("konflikt.titel")}</strong>
        <p>{t("konflikt.text")}</p>
        {wertung && (
          <p className="num">
            {t("konflikt.server", {
              ergebnis: `${formatWert(wertung.score)} ${wertung.unit}`,
              fortschritt: fortschrittText(wertung.progress, t),
            })}
          </p>
        )}
        {aktuell.status === "final" && <p>{t("konflikt.abgeschlossen")}</p>}
      </div>
      <div className={s.bannerAktionen}>
        <Button variant="default" leftSection={<RefreshCw aria-hidden />} onClick={onServer}>
          {t("konflikt.laden")}
        </Button>
        {aktuell.status !== "final" && aktuell.status !== "aborted" && (
          <Button variant="subtle" onClick={onMeins}>
            {t("konflikt.meins")}
          </Button>
        )}
      </div>
    </div>
  );
}
