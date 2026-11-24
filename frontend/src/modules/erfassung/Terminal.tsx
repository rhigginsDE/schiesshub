import { Button, Collapse, Loader, SegmentedControl, Skeleton } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
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
  Users,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { healthAbfrage } from "../../api/abfragen";
import { ApiFehler } from "../../api/client";
import { useDarf } from "../../app/berechtigungen";
import { Bestaetigung } from "../../components/Bestaetigung";
import { scrollVerhalten } from "../../components/bewegung";
import { Chip } from "../../components/Chip";
import { useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { Fehlerzustand } from "../../components/Zustand";
import { formatUhrzeit } from "../../lib/format";
import type { StationStart } from "../anmeldung/api";
import {
  formatWert,
  formatZeit,
  fortschrittText,
  notizen,
  restText,
  ringEinheit,
  vorgaben,
  zaehltTreffer,
} from "./anzeige";
import {
  type Abbruchgrund,
  type AbschnittForm,
  type AufgebenAuskunft,
  type Erfassungsart,
  type ErgebnisStand,
  erfassungSchluessel,
  ergebnisApi,
  ladeMaske,
  type Maske as MaskeDaten,
  maskeAbfrage,
  type Notiz,
  neuerSchluessel,
  SeqKonflikt,
  type SerieForm,
  vorschauAbfrage,
  type Wertung,
} from "./api";
import {
  ABBRUCH_DURCH_SCHUETZEN,
  gemeinsamerStatus,
  type OffeneSerie,
  orteText,
  serienDerAuskunft,
} from "./aufgeben";
import { type Namen, nameVon } from "./auswahl";
import {
  AbbruchDialog,
  AenderungsListe,
  GrundDialog,
  OhnePlatzHinweis,
  PruefDialog,
  type PruefKopf,
} from "./Dialoge";
import {
  type Ablehnung,
  FRISCH,
  istJeZiel,
  istKommaFeld,
  schussPufferAbschliessen,
  schussTaste,
  type Taste,
  tasteAusTastatur,
  type ZahlEingabe,
  zahlTaste,
  zeitText,
} from "./eingabe";
import s from "./erfassung.module.css";
import { Maske } from "./Maske";
import {
  abgeleiteteWerte,
  aenderungen,
  type Entwurf,
  erreichbar,
  erstesOffenes,
  type FeldRef,
  fehlstellen,
  fertigeSerien,
  gleicheRohwerte,
  hatWert,
  mitAbgeleiteten,
  naechstes,
  normalerPfad,
  type PfadMeldung,
  reihenfolge,
  rohwerteAus,
  type Schusswert,
  schuesseAus,
  serieAus,
  serienPfad,
  setzeWert,
  stabil,
  uebrigeMeldungen,
  voriges,
  wertAus,
  zeitenUeberGrenze,
  zielNachStatus,
} from "./rohwerte";
import { Sitzung, type SitzungsZustand, sitzungsAblage } from "./sitzung";
import { Tastenfeld } from "./Tastenfeld";
import { Verlauf } from "./Verlauf";

/** Wie lange „1“ auf eine „0“ wartet, bevor sie als 1 gilt. */
const SCHUSS_WARTEN_MS = 900;

/**
 * Nimmt den Fokus aus einem Eingabe- oder Auswahlfeld (nicht aus Dialogen), damit Ziffern und Enter
 * wieder beim Terminal ankommen: Die Tastatur-Steuerung übergeht Tasten in solchen Feldern.
 */
function tastaturZurueck() {
  const fokus = document.activeElement;
  if (
    fokus instanceof HTMLElement &&
    fokus.closest("input, textarea, select, [role='listbox']") &&
    !fokus.closest("[role='dialog']")
  ) {
    fokus.blur();
  }
}

/**
 * Trägt „Abbruch durch den Schützen“ in die Serien ein, die den Status kennen und noch keinen
 * haben (ein schon gesetzter Status, z. B. „Zeitlimit erreicht“, bleibt).
 */
function mitAbbruchStatus(entwurf: Entwurf, serien: readonly OffeneSerie[]): Entwurf {
  let e = entwurf;
  for (const offen of serien) {
    if (!offen.abbruchStatus || offen.statusGesetzt) continue;
    e = setzeWert(
      e,
      { abschnitt: offen.abschnitt.id, serie: offen.serie.index, key: "status" },
      ABBRUCH_DURCH_SCHUETZEN,
    );
  }
  return e;
}

/**
 * Erstes leeres Feld in diesen Serien (dorthin geht die Eingabe nach dem Status): zuerst ein Wert,
 * den der Server als fehlend nennt (`missing_fields`), sonst das erste offene Feld der Serie.
 */
function erstesFeldIn(
  refs: readonly FeldRef[],
  entwurf: Entwurf,
  serien: readonly OffeneSerie[],
): FeldRef | null {
  for (const offen of serien) {
    const inSerie = refs.filter(
      (r) => r.abschnitt === offen.abschnitt.id && r.serie === offen.serie.index,
    );
    const fehlt = inSerie.find((r) => offen.fehlend.includes(r.key) && !hatWert(entwurf, r));
    const ziel = fehlt ?? erstesOffenes(inSerie, entwurf);
    if (ziel) return ziel;
  }
  return null;
}

/** Erstes offenes Feld einer Serie (Pfad `sections.x.series.2`), sonst ihr erstes Feld. */
function erstesFeldDerSerie(
  refs: readonly FeldRef[],
  entwurf: Entwurf,
  pfad: string,
): FeldRef | null {
  const inSerie = refs.filter(
    (r) => r.serie !== null && serienPfad(r.abschnitt, r.serie) === pfad && !r.ungewertet,
  );
  return erstesOffenes(inSerie, entwurf) ?? inSerie[0] ?? null;
}

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
  /** Vom Schießstand mit „aufgegeben“ hierher geschickt: Rückfrage zum Aufgeben gleich öffnen */
  aufgeben?: boolean;
  /** Die Bitte `aufgeben` ist angekommen (aus der Adresse nehmen) */
  onAufgebenGelesen?: () => void;
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

type Dialog = null | "abschluss" | "abbruch" | "oeffnen" | "korrektur" | "zuruecknehmen";

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
  aufgeben,
  onAufgebenGelesen,
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
        // Unbestätigte Eingaben überleben Neuladen und Neuaufbau der Ansicht (je Tab).
        ablage: sitzungsAblage(`schiesshub.erfassung.entwurf.${turnierId}.${startId}`),
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

  const wiederhergestellt = zustand.wiederhergestellt;
  useEffect(() => {
    if (wiederhergestellt) {
      zeigeMeldung({
        ton: "info",
        titel: t("wiederhergestellt.titel"),
        text: t("wiederhergestellt.text"),
        schluessel: `zurueck-${startId}`,
      });
    }
  }, [wiederhergestellt, startId, t]);

  const fremd = zustand.fremdUebernommen;
  // Uhrzeit der letzten Änderung von einem anderen Gerät: bleibt als Hinweis stehen (QA KLEIN 9).
  const [fremdUm, setFremdUm] = useState<Date | null>(null);
  useEffect(() => {
    if (fremd > 0) {
      setFremdUm(new Date());
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

  // Server antwortet wieder (dieselbe Abfrage wie „Server verbunden“ oben): nicht auf den nächsten
  // Versuch warten, sonst steht kurz „verbunden“ neben „keine Verbindung“ (QA KLEIN 13).
  const health = useQuery(healthAbfrage());
  const serverDa = health.status === "success" && health.data.status !== "fehler";
  const serverStandZeit = health.dataUpdatedAt;
  useEffect(() => {
    if (serverDa && serverStandZeit > 0 && sitzung.lesen().phase === "netzfehler") sitzung.erneut();
  }, [serverDa, serverStandZeit, sitzung]);

  const [korrektur, setKorrektur] = useState(false);
  useEffect(() => {
    sitzung.setzeAutomatisch(!korrektur);
  }, [sitzung, korrektur]);

  const status = basis.status;
  const abgeschlossen = status === "final";
  const abgebrochen = status === "aborted";
  const bearbeitbar =
    phase !== "konflikt" &&
    ((korrektur && darfKorrigieren && (abgeschlossen || abgebrochen)) ||
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
    // Neuladen mit unbestätigter Eingabe: Rückfrage des Browsers (die Eingabe liegt zusätzlich in
    // der Ablage und käme nach dem Neuladen zurück).
    enableBeforeUnload: () => !sitzung.allesBestaetigt(),
    withResolver: true,
  });

  // --- Aktives Feld ---

  // Seriensumme aus den Einzelwerten (Server, nur Anzeige): zählt für Lücken und das erste offene
  // Feld als Wert, gesendet wird sie nie.
  const abgeleitet = useMemo(
    () => abgeleiteteWerte(entwurf, maske.derived_values),
    [entwurf, maske.derived_values],
  );
  const ansicht = useMemo(() => mitAbgeleiteten(entwurf, abgeleitet), [entwurf, abgeleitet]);

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
  const [hinweis, setHinweis] = useState<Ablehnung | null>(null);
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
    (ref: FeldRef | null, eingabe: ZahlEingabe = FRISCH) => {
      setAktivId(ref?.id ?? null);
      setEingabe(eingabe);
      setSchussPuffer("");
      setHinweis(null);
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
    gehe(erstesOffenes(refs, ansicht));
  }, [bearbeitbar, aktivId, refs, ansicht, gehe]);

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
    element?.scrollIntoView?.({ block: "nearest", behavior: scrollVerhalten() });
  }, [sichtbarId]);

  const liste = useCallback(
    (e: Entwurf) => reihenfolge(formRef.current, e, { aufgeklappt }),
    [aufgeklappt],
  );

  const weiterVon = useCallback(
    (id: string, e: Entwurf, eingabe: ZahlEingabe) => {
      gehe(naechstes(liste(e), id), eingabe);
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
      // Leere Serie: nichts löschen und nicht in die vorige Serie springen.
      if (anzahl === 0) setHinweis("leer");
    },
    [sitzung, gehe],
  );

  const taste = useCallback(
    (eingang: Taste | { art: "zeichen"; zeichen: string }) => {
      if (!bearbeitbarRef.current) return;
      const refs = liste(sitzung.lesen().entwurf);
      const aktiv = refs.find((ref) => ref.id === aktivRef.current);
      if (!aktiv) return;
      const schussPuffer = pufferRef.current;
      const eingabe = eingabeRef.current;
      // Schüsse mit festen Ringwerten (ganze Ringe, Treffer je Ziel); Zehntel gehen wie Zahlen.
      if (aktiv.feld.kind === "shots" && !istKommaFeld(aktiv.feld)) {
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
      // Zehntel-Schüsse stehen in einer Liste ohne Lücken: Ein Tipp hinter die erste Lücke
      // schreibt in die Lücke.
      const ziel = aktiv.schuss !== undefined ? erreichbar(e, aktiv) : aktiv;
      if (ziel.id !== aktiv.id) setAktivId(ziel.id);
      const aktuell = wertAus(e, ziel);
      // Selbsttätig weiter nur in ein leeres Feld: ein vorhandener Wert wird nie überschrieben,
      // ohne dass jemand das Feld ausdrücklich ansteuert.
      const folgend = naechstes(refs, ziel.id);
      const ergebnis = zahlTaste(
        ziel.feld,
        eingabe,
        aktuell,
        eingang,
        folgend !== null && hatWert(e, folgend),
      );
      if (ergebnis.abgelehnt) {
        setHinweis(ergebnis.grund ?? null);
        return;
      }
      setHinweis(ergebnis.grund ?? null);
      let neu = e;
      if (ergebnis.geaendert) {
        // Ein Schuss mitten in der Reihe wird beim Leeren nicht entfernt (sonst fielen die
        // folgenden mit weg); er behält seinen Wert, bis ein neuer gültiger Wert dasteht.
        const anzahl =
          ziel.schuss !== undefined && ziel.serie !== null
            ? schuesseAus(serieAus(e, ziel.abschnitt, ziel.serie)).length
            : 0;
        const mitten = ziel.schuss !== undefined && ziel.schuss < anzahl - 1;
        if (ergebnis.wert !== undefined || !mitten) {
          neu = setzeWert(e, ziel, ergebnis.wert);
          sitzung.aendern(neu);
        }
      }
      if (ergebnis.weiter) weiterVon(ziel.id, neu, ergebnis.eingabe);
      else if (ergebnis.zurueck) gehe(voriges(refs, ziel.id));
      else setEingabe(ergebnis.eingabe);
    },
    [
      liste,
      sitzung,
      gehe,
      weiterVon,
      schussEintragen,
      schussLoeschen,
      setAktivId,
      setEingabe,
      setSchussPuffer,
    ],
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
      // Enter auf einem Feld wählt es nie aus: Sonst holt ein Enter nach dem letzten Feld das zuletzt
      // angetippte Feld (z. B. Serie 1 · Zeit) zurück, und die nächsten Ziffern überschreiben es.
      // Ausdrücklich wählen: antippen oder mit der Leertaste.
      if (ereignis.key === "Enter" && ziel?.closest("[data-feld]")) ereignis.preventDefault();
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
    // Felder nehmen beim Antippen keinen Fokus. Steht er noch in einem Auswahlfeld (z. B. eben den
    // Ablauf der Serie gewählt), gingen getippte Ziffern dorthin statt ins angetippte Feld (QA G-5).
    tastaturZurueck();
    gehe(erreichbar(sitzung.lesen().entwurf, ref));
  };

  const statusSetzen = (abschnitt: AbschnittForm, serie: SerieForm, wert: string) => {
    const e = setzeWert(
      sitzung.lesen().entwurf,
      { abschnitt: abschnitt.id, serie: serie.index, key: "status" },
      wert,
    );
    sitzung.aendern(e);
    // Nach der Wahl gehört die Tastatur wieder dem Terminal (QA G-5): Fokus aus dem Auswahlfeld,
    // und aktiv wird ein leeres Feld dieser Serie, nie eines mit Wert.
    tastaturZurueck();
    gehe(zielNachStatus(liste(e), e, abschnitt.id, serie.index));
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
    /** 409 mit Stand selbst behandeln (statt Konflikt der Sitzung); der Dialog bleibt offen. */
    beiKonflikt?: (konflikt: SeqKonflikt) => void,
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
      if (beiKonflikt && fehler instanceof SeqKonflikt) {
        // Nichts wurde geschrieben; ein neuer Versuch ist ein neuer Vorgang.
        vorgangSchluessel.current = neuerSchluessel();
        beiKonflikt(fehler);
        return;
      }
      sitzung.vorgangFehler(fehler);
      if (sitzung.lesen().phase === "konflikt") setDialog(null);
      else setVorgangFehler(fehler);
    } finally {
      setLaedt(false);
    }
  };

  const kopf = maske.header;
  // Kennziffer aus dem Kopf der Maske; die Wettbewerbsliste nur, falls der Server keine mitgibt.
  const kennziffer = kopf.competition_code ?? kennziffern.get(kopf.competition_id) ?? null;
  const wer = `${kopf.start_number} · ${kopf.display_name ?? t("auswahl.ohne_name")}`;
  const pruefKopf: PruefKopf = {
    startnummer: kopf.start_number,
    name: kopf.display_name ?? t("auswahl.ohne_name"),
    wettbewerb: kopf.competition_name,
    kennziffer,
    klasse: kopf.class_name ?? kopf.class_short ?? null,
  };
  const wertung = basis.computed;
  const ergebnisText = wertung
    ? `${formatWert(wertung.score)} ${wertung.unit}`
    : formatWert(basis.score);

  // --- Prüfansicht vor dem Abschluss: frischer Stand des Servers, gesperrt ---
  const [pruefStand, setPruefStand] = useState<ErgebnisStand | null>(null);
  const [pruefLaedt, setPruefLaedt] = useState(false);
  const [pruefFehler, setPruefFehler] = useState<unknown>(null);
  /** Der Server hatte beim Abschließen andere Werte als die Prüfansicht (409): neu prüfen. */
  const [pruefGeaendert, setPruefGeaendert] = useState(false);
  const pruefLauf = useRef(0);

  const pruefungLaden = async () => {
    const lauf = ++pruefLauf.current;
    setPruefStand(null);
    setPruefFehler(null);
    setPruefLaedt(true);
    try {
      const frisch = await ladeMaske(turnierId, startId, form.capture_mode);
      if (lauf !== pruefLauf.current) return;
      // Neuerer Stand (z. B. anderes Gerät): der Sitzung melden, sie entscheidet wie immer.
      sitzung.serverStand(frisch.current);
      setPruefStand(frisch.current);
    } catch (fehler) {
      if (lauf === pruefLauf.current) setPruefFehler(fehler);
    } finally {
      if (lauf === pruefLauf.current) setPruefLaedt(false);
    }
  };

  const pruefungOeffnen = () => {
    setPruefGeaendert(false);
    // Erst wenn der Server alle Eingaben bestätigt hat: nichts wartet, nichts ist unterwegs.
    if (!sitzung.allesBestaetigt()) {
      zeigeMeldung({ ton: "warn", titel: t("abschluss.nicht_bereit") });
      return;
    }
    oeffneDialog("abschluss");
    void pruefungLaden();
  };

  const pruefungSchliessen = () => {
    pruefLauf.current += 1;
    setPruefStand(null);
    setPruefLaedt(false);
    setPruefGeaendert(false);
    setDialog(null);
  };

  /**
   * Schließt genau den Stand ab, der in der Prüfansicht zu sehen war: Sequenznummer und Ergebnis
   * gehen mit. Hat der Server inzwischen andere Werte (409), bleibt die Prüfansicht offen, sagt das
   * und lädt den aktuellen Stand neu.
   */
  const abschliessen = (geprueft: ErgebnisStand) =>
    vorgang(
      (schluessel) =>
        ergebnisApi.abschliessen(turnierId, startId, geprueft.seq, schluessel, {
          expected_seq: geprueft.seq,
          expected_score: geprueft.computed?.score ?? geprueft.score,
        }),
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
      () => {
        setPruefGeaendert(true);
        void pruefungLaden();
      },
    );

  const abbrechen = (grund: Abbruchgrund, text: string | null) =>
    vorgang(
      (schluessel) => ergebnisApi.abbrechen(turnierId, startId, grund, text, schluessel),
      () => {
        setVorgemerkt(null);
        zeigeMeldung({ ton: "info", titel: t("abbruch.erledigt", { wer }) });
        setVorgeschlagen(vorschlag());
      },
    );

  // --- Aufgeben: Vorabauskunft des Servers (abort_preview, aufgeben.ts) ---

  const [abbruchGrund, setAbbruchGrund] = useState<Abbruchgrund | null>(null);
  /** „Abbruch durch den Schützen“ ist eingetragen, das Aufgeben steht noch aus. */
  const [vorgemerkt, setVorgemerkt] = useState<readonly OffeneSerie[] | null>(null);

  // Die Auskunft der Maske gilt für deren Stand. Hat die Sitzung inzwischen einen neueren (eigene
  // Eingabe, Ereignis noch nicht da), fragt das Terminal den Server mit genau diesen Rohwerten
  // (`POST …/preview`, nichts wird gespeichert).
  // Beim aufgegebenen Start sagt dieselbe Auskunft, wie der Abbruch gewertet wird (mit Platz oder
  // ohne, und warum) – sie kommt mit der Maske, ohne eigene Abfrage der Rangliste.
  const offenerStart = !abgeschlossen && !abgebrochen;
  const aufgegeben = abgebrochen && basis.abort_reason === "dnf";
  const auskunftDerMaske = maske.current.seq === basis.seq;
  const basisRoh = basis.raw ?? {};
  const auskunftAbfrage = useQuery({
    ...vorschauAbfrage(turnierId, startId, basisRoh, stabil(basisRoh)),
    enabled:
      !auskunftDerMaske &&
      ((offenerStart && (dialog === "abbruch" || vorgemerkt !== null)) || abgebrochen),
  });
  /** `undefined`: wird geladen; `null`: keine (abgeschlossener Start) */
  const auskunftJetzt: AufgebenAuskunft | null | undefined = abgeschlossen
    ? null
    : auskunftDerMaske
      ? (maske.abort_preview ?? null)
      : auskunftAbfrage.data
        ? (auskunftAbfrage.data.abort_preview ?? null)
        : undefined;
  /** Auskunft zum Aufgeben (nur offene Starts) */
  const auskunft = offenerStart ? auskunftJetzt : null;
  /** Wie der schon abgebrochene Start gewertet wird (nur abgebrochene Starts) */
  const abbruchAuskunft = abgebrochen ? auskunftJetzt : null;
  // Angefangene Serien, an denen das Aufgeben laut Server scheitert.
  const offene = serienDerAuskunft(form, basis.computed, auskunft);
  const mehrereAbschnitte = form.sections.length > 1;

  const abbruchOeffnen = (grund: Abbruchgrund | null) => {
    setAbbruchGrund(grund);
    oeffneDialog("abbruch");
  };

  /**
   * Hauptaktion der Rückfrage bei offenen Serien: trägt „Abbruch durch den Schützen“ ein (wo die
   * Serie den Status kennt) und führt zum ersten noch leeren Feld dieser Serien. Aufgegeben wird
   * danach ausdrücklich mit „Jetzt aufgeben“, wenn der Server die Serien vollständig hat.
   */
  const serienAbschliessen = () => {
    const e = mitAbbruchStatus(sitzung.lesen().entwurf, offene);
    if (e !== sitzung.lesen().entwurf) sitzung.aendern(e);
    setDialog(null);
    setVorgemerkt(offene);
    tastaturZurueck();
    gehe(erstesFeldIn(liste(e), e, offene));
  };

  // Vom Schießstand mit „aufgegeben“ geschickt: Rückfrage einmal öffnen.
  const aufgebenGelesen = useRef(false);
  useEffect(() => {
    if (!aufgeben || aufgebenGelesen.current) return;
    aufgebenGelesen.current = true;
    onAufgebenGelesen?.();
    if (basis.status !== "final" && basis.status !== "aborted" && darfErfassen) {
      setAbbruchGrund("dnf");
      vorgangSchluessel.current = neuerSchluessel();
      setVorgangFehler(null);
      setDialog("abbruch");
    }
  }, [aufgeben, onAufgebenGelesen, basis.status, darfErfassen]);

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

  // --- Aufgegeben ohne Platz: Serienstatus nachtragen oder Abbruch zurücknehmen ---

  // Ob der aufgegebene Start einen Platz hat, sagt die Auskunft des Servers (mit Grund). Solange
  // sie lädt, stehen weder der Hinweis noch die Knöpfe da (sonst springen sie).
  const ohnePlatz = aufgegeben && !korrektur && abbruchAuskunft?.would_place === false;
  const abbruchWegeBereit = !aufgegeben || abbruchAuskunft !== undefined;
  // Serien, an denen die Wertung laut Server scheitert: dort setzt das Nachtragen an.
  const ohnePlatzSerien = ohnePlatz ? serienDerAuskunft(form, basis.computed, abbruchAuskunft) : [];

  /** Zu einer angefangenen Serie springen: beim offenen Start direkt, sonst als Korrektur. */
  const zuSerie = (pfad: string) => {
    setDialog(null);
    tastaturZurueck();
    if (abgebrochen && !korrektur) {
      sitzung.setzeAutomatisch(false);
      korrekturBeginnen();
    }
    const e = sitzung.lesen().entwurf;
    gehe(erstesFeldDerSerie(liste(e), e, pfad));
  };

  /**
   * Korrektur mit „Abbruch durch den Schützen“ in den offenen Serien vorbelegt. Gespeichert wird
   * erst mit Grund („Korrektur speichern“); der Start bleibt aufgegeben und wird danach mit dem
   * bisherigen Ergebnis gewertet.
   */
  const serienstatusNachtragen = () => {
    // Sofort: Im Korrekturmodus sendet das Terminal nichts von selbst.
    sitzung.setzeAutomatisch(false);
    const e = mitAbbruchStatus(sitzung.lesen().entwurf, ohnePlatzSerien);
    korrekturBeginnen();
    sitzung.aendern(e);
    tastaturZurueck();
    gehe(erstesFeldIn(liste(e), e, ohnePlatzSerien));
  };

  const zuruecknehmen = (grund: string) =>
    vorgang(
      async (schluessel) => {
        try {
          return await ergebnisApi.abbruchZuruecknehmen(
            turnierId,
            startId,
            grund,
            basis.seq,
            schluessel,
          );
        } catch (fehler) {
          // 409 ohne Stand: Der Start ist gar nicht mehr abgebrochen (anderes Gerät).
          if (fehler instanceof ApiFehler && fehler.status === 409) {
            neuLaden();
            throw t("zuruecknehmen.nicht_abgebrochen");
          }
          throw fehler;
        }
      },
      (stand) => {
        gestartet.current = false;
        setAktivId(null);
        setVorgeschlagen(null);
        setVorgemerkt(null);
        zeigeMeldung({
          ton: "erfolg",
          titel: t("zuruecknehmen.erledigt", { wer }),
          text: t(
            stand.status === "captured"
              ? "zuruecknehmen.erledigt_erfasst"
              : "zuruecknehmen.erledigt_angemeldet",
          ),
        });
      },
      (konflikt) => {
        // Inzwischen geändert (veraltete Sequenz): neuen Stand zeigen, erneut entscheiden lassen.
        sitzung.uebernehmen(konflikt.aktuell);
        setVorgangFehler(t("zuruecknehmen.konflikt"));
      },
    );

  // --- Anzeige ---

  // Zeiten über der Grenze der Formularbeschreibung gleich bei der Eingabe als Fehler am Feld
  // (der Server lehnt sie ab); dessen Meldung zum selben Feld ersetzt diese Klartext-Meldung.
  const grenzFehler: PfadMeldung[] = zeitenUeberGrenze(form, entwurf).map(({ ref, grenze }) => ({
    pfad: ref.id,
    meldung: t("feld.zeit_zu_gross", { grenze: zeitText(grenze) }),
  }));
  const grenzPfade = new Set(grenzFehler.map((f) => f.pfad));
  const fehler: PfadMeldung[] = [
    ...grenzFehler,
    ...zustand.feldFehler.filter((f) => !grenzPfade.has(f.pfad)),
  ];
  const warnungen: PfadMeldung[] = (wertung?.warnings ?? []).map((w) => ({
    pfad: normalerPfad(w.path),
    meldung: w.message,
  }));
  const uebrigeFehler = uebrigeMeldungen(form, fehler);
  const uebrigeWarnungen = uebrigeMeldungen(form, warnungen);
  const berechnet = zustand.ungespeichert || phase === "wartet" || phase === "sendet";
  const vollstaendig =
    (wertung?.complete ?? false) &&
    !zustand.ungespeichert &&
    phase === "gespeichert" &&
    grenzFehler.length === 0;
  const ringe = form.sections.some((a) => a.series.some((serie) => serie.shots !== null));
  const erfassungsNotizen = notizen(form, "erfassung");
  const titelAktiv = aktiv ? feldTitel(aktiv, form, t) : null;
  /** Alle Eingaben hat der Server (Grundlage für die offenen Serien und das Aufgeben). */
  const allesBeimServer = !zustand.ungespeichert && phase === "gespeichert";
  // Serien, die der Server für den gespeicherten Stand vollständig nennt, haben keine Lücke (z. B.
  // „Serie nicht beendet“ mit 3 von 5 Schuss). Solange Eingaben unterwegs sind, gilt die Maske.
  const fertig = allesBeimServer ? fertigeSerien(wertung) : new Set<string>();
  const luecken = wertung && !wertung.complete ? fehlstellen(form, ansicht, fertig) : [];
  const korrekturRoh = korrektur ? rohwerteAus(form, entwurf) : null;
  const korrekturAenderungen = korrekturRoh ? aenderungen(form, basis.raw ?? {}, korrekturRoh) : [];
  // Korrektur: der Server rechnet die geänderten Werte probeweise (nichts wird gespeichert).
  const mitVorschau = korrektur && zustand.ungespeichert;
  const vorschauJetzt = mitVorschau && korrekturRoh ? stabil(korrekturRoh) : "";
  const [vorschauRuhig] = useDebouncedValue(vorschauJetzt, 300);
  const vorschau = useQuery({
    ...vorschauAbfrage(turnierId, startId, korrekturRoh ?? {}, vorschauRuhig),
    enabled: mitVorschau && vorschauRuhig !== "" && vorschauRuhig === vorschauJetzt,
    placeholderData: keepPreviousData,
  });
  const vorschauWertung = mitVorschau ? (vorschau.data?.computed ?? null) : null;
  const vorschauAktuell =
    vorschauWertung !== null &&
    vorschauRuhig === vorschauJetzt &&
    !vorschau.isPlaceholderData &&
    !vorschau.isFetching;
  const naechsterVorschlag = vorgeschlagen ?? (abgeschlossen || abgebrochen ? vorschlag() : null);
  // Vorgemerktes Aufgeben: was in diesen Serien laut Eingabe noch fehlt.
  const vorgemerktPfade = new Set(
    (vorgemerkt ?? []).map((o) => serienPfad(o.abschnitt.id, o.serie.index)),
  );
  const vorgemerktFehlt = vorgemerkt
    ? fehlstellen(form, entwurf, fertig).filter((f) => vorgemerktPfade.has(f.pfad))
    : [];

  return (
    <>
      <section
        className={`panel ${s.flaeche}`}
        aria-label={t("flaeche")}
        data-korrektur={korrektur || undefined}
      >
        <Kopf maske={maske} basis={basis} kennziffer={kennziffer} />

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
        {fremdUm && !abgeschlossen && !abgebrochen && (
          <div className={s.banner} data-ton="info">
            <Users aria-hidden />
            <div>
              <strong>{t("fremd.hinweis_titel", { zeit: formatUhrzeit(fremdUm) })}</strong>
              <p>{t("fremd.hinweis_text")}</p>
            </div>
          </div>
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
              <p>
                {abgebrochen ? t("korrektur.modus_text_abgebrochen") : t("korrektur.modus_text")}
              </p>
              <AenderungsListe liste={korrekturAenderungen} />
            </div>
          </div>
        )}
        {vorgemerkt && !abgeschlossen && !abgebrochen && !korrektur && (
          <AufgebenVorgemerkt
            liste={vorgemerkt}
            status={gemeinsamerStatus(vorgemerkt)}
            fehlt={vorgemerktFehlt.flatMap((f) => f.felder)}
            bereit={allesBeimServer && auskunft !== undefined && offene.length === 0}
            wartet={!allesBeimServer || auskunft === undefined}
            darf={darfErfassen}
            onJetzt={() => abbruchOeffnen("dnf")}
            onDochNicht={() => setVorgemerkt(null)}
          />
        )}
        {ohnePlatz && abbruchAuskunft && (
          <OhnePlatzHinweis
            auskunft={abbruchAuskunft}
            liste={ohnePlatzSerien}
            name={pruefKopf.name}
            mehrereAbschnitte={mehrereAbschnitte}
            darf={darfKorrigieren}
            onNachtragen={serienstatusNachtragen}
            onKorrigieren={korrekturBeginnen}
            onZuruecknehmen={() => oeffneDialog("zuruecknehmen")}
            onZuSerie={zuSerie}
          />
        )}

        {(ringe || erfassungsNotizen.length > 0) && (
          <div className={s.artZeile}>
            {ringe && (
              <>
                <span className="h-label">{t("art.titel")}</span>
                <SegmentedControl
                  value={form.capture_mode}
                  onChange={(wert) => {
                    // Fokus zurück an die Seite: sonst landen Ziffern und Enter im Umschalter,
                    // und die Tastatur reagiert erst nach einem Tipp ins Feld.
                    if (document.activeElement instanceof HTMLElement)
                      document.activeElement.blur();
                    onArt(wert as Erfassungsart);
                  }}
                  data={[
                    { value: "series", label: t("art.series") },
                    { value: "shot", label: t("art.shot") },
                  ]}
                  disabled={wechselt}
                  className={s.artWahl}
                  aria-label={t("art.titel")}
                />
                {form.capture_mode !== maske.competition_capture_mode && (
                  <span className={s.klein} data-abweichung>
                    {t("art.abweichend", {
                      vorgabe: t(`art.${maske.competition_capture_mode}`),
                    })}
                  </span>
                )}
              </>
            )}
            {abgeleitet.size > 0 && (
              <p className={s.klein} data-abgeleitet-hinweis>
                {t("art.abgeleitet")}
              </p>
            )}
            {erfassungsNotizen.map((notiz) => (
              <p key={`${notiz.kind}-${notiz.text}`} className={s.klein}>
                {notiz.text}
              </p>
            ))}
          </div>
        )}

        <Maske
          form={form}
          entwurf={entwurf}
          wertung={vorschauWertung ?? wertung}
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
          abgeleitet={abgeleitet}
          veraltet={korrektur ? mitVorschau && !vorschauAktuell : berechnet}
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

        <Gesamtstand
          basis={basis}
          berechnet={berechnet}
          korrektur={korrektur}
          vorschau={vorschauWertung}
          vorschauAktuell={vorschauAktuell}
          vorschauFehler={mitVorschau && vorschau.isError}
          notizen={notizen(form, "gleichstand")}
        />

        <Verlauf
          form={form}
          turnierId={turnierId}
          startId={startId}
          offen={abgeschlossen}
          key={`${abgeschlossen}`}
        />
      </section>

      <aside className={s.eingabe} aria-label={t("eingabe")}>
        {(korrektur || (!abgeschlossen && !abgebrochen)) && (
          <Tastenfeld
            aktiv={aktiv}
            titel={titelAktiv}
            eingabe={eingabe}
            wert={aktiv ? wertAus(entwurf, aktiv) : undefined}
            schussPuffer={schussPuffer}
            gesperrt={!bearbeitbar}
            hinweis={hinweis}
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
              <p
                className={s.aktionHinweis}
                data-erledigt={abgeschlossen ? "final" : "abgebrochen"}
              >
                {abgeschlossen
                  ? t("abschluss.ist", { ergebnis: ergebnisText })
                  : t("abbruch.ist", {
                      grund: basis.abort_reason ? t(`abbruch.lang.${basis.abort_reason}`) : "",
                    })}
              </p>
              {abgebrochen && basis.abort_remark && (
                <p className={s.klein} data-bemerkung>
                  {t("abbruch.bemerkung_ist", { text: basis.abort_remark })}
                </p>
              )}
              {/* Wie der Abbruch gewertet wird (Text des Servers); ohne Platz steht er im Hinweis. */}
              {abgebrochen && !ohnePlatz && abbruchAuskunft?.message_de && (
                <p className={s.klein} data-abbruch-auskunft>
                  {abbruchAuskunft.message_de}
                </p>
              )}
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
              {/* Ohne Platz stehen beide Wege mit Erklärung im Hinweis links. */}
              {abgebrochen && darfKorrigieren && !ohnePlatz && abbruchWegeBereit && (
                <>
                  <Button
                    variant="default"
                    leftSection={<Undo2 aria-hidden />}
                    onClick={() => oeffneDialog("zuruecknehmen")}
                  >
                    {t("zuruecknehmen.knopf")}
                  </Button>
                  <Button
                    variant="default"
                    leftSection={<PencilLine aria-hidden />}
                    onClick={korrekturBeginnen}
                  >
                    {t("korrektur.knopf")}
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
                onClick={pruefungOeffnen}
              >
                {t("abschluss.knopf")}
              </Button>
              <SendeStatus zustand={zustand} onErneut={() => sitzung.erneut()} />
              <p className={s.aktionHinweis} aria-live="polite">
                {vollstaendig
                  ? t("abschluss.bereit")
                  : luecken.length > 0
                    ? t("abschluss.fehlt")
                    : wertung
                      ? (restText(wertung.progress, t, zaehltTreffer(wertung.unit)) ??
                        t("abschluss.warten"))
                      : t("abschluss.warten")}
              </p>
              {!vollstaendig && luecken.length > 0 && (
                <ul className={s.luecken}>
                  {luecken.map((luecke) => {
                    const abschnitt = form.sections.find((a) => a.id === luecke.abschnitt);
                    const ort =
                      luecke.serie !== null
                        ? (abschnitt?.series.find((x) => x.index === luecke.serie)?.label ?? "")
                        : (abschnitt?.name ?? "");
                    return (
                      <li key={luecke.pfad}>
                        <button
                          type="button"
                          className={s.luecke}
                          disabled={!bearbeitbar}
                          onClick={() => feldWaehlen(luecke.ziel)}
                        >
                          {t("abschluss.fehlt_ort", { ort, felder: luecke.felder.join(", ") })}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
              <div className={s.trenner} />
              <Button
                variant="subtle"
                color="red"
                leftSection={<Ban aria-hidden />}
                disabled={!darfErfassen}
                onClick={() => abbruchOeffnen(null)}
              >
                {t("abbruch.knopf")}
              </Button>
            </>
          )}
        </section>
      </aside>

      {dialog === "abschluss" && (
        <PruefDialog
          offen
          laedt={laedt}
          fehler={vorgangFehler}
          onSchliessen={pruefungSchliessen}
          form={form}
          kopf={pruefKopf}
          stand={pruefStand}
          standLaedt={pruefLaedt}
          standFehler={pruefFehler}
          geaendert={pruefGeaendert}
          onNeuLaden={() => void pruefungLaden()}
          lokal={rohwerteAus(form, entwurf)}
          onBestaetigen={(geprueft) => void abschliessen(geprueft)}
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
          name={pruefKopf.name}
          startGrund={abbruchGrund}
          auskunft={auskunft}
          offeneSerien={offene}
          onSerienAbschliessen={serienAbschliessen}
          onZuSerie={zuSerie}
          mehrereAbschnitte={mehrereAbschnitte}
          bereit={allesBeimServer || phase === "abgelehnt"}
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
          text={t(abgebrochen ? "korrektur.text_abgebrochen" : "korrektur.text", { wer })}
          bestaetigen={t("korrektur.bestaetigen")}
        >
          <AenderungsListe liste={korrekturAenderungen} />
        </GrundDialog>
      )}
      {dialog === "zuruecknehmen" && (
        <GrundDialog
          offen
          laedt={laedt}
          fehler={vorgangFehler}
          onSchliessen={() => setDialog(null)}
          onBestaetigen={(grund) => void zuruecknehmen(grund)}
          titel={t("zuruecknehmen.titel")}
          text={t("zuruecknehmen.text", {
            wer,
            grund: basis.abort_reason ? t(`abbruch.lang.${basis.abort_reason}`) : "",
          })}
          bestaetigen={t("zuruecknehmen.bestaetigen")}
        >
          <ul className={s.danachListe}>
            <li>
              {gleicheRohwerte(basis.raw, {})
                ? t("zuruecknehmen.danach_angemeldet")
                : t("zuruecknehmen.danach_erfasst")}
            </li>
            <li>{t("zuruecknehmen.danach_stand")}</li>
            <li>{t("zuruecknehmen.danach_verlauf")}</li>
          </ul>
        </GrundDialog>
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
          onBestaetigen={() => {
            sitzung.ablageLeeren();
            blocker.proceed();
          }}
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
    ref.schuss !== undefined
      ? t(istJeZiel(ref.feld) ? "tasten.ziel" : "tasten.schuss", { nr: ref.schuss + 1 })
      : ref.feld.label;
  return ref.ungewertet ? `${ort} · ${was} · ${t("feld.ungewertet")}` : `${ort} · ${was}`;
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
  const vorgabenListe = vorgaben(maske.form);
  const zeile = [
    kopf.club,
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
          {(kopf.class_name || kopf.class_short) && (
            <strong className={s.klasse}>
              {t("auswahl.klasse", { klasse: kopf.class_name ?? kopf.class_short })}
            </strong>
          )}
          <span className="gedaempft">
            {maske.form.variant_name !== "Standard" ? `${maske.form.variant_name} · ` : ""}
            {maske.form.max_rings != null
              ? t("kopf.max", {
                  einheit: ringEinheit(maske.form.unit, t),
                  max: formatWert(maske.form.max_rings),
                })
              : t(`kopf.richtung.${maske.form.direction}`)}
          </span>
          {vorgabenListe.length > 0 && (
            <ul className={s.vorgaben} aria-label={t("vorgaben.titel")}>
              {vorgabenListe.map((vorgabe) =>
                vorgabe.art === "aufgelegt" ? (
                  <li key="aufgelegt">{t("vorgaben.aufgelegt")}</li>
                ) : (
                  <li key={vorgabe.kind}>{vorgabe.text}</li>
                ),
              )}
            </ul>
          )}
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
  vorschau,
  vorschauAktuell,
  vorschauFehler,
  notizen: gleichstandNotizen,
}: {
  basis: ErgebnisStand;
  berechnet: boolean;
  korrektur: boolean;
  /** Korrektur: Probe-Rechnung des Servers für die geänderten Werte (nichts gespeichert) */
  vorschau: Wertung | null;
  vorschauAktuell: boolean;
  vorschauFehler: boolean;
  /** Notizen des Servers zum Gleichstand (Höchstergebnis, Stechen, manuell) */
  notizen: readonly Notiz[];
}) {
  const { t } = useTranslation("erfassung");
  const [wegOffen, setWegOffen] = useState(false);
  const bisher = basis.computed;
  const wertung = (korrektur && vorschau) || bisher;
  if (!wertung) return null;
  // Korrektur mit Änderungen: Vorschau oder „wird berechnet“; ohne Änderungen das gespeicherte.
  const korrekturGeaendert = korrektur && (vorschau !== null || berechnet);
  const nochNichts = gleicheRohwerte(basis.raw, {});
  const nebenwerte: { name: string; wert: string }[] = [];
  const treffer = zaehltTreffer(wertung.unit);
  // Zehner und Innenzehner nur, wenn der Server sie liefert (bei Trefferzählung `null`).
  const zehnerDa = wertung.rings !== null;
  if (wertung.tens !== null && zehnerDa) {
    nebenwerte.push({ name: t("gesamt.zehner"), wert: formatWert(wertung.tens) });
  }
  if (wertung.inner_tens !== null && zehnerDa) {
    nebenwerte.push({ name: t("gesamt.innenzehner"), wert: formatWert(wertung.inner_tens) });
  }
  if (wertung.penalty_cs) {
    nebenwerte.push({ name: t("gesamt.zuschlag"), wert: formatZeit(wertung.penalty_cs) });
  }
  if (wertung.deduction !== null && Number(wertung.deduction) !== 0) {
    nebenwerte.push({ name: t("gesamt.abzug"), wert: formatWert(wertung.deduction) });
  }
  const rechnet = korrektur ? korrekturGeaendert && !vorschauAktuell : berechnet;
  return (
    <section className={s.gesamt} aria-live="polite" aria-labelledby="erf-gesamt">
      <div className={s.gesamtZeile}>
        <div className={s.gesamtHaupt} data-veraltet={rechnet || !wertung.complete || undefined}>
          <span className="h-label" id="erf-gesamt">
            {t("gesamt.titel")}
          </span>
          <strong className="num">{nochNichts ? "–" : formatWert(wertung.score)}</strong>
          <span className={s.gesamtEinheit}>{wertung.unit}</span>
          {/* Nicht nur blasser: auch in Worten, dass die Zahl gleich neu kommt. */}
          {rechnet && wertung.complete && !nochNichts && (
            <span className={s.gesamtEinheit}>{t("gesamt.wird_berechnet")}</span>
          )}
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
        <span className="num">{fortschrittText(wertung.progress, t, treffer)}</span>
        {(korrektur ? korrekturGeaendert && !vorschauAktuell && !vorschauFehler : berechnet) && (
          <span className={s.berechnet}>
            <Loader size={12} aria-hidden />
            {t("gesamt.berechnet")}
          </span>
        )}
        {korrektur && vorschau && bisher && (
          <span className={s.berechnet}>
            {t("korrektur.vorschau", {
              bisher: `${formatWert(bisher.score)} ${bisher.unit}`,
            })}
          </span>
        )}
        {korrektur && vorschauFehler && (
          <span className={s.berechnet}>{t("korrektur.erst_danach")}</span>
        )}
        {wertung.tie_breakers_missing_items.length > 0 && (
          <span className={s.klein}>
            {t("gesamt.gleichstand_fehlt", {
              was: wertung.tie_breakers_missing_items.map((kriterium) => kriterium.text).join(", "),
            })}
          </span>
        )}
      </p>
      {gleichstandNotizen.length > 0 && (
        <ul className={s.notizen} aria-label={t("gesamt.notizen")}>
          {gleichstandNotizen.map((notiz) => (
            <li key={`${notiz.kind}-${notiz.text}`}>{notiz.text}</li>
          ))}
        </ul>
      )}
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

/**
 * Nach „Abbruch durch den Schützen eintragen“: sagt, was in der Serie noch fehlt, und bietet
 * „Jetzt aufgeben“ an, sobald der Server die Serie vollständig hat.
 */
function AufgebenVorgemerkt({
  liste,
  status,
  fehlt,
  bereit,
  wartet,
  darf,
  onJetzt,
  onDochNicht,
}: {
  liste: readonly OffeneSerie[];
  status: string | null;
  /** Bezeichnungen der fehlenden Felder in diesen Serien (laut Eingabe) */
  fehlt: readonly string[];
  bereit: boolean;
  wartet: boolean;
  darf: boolean;
  onJetzt: () => void;
  onDochNicht: () => void;
}) {
  const { t } = useTranslation("erfassung");
  const orte = orteText(liste, t("abbruch.und"));
  const felder = [...new Set(fehlt)].join(", ");
  const text = bereit
    ? t("abbruch.vorgemerkt.bereit")
    : felder
      ? status
        ? t("abbruch.vorgemerkt.fehlt", { orte, status, felder })
        : t("abbruch.vorgemerkt.fehlt_ohne_status", { orte, felder })
      : t("abbruch.vorgemerkt.wartet");
  return (
    <div className={s.banner} data-ton="info" data-aufgeben-vorgemerkt>
      <Ban aria-hidden />
      <div>
        <strong>{t("abbruch.vorgemerkt.titel")}</strong>
        <p aria-live="polite">{wartet && !felder ? t("abbruch.vorgemerkt.wartet") : text}</p>
      </div>
      <div className={s.bannerAktionen}>
        <Button
          variant="light"
          color="red"
          leftSection={<Ban aria-hidden />}
          disabled={!bereit || !darf}
          onClick={onJetzt}
        >
          {t("abbruch.vorgemerkt.jetzt")}
        </Button>
        <Button variant="subtle" onClick={onDochNicht}>
          {t("abbruch.vorgemerkt.doch_nicht")}
        </Button>
      </div>
    </div>
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
              fortschritt: fortschrittText(wertung.progress, t, zaehltTreffer(wertung.unit)),
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
