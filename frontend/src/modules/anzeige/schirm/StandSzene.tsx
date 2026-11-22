import { Check, ChevronRight } from "lucide-react";
import { type ReactNode, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { PositionsAblauf } from "../../../components/anschlag/PositionsAblauf";
import { formatDauer, formatZahl } from "../../../lib/format";
import {
  alsPosition,
  type BahnFortschritt,
  bahnFortschritt,
  feedUhrzeit,
  hatPositionen,
  hauptSerie,
  laufendeSerien,
  type NaechsteEintrag,
  naechsteEintraege,
  naechsteSeiten,
  naechsteZahl,
  trefferaufnahmeNach,
} from "../format";
import { seiteZurZeit, type Takt, teilTakt } from "../rotation";
import type {
  FeedAblauf,
  FeedAbschnitt,
  FeedNaechsterEintrag,
  FeedPerson,
  SzeneVon,
} from "../typen";
import { AbschnittKopf, LivePunkt, SeitenMarke, useName, WettbewerbTitel } from "./Bausteine";
import { useGroesse, useSchirm, useSeiten } from "./messen";
import s from "./schirm.module.css";

/** Kennzahlen eines Abschnitts aus dem Feed: gewertete Serien, Sollzeit, Zeitmessung. */
function AbschnittFakten({ abschnitt }: { abschnitt: FeedAbschnitt }) {
  const { t } = useTranslation("anzeige");
  const { sprache } = useSchirm();
  const fakten: string[] = [];
  if (abschnitt.counted_series != null && abschnitt.counted_series < abschnitt.series_count) {
    fakten.push(
      t("schirm.ablauf.gewertet", {
        gewertet: abschnitt.counted_series,
        gesamt: abschnitt.series_count,
      }),
    );
  }
  if (abschnitt.target_time_s != null) {
    fakten.push(
      t("schirm.ablauf.sollzeit", { zeit: formatDauer(abschnitt.target_time_s, sprache) }),
    );
  }
  return (
    <p className={s.abschnittZeile}>
      <strong>{abschnitt.name}</strong>
      <span>{abschnitt.summary}</span>
      {fakten.map((fakt) => (
        <span key={fakt} className={s.fakt}>
          {fakt}
        </span>
      ))}
    </p>
  );
}

/** „Bahn 2“ oder „Bahnen 1, 3“ für die laufende Serie. */
function useBahnenText(): (bahnen: readonly number[]) => string {
  const { t } = useTranslation("anzeige");
  return (bahnen) => t("schirm.ablauf.bahnen", { count: bahnen.length, bahnen: bahnen.join(", ") });
}

/** Serien-Übersicht für Disziplinen ohne Positionen: Schuss, Zeit, Distanz, gestrichen, Trefferaufnahme. */
function SerienFolge({
  abschnitt,
  laufend,
}: {
  abschnitt: FeedAbschnitt;
  laufend: ReadonlyMap<number, readonly number[]>;
}) {
  const { t } = useTranslation("anzeige");
  const { sprache } = useSchirm();
  const bahnenText = useBahnenText();
  return (
    <ol className={s.serienFolge} aria-label={abschnitt.name}>
      {abschnitt.series.map((serie, nr) => {
        const letzte = nr === abschnitt.series.length - 1;
        const bahnen = laufend.get(serie.number);
        return (
          <li
            key={serie.number}
            className={s.serienEintrag}
            aria-current={bahnen ? "step" : undefined}
          >
            <div
              className={s.serienKachel}
              data-gestrichen={!serie.counted || undefined}
              data-aktiv={bahnen ? "" : undefined}
            >
              {bahnen && (
                <span className={s.jetztMarke}>
                  {t("schirm.ablauf.jetzt_kurz", { bahnen: bahnenText(bahnen) })}
                </span>
              )}
              <span className={s.serienNr}>{t("schirm.ablauf.serie", { nr: serie.number })}</span>
              {serie.shots != null && (
                <span className={`num ${s.serienGross}`}>
                  {t("schirm.ablauf.schuss", { count: serie.shots })}
                </span>
              )}
              {serie.time_s != null && (
                <span className="num">{formatDauer(serie.time_s, sprache)}</span>
              )}
              {serie.distance_m != null && (
                <span className="num">
                  {t("allgemein:einheit.meter", {
                    wert: formatZahl(serie.distance_m, {}, sprache),
                  })}
                </span>
              )}
              {!serie.counted && (
                <span className={s.gestrichenText}>{t("schirm.ablauf.gestrichen")}</span>
              )}
            </div>
            {serie.hit_review_after ? (
              <span className={s.aufnahme}>{t("schirm.ablauf.trefferaufnahme")}</span>
            ) : (
              !letzte && <ChevronRight className={s.pfeil} aria-hidden />
            )}
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Vergrößert einen Baustein mit festen Pixelgrenzen (der Positions-Ablauf deckelt seine Schrift)
 * auf großen Bildschirmen, damit er im selben Verhältnis wächst wie der Rest des Bildes.
 */
function Skaliert({ children }: { children: ReactNode }) {
  const { faktor } = useSchirm();
  const [aussen, groesse] = useGroesse<HTMLDivElement>();
  const innen = useRef<HTMLDivElement>(null);
  const [hoehe, setHoehe] = useState(0);

  useLayoutEffect(() => {
    const element = innen.current;
    if (!element) return;
    const messen = () => setHoehe(element.offsetHeight);
    messen();
    const beobachter = new ResizeObserver(messen);
    beobachter.observe(element);
    return () => beobachter.disconnect();
  }, []);

  const aktiv = faktor > 1 && groesse.breite > 0;
  return (
    <div ref={aussen} className={s.skaliert} style={aktiv ? { height: hoehe * faktor } : undefined}>
      <div
        ref={innen}
        className={s.skaliertInnen}
        style={
          aktiv
            ? {
                width: groesse.breite / faktor,
                transform: `scale(${faktor})`,
                position: "absolute",
              }
            : undefined
        }
      >
        {children}
      </div>
    </div>
  );
}

/**
 * Unter dem Positions-Ablauf: welche Bahn gerade an welcher Position ist. Der Ablauf selbst hebt
 * nur eine Position hervor; hier stehen alle, auch wenn die Bahnen verschieden weit sind.
 */
function JetztZeile({ laufend }: { laufend: ReadonlyMap<number, readonly number[]> }) {
  const { t } = useTranslation("anzeige");
  const bahnenText = useBahnenText();
  if (laufend.size === 0) return null;
  return (
    <p className={s.jetztZeile}>
      <strong className={s.jetztMarke}>{t("schirm.ablauf.jetzt")}</strong>
      {[...laufend].map(([serie, bahnen]) => (
        <span key={serie}>
          {t("schirm.ablauf.position_bahnen", { nr: serie, bahnen: bahnenText(bahnen) })}
        </span>
      ))}
    </p>
  );
}

function Abschnitt({
  abschnitt,
  nr,
  ablauf,
}: {
  abschnitt: FeedAbschnitt;
  nr: number;
  ablauf: FeedAblauf;
}) {
  const laufend = laufendeSerien(ablauf, abschnitt.id);
  const haupt = hauptSerie(laufend);
  const aktivIndex = abschnitt.series.findIndex((serie) => serie.number === haupt);
  return (
    <section className={s.abschnitt}>
      <AbschnittFakten abschnitt={abschnitt} />
      {hatPositionen(abschnitt) ? (
        <>
          <Skaliert>
            <PositionsAblauf
              positionen={abschnitt.series.flatMap((serie) =>
                serie.position ? [alsPosition(serie.position)] : [],
              )}
              trefferaufnahmeNach={trefferaufnahmeNach(abschnitt)}
              serienGewertet={abschnitt.counted_series}
              schussJeSerie={abschnitt.shots_per_series}
              zeitJeSerieS={abschnitt.time_per_series_s}
              aktivIndex={aktivIndex >= 0 ? aktivIndex : null}
              ton={nr % 2 === 0 ? "a" : "b"}
              label={abschnitt.name}
            />
          </Skaliert>
          <JetztZeile laufend={laufend} />
        </>
      ) : (
        <SerienFolge abschnitt={abschnitt} laufend={laufend} />
      )}
    </section>
  );
}

/**
 * Ablauf einer Disziplin. Passt nicht alles auf den Schirm, kommen die Abschnitte nacheinander
 * (je ein Teil der Szenendauer), statt abgeschnitten zu werden.
 */
function AblaufBlock({ ablauf, takt }: { ablauf: FeedAblauf; takt: Takt }) {
  const { t } = useTranslation("anzeige");
  const { jetzt } = useSchirm();
  const ref = useRef<HTMLDivElement>(null);
  const [geteilt, setGeteilt] = useState(false);
  const abschnitte = ablauf.sections;

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || geteilt || abschnitte.length < 2) return;
    if (element.scrollHeight > element.clientHeight + 2) setGeteilt(true);
  });

  const seite = geteilt ? seiteZurZeit(takt, jetzt, abschnitte.length) : 0;
  const sichtbar = geteilt ? abschnitte.slice(seite, seite + 1) : abschnitte;
  const titel = <WettbewerbTitel code={ablauf.competition_code} name={ablauf.competition_name} />;

  return (
    <div className={s.ablauf}>
      <AbschnittKopf
        kicker={t("schirm.ablauf.kicker")}
        titel={titel}
        meta={geteilt && <SeitenMarke seite={seite} seiten={abschnitte.length} />}
      />
      <p className={s.ablaufMeta}>
        <span>{ablauf.variant_name}</span>
        <span>{ablauf.scoring}</span>
      </p>
      {ablauf.notes.length > 0 && (
        <ul className={s.hinweisListe}>
          {ablauf.notes.map((text) => (
            <li key={`n-${text}`}>{text}</li>
          ))}
        </ul>
      )}
      <div ref={ref} className={s.abschnitte}>
        {sichtbar.map((abschnitt) => (
          <Abschnitt
            key={abschnitt.id}
            abschnitt={abschnitt}
            nr={abschnitte.indexOf(abschnitt)}
            ablauf={ablauf}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * „Serie 2 von 4“ (bei Positionen „Position 2 von 6“) in zwei Zeilen, damit der Name Platz behält:
 * klein die Art (mit Abschnitt), groß die Zahlen. Fertig erfasst: Haken und „fertig“.
 */
function FortschrittMarke({ fortschritt }: { fortschritt: BahnFortschritt }) {
  const { t } = useTranslation("anzeige");
  if (fortschritt.fertig) {
    return (
      <span className={s.bahnStand} data-fertig="">
        <Check aria-hidden />
        {t("schirm.stand.fertig")}
      </span>
    );
  }
  const art = t(fortschritt.positionen ? "schirm.stand.position" : "schirm.stand.serie");
  return (
    <span className={s.bahnStand}>
      <span className={s.bahnStandArt}>
        {fortschritt.abschnitt ? `${fortschritt.abschnitt} · ${art}` : art}
      </span>{" "}
      <span className={`num ${s.bahnStandZahl}`}>
        {t("schirm.stand.von", { nr: fortschritt.serie, gesamt: fortschritt.serien })}
      </span>
    </span>
  );
}

function PersonZeile({
  person,
  nr,
  frei,
  fortschritt,
}: {
  person: FeedPerson | null;
  nr: string;
  frei?: boolean;
  fortschritt?: BahnFortschritt | null;
}) {
  const { t } = useTranslation("anzeige");
  const name = useName();
  if (!person || frei) {
    return (
      <div className={s.bahn} data-zeile="" data-frei="">
        <span className={`num ${s.bahnNr}`}>{nr}</span>
        <span className={s.wer}>
          <b className={s.bahnName}>{t("schirm.stand.frei")}</b>
        </span>
      </div>
    );
  }
  return (
    <div className={s.bahn} data-zeile="" data-status={person.status}>
      <span className={`num ${s.bahnNr}`}>{nr}</span>
      <span className={s.wer}>
        <b className={s.bahnName}>
          <span className={`num ${s.startnr}`}>{person.start_number}</span>
          {name(person)}
        </b>
        <span className={s.unter}>
          {[person.club, person.class_short].filter(Boolean).join(" · ")}
          {" · "}
          {/* Kennziffer davor: 1001 und 1201 heißen beide „Pistole bis 9 mm“. */}
          <WettbewerbTitel code={person.competition_code} name={person.competition_name} klein />
        </span>
      </span>
      {(fortschritt || person.status === "called") && (
        <span className={s.bahnRechts}>
          {fortschritt && <FortschrittMarke fortschritt={fortschritt} />}
          {person.status === "called" && <LivePunkt />}
        </span>
      )}
    </div>
  );
}

function AmStand({ stand, takt }: { stand: SzeneVon<"range">["range"]; takt: Takt }) {
  const { t } = useTranslation("anzeige");
  const seiten = useSeiten(stand.lanes, takt);
  return (
    <section className={s.standBlock}>
      <AbschnittKopf
        kicker={t("schirm.stand.am_stand")}
        titel={stand.range_name}
        meta={<SeitenMarke seite={seiten.seite} seiten={seiten.seiten} />}
      />
      <div ref={seiten.ref} className={s.bahnListe}>
        {seiten.eintraege.map((bahn) => (
          <PersonZeile
            key={bahn.lane}
            person={bahn.start}
            nr={String(bahn.lane)}
            fortschritt={bahnFortschritt(bahn, stand.procedures)}
          />
        ))}
      </div>
    </section>
  );
}

/** „gerade auf Bahn 1, 25-m-Stand“: Die Person schießt gerade woanders (oder hier). */
function useBesetztText(): (eintrag: FeedNaechsterEintrag) => string | null {
  const { t } = useTranslation("anzeige");
  return (eintrag) => {
    if (!eintrag.busy) return null;
    const stand = eintrag.busy_range_name;
    if (eintrag.busy_lane != null && stand) {
      return t("schirm.stand.busy", { bahn: eintrag.busy_lane, stand });
    }
    if (stand) return t("schirm.stand.busy_ohne_bahn", { stand });
    return t("schirm.stand.busy_kurz");
  };
}

function NaechsteZeile({ eintrag }: { eintrag: NaechsteEintrag }) {
  const { t } = useTranslation("anzeige");
  const { sprache } = useSchirm();
  const name = useName();
  const besetzt = useBesetztText();

  if (eintrag.art === "mehr") {
    return (
      <div className={s.naechsteMehr} data-zeile="">
        {t("schirm.stand.weitere", { count: eintrag.anzahl })}
      </div>
    );
  }
  if (eintrag.art === "kopf") {
    const block = eintrag.block;
    const zeitplan = block.kind === "schedule";
    return (
      <div className={s.naechsteKopf} data-zeile="">
        {/* Beschriftung der Zahlenspalte: Bahn (Zeitplan) oder Platz (Reihenfolge) */}
        <span className={s.naechsteSpalte}>
          {t(zeitplan ? "schirm.stand.spalte_bahn" : "schirm.stand.spalte_platz")}
        </span>
        <span className={s.naechsteTitel}>
          <b className={s.naechsteWettbewerb}>
            <WettbewerbTitel code={block.competition_code} name={block.competition_name} klein />
          </b>
          <span className={s.naechsteWann}>
            {zeitplan
              ? t("schirm.stand.durchgang_um", {
                  nummer: block.heat_number,
                  zeit: feedUhrzeit(block.starts_at_local, block.starts_at, sprache),
                })
              : t("schirm.stand.reihenfolge")}
            {eintrag.fortsetzung && ` · ${t("schirm.fortsetzung")}`}
          </span>
        </span>
      </div>
    );
  }
  const person = eintrag.eintrag;
  const woanders = besetzt(person);
  const unter = [person.club, person.class_short].filter(Boolean).join(" · ");
  return (
    <div className={s.bahn} data-zeile="" data-besetzt={woanders ? "" : undefined}>
      <span className={`num ${s.bahnNr}`}>{naechsteZahl(person)}</span>
      <span className={s.wer}>
        <b className={s.bahnName}>
          <span className={`num ${s.startnr}`}>{person.start_number}</span>
          {name(person)}
        </b>
        <span className={s.unter}>
          {unter}
          {person.attempt > 1 && ` · ${t("schirm.versuch", { nr: person.attempt })}`}
          {woanders && (
            <>
              {" "}
              <em className={s.besetzt}>{woanders}</em>
            </>
          )}
        </span>
      </span>
    </div>
  );
}

/**
 * „Als Nächstes“: je Wettbewerb ein Block mit Kennziffer und Name – bei Zeitplan der nächste
 * Durchgang mit Bahn, bei Reihenfolge die nächsten Plätze. Blättert, statt abzuschneiden.
 */
function AlsNaechstes({ stand, takt }: { stand: SzeneVon<"range">["range"]; takt: Takt }) {
  const { t } = useTranslation("anzeige");
  const eintraege = useMemo(() => naechsteEintraege(stand.upcoming), [stand.upcoming]);
  const seiten = useSeiten(eintraege, takt, naechsteSeiten);
  return (
    <section className={s.standBlock} data-art="naechste">
      <AbschnittKopf
        titel={t("schirm.stand.als_naechstes")}
        meta={<SeitenMarke seite={seiten.seite} seiten={seiten.seiten} />}
      />
      {eintraege.length === 0 ? (
        <p className={s.leerText}>{t("schirm.stand.niemand")}</p>
      ) : (
        <div ref={seiten.ref} className={s.bahnListe}>
          {seiten.eintraege.map((eintrag) => (
            <NaechsteZeile key={eintrag.schluessel} eintrag={eintrag} />
          ))}
        </div>
      )}
    </section>
  );
}

/** Standanzeige: links laufende Disziplin(en) mit Ablauf, rechts „Am Stand“ und „Als Nächstes“. */
export function StandAnzeige({ szene, takt }: { szene: SzeneVon<"range">; takt: Takt }) {
  const { jetzt } = useSchirm();
  const stand = szene.range;
  const ablaeufe = stand.procedures;
  const seite = seiteZurZeit(takt, jetzt, ablaeufe.length);
  const ablauf = ablaeufe[seite];
  const teil = teilTakt(takt, seite, ablaeufe.length);

  return (
    <section
      className={s.szeneStand}
      data-ohne-ablauf={ablauf ? undefined : ""}
      aria-label={szene.title}
    >
      {ablauf && <AblaufBlock key={ablauf.competition_id} ablauf={ablauf} takt={teil} />}
      <div className={s.standSeite}>
        <AmStand stand={stand} takt={takt} />
        <AlsNaechstes stand={stand} takt={takt} />
      </div>
    </section>
  );
}
