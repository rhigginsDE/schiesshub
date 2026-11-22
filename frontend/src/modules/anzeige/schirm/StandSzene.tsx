import { Check, ChevronRight } from "lucide-react";
import { type ReactNode, useLayoutEffect, useRef, useState } from "react";
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
  trefferaufnahmeNach,
} from "../format";
import { seiteZurZeit, type Takt, teilTakt } from "../rotation";
import type { FeedAblauf, FeedAbschnitt, FeedPerson, SzeneVon } from "../typen";
import {
  AbschnittKopf,
  AbweichendMarke,
  LivePunkt,
  SeitenMarke,
  useName,
  WettbewerbTitel,
} from "./Bausteine";
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
  const { t } = useTranslation("anzeige");
  const laufend = laufendeSerien(ablauf, abschnitt.id);
  const haupt = hauptSerie(laufend);
  const aktivIndex = abschnitt.series.findIndex((serie) => serie.number === haupt);
  const abweichung =
    abschnitt.deviations.length > 0
      ? t("schirm.ablauf.abschnitt_abweichend", { text: abschnitt.deviations.join(" · ") })
      : undefined;
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
              hinweis={abweichung}
              label={abschnitt.name}
            />
          </Skaliert>
          <JetztZeile laufend={laufend} />
        </>
      ) : (
        <>
          {abweichung && <p className={s.abweichungText}>{abweichung}</p>}
          <SerienFolge abschnitt={abschnitt} laufend={laufend} />
        </>
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
  const titel = <WettbewerbTitel code={ablauf.catalog_code} name={ablauf.competition_name} />;

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
        {ablauf.deviates && <AbweichendMarke />}
      </p>
      {(ablauf.deviations.length > 0 || ablauf.notes.length > 0) && (
        <ul className={s.hinweisListe}>
          {ablauf.deviations.map((text) => (
            <li key={`a-${text}`} data-art="abweichung">
              {text}
            </li>
          ))}
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
          {[person.club, person.class_short, person.competition_name].filter(Boolean).join(" · ")}
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

function AlsNaechstes({ stand, takt }: { stand: SzeneVon<"range">["range"]; takt: Takt }) {
  const { t } = useTranslation("anzeige");
  const { sprache } = useSchirm();
  const seiten = useSeiten(stand.next, takt);
  const durchgang = stand.next_heat;
  const beginn = durchgang
    ? feedUhrzeit(durchgang.starts_at_local, durchgang.starts_at, sprache)
    : null;
  return (
    <section className={s.standBlock} data-art="naechste">
      <AbschnittKopf
        kicker={t("schirm.stand.als_naechstes")}
        titel={
          durchgang
            ? t("schirm.stand.durchgang", { nummer: durchgang.number })
            : t("schirm.stand.reihenfolge")
        }
        meta={
          <>
            {beginn && <span className="num">{beginn}</span>}
            <SeitenMarke seite={seiten.seite} seiten={seiten.seiten} />
          </>
        }
      />
      {stand.next.length === 0 ? (
        <p className={s.leerText}>{t("schirm.stand.niemand")}</p>
      ) : (
        <div ref={seiten.ref} className={s.bahnListe}>
          {seiten.eintraege.map((person) => (
            <PersonZeile
              key={person.start_id}
              person={person}
              nr={String(
                person.lane != null && person.heat_number === durchgang?.number
                  ? person.lane
                  : stand.next.indexOf(person) + 1,
              )}
            />
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
