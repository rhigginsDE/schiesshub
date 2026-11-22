import { Button, NumberInput, Select } from "@mantine/core";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ArrowLeft,
  ArrowRight,
  Clock,
  IdCard,
  MapPin,
  Pencil,
  Shield,
  Trash2,
  TriangleAlert,
  Undo2,
} from "lucide-react";
import { type FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { klassenAbfrage } from "../../api/abfragen";
import { ApiFehler } from "../../api/client";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { FehlerHinweis, useFehlerText } from "../../components/FehlerHinweis";
import { formatGeld } from "../../components/geld";
import { Stepper } from "../../components/Stepper";
import { formatUhrzeit, formatZahl } from "../../lib/format";
import { feldFehlerFuer } from "../turnier/senden";
import type { Stand, TurnierUebersicht, Wettbewerb } from "../turnier/typen";
import s from "./AnmeldungSeite.module.css";
import {
  type Anmeldung,
  type AnmeldungAenderung,
  type Durchgang,
  durchgaengeAbfrage,
  naechsterPlatzAbfrage,
  type Start,
  startsSchluessel,
  useAnmeldungLoeschen,
  useStartStornieren,
} from "./api";
import { type BuchungsErgebnis, BuchungsFehler, buchen, type Platz } from "./buchen";
import {
  type Betrag,
  betragVorschau,
  gebuchteStarts,
  loeschbar,
  mengenHinweis,
  naechsteStartnummer,
  nochBuchbar,
  type Sperre,
  sperreFuer,
  statusAnzeige,
  stornoSperre,
  summe,
} from "./logik";
import { PlatzWahl } from "./PlatzWahl";

/** Die gewählte Person, egal ob aus der Personensuche oder aus einer Anmeldung. */
export interface Schuetze {
  id: string;
  name: string;
  verein: string | null;
  mitgliedsnummer: string | null;
  /** Anzeigename nach Einstellung der Person; `null` = verborgen */
  anzeige: string | null;
}

interface AnmeldungFormularProps {
  uebersicht: TurnierUebersicht;
  schuetze: Schuetze;
  /** Vorhandene Anmeldung der Person im Turnier (live vom Server) */
  anmeldung: Anmeldung | null;
  anmeldungen: readonly Anmeldung[];
  /** Gespeichert; `aenderung` = was an Klasse/Startnummer einer vorhandenen Anmeldung geändert wurde */
  onFertig: (ergebnis: BuchungsErgebnis, aenderung: AnmeldungAenderung) => void;
  onZurueck: () => void;
  onGeloescht: () => void;
  onUngespeichert: (ungespeichert: boolean) => void;
}

const ANMELDE_FELDER = ["class_id", "start_number"] as const;

export function kennziffer(wettbewerb: Pick<Wettbewerb, "catalog_code">): string {
  return wettbewerb.catalog_code ?? "—";
}

/** Linke Spalte: Person, Klasse, Startnummer und Starts buchen. */
export function AnmeldungFormular({
  uebersicht,
  schuetze,
  anmeldung,
  anmeldungen,
  onFertig,
  onZurueck,
  onGeloescht,
  onUngespeichert,
}: AnmeldungFormularProps) {
  const { t, i18n } = useTranslation("anmeldung");
  const sprache = i18n.language;
  const queryClient = useQueryClient();
  const fehlerText = useFehlerText();
  const titelId = useId();
  const klasseFeld = useRef<HTMLInputElement>(null);
  const turnierId = uebersicht.id;
  const waehrung = uebersicht.settings.currency;
  const geld = (cents: number) => formatGeld(cents, waehrung, sprache);

  // Eingaben. Bei Live-Aktualisierung (neue Daten vom Server) bleiben sie stehen.
  const [klasseId, setKlasseId] = useState<string | null>(anmeldung?.class_id ?? null);
  const [startnummer, setStartnummer] = useState<number | null>(anmeldung?.start_number ?? null);
  const [anzahl, setAnzahl] = useState<Record<string, number>>({});
  const [plaetze, setPlaetze] = useState<Record<string, Platz | null>>({});
  const [platzWahl, setPlatzWahl] = useState<Wettbewerb | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<BuchungsFehler | null>(null);
  const [geprueft, setGeprueft] = useState(false);
  const [loeschenOffen, setLoeschenOffen] = useState(false);
  const [storno, setStorno] = useState<Start | null>(null);
  // Die Anmeldung, die beim Speichern entstand, falls ein späterer Schritt scheiterte.
  const vorhanden = anmeldung ?? fehler?.anmeldung ?? null;

  const loeschen = useAnmeldungLoeschen(turnierId);
  const stornieren = useStartStornieren(turnierId);

  const klassen = uebersicht.classes;
  const klasse = klassen.find((k) => k.id === klasseId) ?? null;
  const staende = useMemo(
    () => new Map(uebersicht.ranges.map((stand) => [stand.id, stand])),
    [uebersicht.ranges],
  );
  const wettbewerbe = useMemo(
    () => [...uebersicht.competitions].sort((a, b) => a.sort - b.sort),
    [uebersicht.competitions],
  );
  const nachId = useMemo(() => new Map(wettbewerbe.map((w) => [w.id, w])), [wettbewerbe]);

  // Hilfetext der Klasse aus dem Katalog (Altersgrenzen), falls ein Verband bekannt ist.
  const verband = wettbewerbe.find((w) => w.catalog_federation)?.catalog_federation ?? null;
  const katalogKlassen = useQuery({ ...klassenAbfrage(verband ?? ""), enabled: verband !== null });
  const klassenHilfe = klasse
    ? (katalogKlassen.data?.find((k) => k.id === klasse.code)?.alter_hilfe ?? null)
    : null;

  // Durchgänge der Zeitplan-Stände, um gebuchte Plätze mit Uhrzeit zu zeigen.
  const zeitplanStaende = [
    ...new Set(
      wettbewerbe
        .filter((w) => w.planning === "schedule" && w.range_id)
        .map((w) => w.range_id as string),
    ),
  ];
  const durchgangsAbfragen = useQueries({
    queries: zeitplanStaende.map((id) => durchgaengeAbfrage(turnierId, id)),
  });
  const durchgaenge = new Map<string, Durchgang>();
  for (const abfrage of durchgangsAbfragen) {
    for (const durchgang of abfrage.data ?? []) durchgaenge.set(durchgang.id, durchgang);
  }

  // Zeilen mit Grenzen, Sperren und Betrag. Was der Server inzwischen gebucht hat, begrenzt neu.
  const zeilen = wettbewerbe.map((wettbewerb) => {
    const bereits = gebuchteStarts(vorhanden, wettbewerb.id);
    const sperre = sperreFuer(wettbewerb, klasse, bereits);
    const frei = sperre ? 0 : nochBuchbar(wettbewerb, bereits);
    const neu = Math.min(anzahl[wettbewerb.id] ?? 0, frei);
    return {
      wettbewerb,
      bereits,
      sperre,
      frei,
      neu,
      betrag: betragVorschau(wettbewerb, bereits, neu),
    };
  });
  const gesamt = summe(zeilen.map((z) => z.betrag));
  const neueStarts = zeilen.reduce((n, z) => n + z.neu, 0);
  const aenderung: AnmeldungAenderung = {};
  if (vorhanden) {
    if (klasseId && klasseId !== vorhanden.class_id) aenderung.class_id = klasseId;
    if (startnummer !== null && startnummer !== vorhanden.start_number) {
      aenderung.start_number = startnummer;
    }
  }
  const hatAenderung = Object.keys(aenderung).length > 0;
  const ungespeichert = neueStarts > 0 || hatAenderung || (!vorhanden && klasseId !== null);

  useEffect(() => onUngespeichert(ungespeichert), [ungespeichert, onUngespeichert]);
  useEffect(() => () => onUngespeichert(false), [onUngespeichert]);

  // Neue Person: gleich die Klasse wählen lassen.
  useEffect(() => {
    if (!anmeldung) klasseFeld.current?.focus();
  }, [anmeldung]);

  const vorschauNummer = naechsteStartnummer(
    anmeldungen,
    uebersicht.settings.first_start_number ?? 1,
  );

  const setzeAnzahl = (wettbewerbId: string, wert: number) => {
    setAnzahl((alt) => ({ ...alt, [wettbewerbId]: wert }));
    if (fehler?.wettbewerbId === wettbewerbId) setFehler(null);
  };

  const absenden = async (ereignis?: FormEvent) => {
    ereignis?.preventDefault();
    setGeprueft(true);
    if (!klasseId || laeuft) return;
    if (vorhanden && neueStarts === 0 && !hatAenderung) return;
    setLaeuft(true);
    setFehler(null);
    try {
      const ergebnis = await buchen({
        turnierId,
        anmeldung: vorhanden,
        personId: schuetze.id,
        klasseId,
        startnummer: vorhanden ? null : startnummer,
        aenderung,
        zeilen: zeilen.map((z) => ({
          wettbewerb: z.wettbewerb,
          anzahl: z.neu,
          platz: plaetze[z.wettbewerb.id] ?? undefined,
        })),
      });
      onFertig(ergebnis, aenderung);
    } catch (fehlerWert) {
      if (!(fehlerWert instanceof BuchungsFehler)) throw fehlerWert;
      // Was gebucht ist, aus den Eingaben nehmen; der Rest bleibt für den nächsten Versuch.
      const gebucht: Record<string, number> = {};
      for (const start of fehlerWert.gebucht) {
        gebucht[start.competition_id] = (gebucht[start.competition_id] ?? 0) + 1;
      }
      setAnzahl((alt) =>
        Object.fromEntries(
          Object.entries(alt).map(([id, n]) => [id, Math.max(0, n - (gebucht[id] ?? 0))]),
        ),
      );
      setFehler(fehlerWert);
    } finally {
      setLaeuft(false);
      void queryClient.invalidateQueries({ queryKey: startsSchluessel.turnier(turnierId) });
    }
  };

  // Strg+Enter speichert von überall auf der Seite (nicht aus Dialogen heraus).
  const absendenRef = useRef(absenden);
  absendenRef.current = absenden;
  useEffect(() => {
    const beiTaste = (ereignis: globalThis.KeyboardEvent) => {
      if (ereignis.key !== "Enter" || !(ereignis.ctrlKey || ereignis.metaKey)) return;
      if (document.querySelector("[role=dialog]")) return;
      ereignis.preventDefault();
      void absendenRef.current();
    };
    window.addEventListener("keydown", beiTaste);
    return () => window.removeEventListener("keydown", beiTaste);
  }, []);

  // Fehler beim Anmelden feldgenau; 409 zur Startnummer gehört an das Feld.
  const anmeldeFehler =
    fehler?.schritt === "anmeldung" ? feldFehlerFuer(fehler.ursache, ANMELDE_FELDER) : {};
  if (
    fehler?.schritt === "anmeldung" &&
    fehler.ursache instanceof ApiFehler &&
    fehler.ursache.art === "konflikt" &&
    /startnummer/i.test(fehler.ursache.detail ?? "")
  ) {
    anmeldeFehler.start_number = fehlerText(fehler.ursache);
    delete anmeldeFehler[""];
  }
  const klasseFehlt = geprueft && !klasseId;

  const knopfText = !vorhanden
    ? t("aktion.anmelden")
    : neueStarts > 0
      ? t("aktion.buchen")
      : hatAenderung
        ? t("aktion.speichern")
        : t("aktion.buchen");
  const knopfGesperrt = vorhanden !== null && neueStarts === 0 && !hatAenderung;

  return (
    <form
      className={`panel ${s.formular}`}
      onSubmit={(ereignis) => void absenden(ereignis)}
      noValidate
      aria-labelledby={titelId}
    >
      <div className={s.formKopf}>
        <Button
          variant="subtle"
          color="gray"
          size="compact-md"
          leftSection={<ArrowLeft aria-hidden />}
          onClick={onZurueck}
        >
          {t("schuetze.andere")}
        </Button>
        {vorhanden ? (
          <Chip ton="gruen">{t("schuetze.angemeldet")}</Chip>
        ) : (
          <Chip ton="info">{t("schuetze.neue_anmeldung")}</Chip>
        )}
      </div>

      {/* Person */}
      <div className={`inset ${s.person}`}>
        <div className={s.nr}>
          <span className="h-label">{t("person.startnummer")}</span>
          <b className="num">
            {vorhanden
              ? formatZahl(vorhanden.start_number, {}, sprache)
              : startnummer !== null
                ? formatZahl(startnummer, {}, sprache)
                : formatZahl(vorschauNummer, {}, sprache)}
          </b>
        </div>
        <div className={s.wer}>
          <strong id={titelId}>{schuetze.name}</strong>
          <div className={s.fakten}>
            <span>
              <Shield aria-hidden />
              {schuetze.verein ?? t("person.ohne_verein")}
            </span>
            {schuetze.mitgliedsnummer && (
              <span>
                <IdCard aria-hidden />
                <span className="num">
                  {t("person.mitgliedsnummer", { nr: schuetze.mitgliedsnummer })}
                </span>
              </span>
            )}
            {schuetze.anzeige !== schuetze.name && (
              <span>
                {schuetze.anzeige
                  ? t("person.anzeige_als", { name: schuetze.anzeige })
                  : t("person.anzeige_verborgen")}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Klasse und Startnummer */}
      <div className={s.felder}>
        <Select
          ref={klasseFeld}
          size="md"
          label={t("klasse.titel")}
          placeholder={t("klasse.platzhalter")}
          description={klassenHilfe ?? (klassen.length === 0 ? t("klasse.keine") : undefined)}
          data={klassen.map((k) => ({ value: k.id, label: `${k.short} · ${k.name}` }))}
          value={klasseId}
          onChange={(wert) => {
            setKlasseId(wert);
            if (fehler?.schritt === "anmeldung") setFehler(null);
          }}
          searchable
          selectFirstOptionOnChange
          allowDeselect={false}
          nothingFoundMessage={t("klasse.nichts")}
          error={klasseFehlt ? t("klasse.fehlt") : anmeldeFehler.class_id}
          required
          comboboxProps={{ withinPortal: true }}
        />
        <NumberInput
          size="md"
          label={t("person.startnummer")}
          description={vorhanden ? t("person.startnummer_aendern") : t("person.startnummer_auto")}
          placeholder={formatZahl(vorschauNummer, {}, sprache)}
          min={1}
          allowDecimal={false}
          allowNegative={false}
          hideControls
          value={startnummer ?? ""}
          onChange={(wert) => {
            setStartnummer(typeof wert === "number" ? wert : null);
            if (fehler?.schritt === "anmeldung") setFehler(null);
          }}
          classNames={{ input: "num" }}
          error={anmeldeFehler.start_number}
          className={s.nummernFeld}
        />
      </div>
      {fehler?.schritt === "anmeldung" && anmeldeFehler[""] && (
        <FehlerHinweis fehler={fehler.ursache} text={anmeldeFehler[""]} />
      )}

      {/* Starts buchen */}
      <section className={s.buchen} aria-labelledby={`${titelId}-buchen`}>
        <h3 className="h-section" id={`${titelId}-buchen`}>
          {t("buchen.titel")}
        </h3>
        {wettbewerbe.length === 0 ? (
          <div className={s.leerHinweis}>
            <p className="gedaempft">{t("buchen.keine")}</p>
            <Button
              renderRoot={(props) => (
                <Link {...props} to={`/turnier/${turnierId}`} search={{ bereich: "wettbewerbe" }} />
              )}
              variant="default"
              rightSection={<ArrowRight aria-hidden />}
            >
              {t("buchen.keine_link")}
            </Button>
          </div>
        ) : (
          <ul className={s.zeilen}>
            {zeilen.map((zeile) => (
              <WettbewerbZeile
                key={zeile.wettbewerb.id}
                turnierId={turnierId}
                anmeldungId={vorhanden?.id ?? null}
                stand={
                  zeile.wettbewerb.range_id ? staende.get(zeile.wettbewerb.range_id) : undefined
                }
                {...zeile}
                platz={plaetze[zeile.wettbewerb.id] ?? null}
                geld={geld}
                fehler={
                  fehler?.schritt === "start" && fehler.wettbewerbId === zeile.wettbewerb.id
                    ? fehler.ursache
                    : null
                }
                onAnzahl={(wert) => setzeAnzahl(zeile.wettbewerb.id, wert)}
                onPlatzWaehlen={() => setPlatzWahl(zeile.wettbewerb)}
                onPlatzZuruecksetzen={() =>
                  setPlaetze((alt) => ({ ...alt, [zeile.wettbewerb.id]: null }))
                }
                durchgaenge={durchgaenge}
              />
            ))}
          </ul>
        )}
      </section>

      {/* Summe und Hauptaktion */}
      <div className={s.kasse}>
        <div className={s.summe}>
          <span className="h-label">{t("summe.titel")}</span>
          <b className="num" aria-live="polite">
            {geld(gesamt.cents)}
          </b>
          <span className="gedaempft">{summenText(t, gesamt, neueStarts, !vorhanden)}</span>
        </div>
        <div className={s.aktionen}>
          <span className={s.tasten}>
            <kbd>Strg</kbd> + <kbd>Enter</kbd> {t("aktion.tasten_speichern")} · <kbd>Esc</kbd>{" "}
            {t("aktion.tasten_zurueck")}
          </span>
          <Button type="submit" size="lg" loading={laeuft} disabled={knopfGesperrt}>
            {knopfText}
          </Button>
        </div>
      </div>
      {fehler?.schritt === "start" && fehler.anmeldung && fehler.gebucht.length > 0 && (
        <p className={s.teilweise} role="status">
          <TriangleAlert aria-hidden />
          {t("fehler.teilweise", { count: fehler.gebucht.length })}
        </p>
      )}

      {/* Gebuchte Starts */}
      {vorhanden && (
        <GebuchteStarts
          anmeldung={vorhanden}
          wettbewerbe={nachId}
          durchgaenge={durchgaenge}
          geld={geld}
          onStornieren={(start) => {
            stornieren.reset();
            setStorno(start);
          }}
          onLoeschen={() => {
            loeschen.reset();
            setLoeschenOffen(true);
          }}
        />
      )}

      {platzWahl?.range_id && (
        <PlatzWahl
          turnierId={turnierId}
          wettbewerb={platzWahl}
          stand={staende.get(platzWahl.range_id)}
          gewaehlt={plaetze[platzWahl.id] ?? null}
          onWahl={(platz) => {
            setPlaetze((alt) => ({ ...alt, [platzWahl.id]: platz }));
            setPlatzWahl(null);
          }}
          onSchliessen={() => setPlatzWahl(null)}
        />
      )}

      <Bestaetigung
        offen={storno !== null}
        titel={t("storno.titel")}
        text={
          storno
            ? t("storno.text", {
                wettbewerb: nachId.get(storno.competition_id)?.name ?? "",
                versuch: storno.attempt,
                betrag: geld(storno.fee_cents),
              })
            : ""
        }
        bestaetigen={t("storno.bestaetigen")}
        abbrechen={t("storno.abbrechen")}
        ton="gefahr"
        laedt={stornieren.isPending}
        fehler={stornieren.isError ? fehlerText(stornieren.error) : undefined}
        onBestaetigen={() =>
          storno && stornieren.mutate(storno.id, { onSuccess: () => setStorno(null) })
        }
        onSchliessen={() => setStorno(null)}
      />

      <Bestaetigung
        offen={loeschenOffen}
        titel={t("loeschen.titel")}
        text={t("loeschen.text", {
          name: schuetze.name,
          nr: vorhanden?.start_number ?? "",
          count: vorhanden?.starts.length ?? 0,
        })}
        bestaetigen={t("loeschen.bestaetigen")}
        abbrechen={t("loeschen.abbrechen")}
        ton="gefahr"
        laedt={loeschen.isPending}
        fehler={loeschen.isError ? fehlerText(loeschen.error) : undefined}
        onBestaetigen={() =>
          vorhanden &&
          loeschen.mutate(vorhanden.id, {
            onSuccess: () => {
              setLoeschenOffen(false);
              onGeloescht();
            },
          })
        }
        onSchliessen={() => setLoeschenOffen(false)}
      />
    </form>
  );
}

type T = ReturnType<typeof useTranslation>["t"];

function summenText(t: T, gesamt: Betrag, neu: number, neueAnmeldung: boolean): string {
  if (neu === 0) return t(neueAnmeldung ? "summe.nichts_neu" : "summe.nichts");
  const teile = [t("summe.starts", { count: neu })];
  if (gesamt.nachkauf > 0) teile.push(t("summe.davon_nachkauf", { count: gesamt.nachkauf }));
  return teile.join(" · ");
}

function sperrText(t: T, sperre: Sperre): string {
  if (sperre.art === "klasse") return t("buchen.sperre_klasse", { klasse: sperre.klasse });
  if (sperre.art === "ohne_klasse") return t("buchen.sperre_ohne_klasse");
  return t("buchen.sperre_voll", { count: sperre.grenze });
}

function platzText(
  t: T,
  sprache: string,
  durchgang: Pick<Durchgang, "number" | "starts_at">,
  bahn: number,
): string {
  return t("platz.kurz", {
    zeit: formatUhrzeit(new Date(durchgang.starts_at), sprache),
    nummer: durchgang.number,
    bahn,
  });
}

interface WettbewerbZeileProps {
  turnierId: string;
  anmeldungId: string | null;
  wettbewerb: Wettbewerb;
  stand: Stand | undefined;
  bereits: number;
  sperre: Sperre | null;
  frei: number;
  neu: number;
  betrag: Betrag;
  platz: Platz | null;
  durchgaenge: Map<string, Durchgang>;
  geld: (cents: number) => string;
  fehler: unknown;
  onAnzahl: (wert: number) => void;
  onPlatzWaehlen: () => void;
  onPlatzZuruecksetzen: () => void;
}

function WettbewerbZeile({
  turnierId,
  anmeldungId,
  wettbewerb,
  stand,
  bereits,
  sperre,
  frei,
  neu,
  betrag,
  platz,
  durchgaenge,
  geld,
  fehler,
  onAnzahl,
  onPlatzWaehlen,
  onPlatzZuruecksetzen,
}: WettbewerbZeileProps) {
  const { t, i18n } = useTranslation("anmeldung");
  const sprache = i18n.language;
  const fehlerText = useFehlerText();
  const zeitplan = wettbewerb.planning === "schedule" && wettbewerb.range_id !== null;
  const vorschlag = useQuery({
    ...naechsterPlatzAbfrage(turnierId, wettbewerb.id, anmeldungId),
    enabled: zeitplan && neu > 0 && !platz,
  });
  const name = `${kennziffer(wettbewerb)} ${wettbewerb.name}`;
  const gewaehlterDurchgang = platz ? durchgaenge.get(platz.durchgangId) : undefined;
  const gebucht = bereits > 0;
  const hinweis = mengenHinweis(wettbewerb, bereits, neu);

  return (
    <li
      className={s.zeile}
      data-neu={neu > 0 || undefined}
      data-gesperrt={sperre ? true : undefined}
    >
      <span className={`num ${s.kz}`}>{kennziffer(wettbewerb)}</span>
      <div className={s.zeileName}>
        <strong>{wettbewerb.name}</strong>
        <span>
          {stand?.name ?? t("buchen.ohne_stand")}
          {" · "}
          {t(zeitplan ? "buchen.zeitplan" : "buchen.reihenfolge")}
          {gebucht && (
            <>
              {" · "}
              {t("buchen.schon", { count: bereits })}
            </>
          )}
        </span>
        {sperre && <span className={s.sperre}>{sperrText(t, sperre)}</span>}
      </div>
      <div className={s.menge}>
        <Stepper
          wert={neu}
          max={frei}
          onWert={onAnzahl}
          gesperrt={sperre !== null}
          beschriftung={t("buchen.anzahl", { name })}
          weniger={t("buchen.weniger", { name })}
          mehr={t("buchen.mehr", { name })}
        />
        <small data-grenze={(!sperre && hinweis.art === "grenze") || undefined}>
          {sperre
            ? t("buchen.gesperrt")
            : hinweis.art === "noch"
              ? t("buchen.noch", { count: hinweis.anzahl })
              : t("buchen.grenze", { count: hinweis.grenze })}
        </small>
      </div>
      <div className={s.preis}>
        <b className="num">{geld(betrag.cents)}</b>
        <small>
          {neu === 0
            ? gebucht
              ? t("buchen.preis_nachkauf", { betrag: geld(wettbewerb.fee_repeat_cents) })
              : t("buchen.preis_start", { betrag: geld(wettbewerb.fee_first_cents) })
            : betrag.erste && betrag.nachkauf
              ? t("buchen.start_und_nachkauf", { count: betrag.nachkauf })
              : betrag.erste
                ? t("buchen.ein_start")
                : t("buchen.nachkauf", { count: betrag.nachkauf })}
        </small>
      </div>
      {zeitplan && neu > 0 && (
        <div className={s.platz}>
          <Clock aria-hidden />
          {platz && gewaehlterDurchgang ? (
            <span>
              {t("platz.gewaehlt")}{" "}
              <b className="num">{platzText(t, sprache, gewaehlterDurchgang, platz.bahn)}</b>
            </span>
          ) : vorschlag.isPending ? (
            <span className="gedaempft">{t("platz.laedt")}</span>
          ) : vorschlag.isError ? (
            <span className={s.sperre}>{fehlerText(vorschlag.error)}</span>
          ) : vorschlag.data ? (
            <span>
              {t("platz.vorschlag")}{" "}
              <b className="num">
                {platzText(t, sprache, vorschlag.data.heat, vorschlag.data.lane)}
              </b>
            </span>
          ) : (
            <span className={s.sperre}>{t("platz.keiner")}</span>
          )}
          <Button
            variant="default"
            size="compact-sm"
            leftSection={<Pencil aria-hidden />}
            onClick={onPlatzWaehlen}
          >
            {t("platz.aendern")}
          </Button>
          {platz && (
            <Button
              variant="subtle"
              color="gray"
              size="compact-sm"
              leftSection={<Undo2 aria-hidden />}
              onClick={onPlatzZuruecksetzen}
            >
              {t("platz.vorschlag_nehmen")}
            </Button>
          )}
          {neu > 1 && <small className="gedaempft">{t("platz.weitere", { count: neu - 1 })}</small>}
        </div>
      )}
      {fehler ? (
        <div className={s.zeileFehler}>
          <FehlerHinweis fehler={fehler} />
        </div>
      ) : null}
    </li>
  );
}

interface GebuchteStartsProps {
  anmeldung: Anmeldung;
  wettbewerbe: Map<string, Wettbewerb>;
  durchgaenge: Map<string, Durchgang>;
  geld: (cents: number) => string;
  onStornieren: (start: Start) => void;
  onLoeschen: () => void;
}

function GebuchteStarts({
  anmeldung,
  wettbewerbe,
  durchgaenge,
  geld,
  onStornieren,
  onLoeschen,
}: GebuchteStartsProps) {
  const { t, i18n } = useTranslation("anmeldung");
  const sprache = i18n.language;
  const kannLoeschen = loeschbar(anmeldung);
  return (
    <section className={s.gebucht} aria-labelledby="anmeldung-gebucht">
      <div className="panel-kopf">
        <h3 className="h-section" id="anmeldung-gebucht">
          {t("gebucht.titel")}
        </h3>
        <span className="gedaempft">
          {t("gebucht.summe")} <b className="num">{geld(anmeldung.fee_total_cents)}</b>
        </span>
      </div>
      {anmeldung.starts.length === 0 ? (
        <p className="gedaempft">{t("gebucht.keine")}</p>
      ) : (
        <ul className={s.startListe}>
          {anmeldung.starts.map((start) => {
            const wettbewerb = wettbewerbe.get(start.competition_id);
            const anzeige = statusAnzeige(start);
            const sperre = stornoSperre(start);
            const durchgang = start.heat_id ? durchgaenge.get(start.heat_id) : undefined;
            return (
              <li key={start.id} className={s.startZeile}>
                <span className={`num ${s.kz}`}>{wettbewerb ? kennziffer(wettbewerb) : "—"}</span>
                <span className={s.startText}>
                  <strong>
                    {wettbewerb?.name ?? t("gebucht.unbekannt")}
                    {" · "}
                    {t("gebucht.versuch", { nr: start.attempt })}
                  </strong>
                  <span className="gedaempft">
                    {durchgang && start.lane ? (
                      <>
                        <MapPin aria-hidden /> {platzText(t, sprache, durchgang, start.lane)}
                      </>
                    ) : wettbewerb?.planning === "schedule" && start.status === "registered" ? (
                      t("gebucht.ohne_platz")
                    ) : start.queue_position ? (
                      t("gebucht.position", { nr: start.queue_position })
                    ) : null}
                  </span>
                  {sperre && <span className="gedaempft">{t(`gebucht.sperre_${sperre}`)}</span>}
                </span>
                <Chip ton={anzeige.ton} className={s.startStatus}>
                  {t(`status.${anzeige.schluessel}`)}
                  {anzeige.schluessel === "aufgerufen" && anzeige.bahn
                    ? ` · ${t("status.bahn", { bahn: anzeige.bahn })}`
                    : ""}
                </Chip>
                <span className={`num ${s.startPreis}`}>{geld(start.fee_cents)}</span>
                <Button
                  variant="default"
                  size="compact-md"
                  className={s.stornoKnopf}
                  disabled={sperre !== null}
                  onClick={() => onStornieren(start)}
                  aria-label={t("storno.knopf_lang", {
                    wettbewerb: wettbewerb?.name ?? "",
                    nr: start.attempt,
                  })}
                  title={sperre ? t(`gebucht.sperre_${sperre}`) : undefined}
                >
                  {t("storno.knopf")}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <div className={s.loeschenZeile}>
        <Button
          variant="default"
          className={s.gefahr}
          leftSection={<Trash2 aria-hidden />}
          disabled={!kannLoeschen}
          onClick={onLoeschen}
        >
          {t("loeschen.knopf")}
        </Button>
        {!kannLoeschen && <span className="gedaempft">{t("loeschen.gesperrt")}</span>}
      </div>
    </section>
  );
}
