import { MonitorOff, TriangleAlert, Unplug } from "lucide-react";
import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { formatDatum, formatUhrzeit } from "../../../lib/format";
import {
  indexNachWechsel,
  naechsterIndex,
  restSekunden,
  szenenSchluessel,
  type Takt,
} from "../rotation";
import type { Feed, FeedKopf, FeedSzene } from "../typen";
import { SchirmKontext, type SchirmLage, useGroesse, useSchirm } from "./messen";
import { LiveWertung, Siegerliste } from "./Rangliste";
import { StandAnzeige } from "./StandSzene";
import { StartlistenSzene } from "./Startliste";
import s from "./schirm.module.css";
import { themaStil } from "./thema";
import { type FeedQuelle, type FeedZustand, type SperrFehler, useFeed } from "./useFeed";

/** Kürzere Seite von Full HD; darauf sind Bausteine mit festen Pixelgrenzen abgestimmt. */
const FULL_HD_KURZ = 1080;

interface SchirmProps {
  quelle: FeedQuelle;
  /** Verkleinert in der Verwaltung: keine eigenen Seiteneffekte, Beschriftung als Vorschau */
  vorschau?: boolean;
}

/**
 * Der Bildschirm im Schützenhaus. Zeichnet ausschließlich, was der Feed liefert, und füllt seinen
 * Rahmen genau (Größen relativ zum Rahmen, `cqmin`), damit Full HD, 4K und kleine Fernseher gleich
 * aussehen. Dieselbe Komponente steckt verkleinert in der Vorschau der Verwaltung.
 */
export function Schirm({ quelle, vorschau = false }: SchirmProps) {
  const zustand = useFeed(quelle);
  return <SchirmAnsicht zustand={zustand} quelle={quelle} vorschau={vorschau} />;
}

/** Darstellung zu einem Feed-Zustand; getrennt vom Laden, damit Tests einen Feed vorgeben können. */
export function SchirmAnsicht({
  zustand,
  quelle,
  vorschau = false,
}: {
  zustand: Pick<FeedZustand, "feed" | "laedt" | "sperre" | "getrenntSeit" | "versatzMs">;
  quelle: FeedQuelle;
  vorschau?: boolean;
}) {
  const { i18n } = useTranslation("anzeige");
  const [buehneRef, groesse] = useGroesse<HTMLDivElement>();
  const jetzt = useJetzt();
  const { feed } = zustand;
  const lage = useMemo<SchirmLage>(
    () => ({
      jetzt,
      versatzMs: zustand.versatzMs,
      hochkant: groesse.hoehe > groesse.breite,
      faktor: Math.max(1, Math.min(groesse.breite, groesse.hoehe) / FULL_HD_KURZ),
      sprache: i18n.language,
    }),
    [jetzt, zustand.versatzMs, groesse.hoehe, groesse.breite, i18n.language],
  );

  return (
    <div
      ref={buehneRef}
      className={s.buehne}
      style={themaStil(feed?.theme ?? "dark")}
      data-vorschau={vorschau || undefined}
    >
      <SchirmKontext.Provider value={lage}>
        {feed && feed.scenes.length > 0 ? (
          <SchirmInhalt feed={feed} getrenntSeit={zustand.getrenntSeit} />
        ) : zustand.sperre ? (
          <Sperre sperre={zustand.sperre} quelle={quelle} />
        ) : zustand.laedt ? (
          <Ruhe />
        ) : (
          <Ruhe getrenntSeit={zustand.getrenntSeit} />
        )}
      </SchirmKontext.Provider>
    </div>
  );
}

/** Geräteuhr, tickt jede Sekunde. */
function useJetzt(): number {
  const [jetzt, setJetzt] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setJetzt(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return jetzt;
}

interface Rotation {
  index: number;
  start: number;
}

/**
 * Szenen nacheinander mit ihrer Dauer. Kommt ein neuer Feed, bleibt die laufende Szene stehen,
 * wenn es sie noch gibt. Eine einzelne Szene steht still.
 */
function useRotation(szenen: FeedSzene[]): { szene: FeedSzene; index: number; takt: Takt } {
  const [rotation, setRotation] = useState<Rotation>(() => ({ index: 0, start: Date.now() }));
  const vorige = useRef(szenen);

  useEffect(() => {
    if (vorige.current === szenen) return;
    const alte = vorige.current;
    vorige.current = szenen;
    setRotation((alt) => {
      const index = indexNachWechsel(alte, szenen, alt.index);
      const bisher = alte[alt.index];
      const neu = szenen[index];
      const gleich = bisher && neu && szenenSchluessel(bisher) === szenenSchluessel(neu);
      return gleich ? { index, start: alt.start } : { index, start: Date.now() };
    });
  }, [szenen]);

  const index = Math.min(rotation.index, szenen.length - 1);
  const szene = szenen[index] as FeedSzene;
  const dauer = Math.max(1, szene.seconds) * 1000;

  useEffect(() => {
    if (szenen.length <= 1) return;
    const rest = Math.max(0, rotation.start + dauer - Date.now());
    const timer = setTimeout(
      () =>
        setRotation((alt) => ({
          index: naechsterIndex(alt.index, szenen.length),
          start: Date.now(),
        })),
      rest,
    );
    return () => clearTimeout(timer);
  }, [rotation, dauer, szenen.length]);

  return { szene, index, takt: { start: rotation.start, dauer } };
}

function SchirmInhalt({ feed, getrenntSeit }: { feed: Feed; getrenntSeit: Date | null }) {
  const { t } = useTranslation("anzeige");
  const { szene, index, takt } = useRotation(feed.scenes);
  const warnungen = feed.warnings.filter((warnung) => warnung.code !== "provisional");
  const vorlaeufig = feed.warnings.find((warnung) => warnung.code === "provisional");
  const titel =
    szene.parts > 1
      ? t("schirm.szene_teil", { titel: szene.title, teil: szene.part, teile: szene.parts })
      : szene.title;

  return (
    <div className={s.schirm} data-ticker={feed.ticker ? "" : undefined}>
      <Kopf kopf={feed.header} szene={titel} />
      {warnungen.length > 0 && (
        <div className={s.warnungen} role="alert">
          {warnungen.map((warnung) => (
            <p key={warnung.code} className={s.warnung}>
              <TriangleAlert aria-hidden />
              {warnung.message}
            </p>
          ))}
        </div>
      )}
      <main className={s.flaeche}>
        <div key={`${szenenSchluessel(szene)}@${takt.start}`} className={s.einblenden}>
          <SzenenInhalt szene={szene} kopf={feed.header} takt={takt} />
        </div>
      </main>
      <Fuss
        index={index}
        anzahl={feed.scenes.length}
        takt={takt}
        naechste={
          feed.scenes.length > 1 ? feed.scenes[(index + 1) % feed.scenes.length]?.title : undefined
        }
        vorlaeufig={vorlaeufig?.message}
      />
      {feed.ticker && <Laufzeile text={feed.ticker} />}
      {getrenntSeit && <GetrenntMarke seit={getrenntSeit} />}
    </div>
  );
}

function SzenenInhalt({ szene, kopf, takt }: { szene: FeedSzene; kopf: FeedKopf; takt: Takt }) {
  switch (szene.kind) {
    case "live_ranking":
      return <LiveWertung szene={szene} takt={takt} />;
    case "winners":
      return <Siegerliste szene={szene} takt={takt} />;
    case "startlist":
      return <StartlistenSzene szene={szene} takt={takt} />;
    case "range":
      return <StandAnzeige szene={szene} takt={takt} />;
    case "notice":
      return (
        <section className={s.szeneText} aria-label={szene.title}>
          <h2 className={s.hinweisTitel}>{szene.heading}</h2>
          {szene.text && <p className={s.hinweisText}>{szene.text}</p>}
        </section>
      );
    case "idle":
      return (
        <section className={s.szeneText} data-ruhe="" aria-label={szene.title}>
          <img src="/icons/app-icon.svg" alt="" className={s.ruheLogo} />
          <h2 className={s.hinweisTitel}>{kopf.title}</h2>
          <p className={s.ruheUeberschrift}>{szene.heading}</p>
          {szene.text && <p className={s.hinweisText}>{szene.text}</p>}
        </section>
      );
  }
}

function useServerZeit(): Date {
  const { jetzt, versatzMs } = useSchirm();
  return new Date(jetzt + versatzMs);
}

function zeitraum(kopf: FeedKopf, sprache: string): string | null {
  if (!kopf.date_from) return null;
  const von = formatDatum(kopf.date_from, sprache);
  const bis = kopf.date_to ? formatDatum(kopf.date_to, sprache) : von;
  return von === bis ? von : `${von} – ${bis}`;
}

function Kopf({ kopf, szene }: { kopf: FeedKopf; szene: string }) {
  const { sprache } = useSchirm();
  const zeit = useServerZeit();
  const unter = [kopf.organizer, zeitraum(kopf, sprache)].filter(Boolean).join(" · ");
  return (
    <header className={s.kopf}>
      <div className={s.marke} aria-hidden="true">
        <img src="/icons/app-icon.svg" alt="" />
        <b>
          schiesshub<span>.app</span>
        </b>
      </div>
      <div className={s.titel}>
        <h1>{kopf.title}</h1>
        {unter && <span>{unter}</span>}
      </div>
      <div className={s.jetzt}>
        <span className={s.szenenName}>{szene}</span>
        <time className={`num ${s.uhr}`} dateTime={zeit.toISOString()}>
          {formatUhrzeit(zeit, sprache)}
        </time>
      </div>
    </header>
  );
}

function Fuss({
  index,
  anzahl,
  takt,
  naechste,
  vorlaeufig,
}: {
  index: number;
  anzahl: number;
  takt: Takt;
  naechste?: string;
  vorlaeufig?: string;
}) {
  const { t } = useTranslation("anzeige");
  const { jetzt } = useSchirm();
  const rotiert = anzahl > 1;
  if (!rotiert && !vorlaeufig) return <footer className={s.fuss} data-leer="" />;
  return (
    <footer className={s.fuss}>
      {rotiert ? (
        <div className={s.rotation}>
          <span className={s.punkte} aria-hidden="true">
            {Array.from({ length: anzahl }, (_, nr) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: Punkte stehen für Stellen
              <span key={nr} data-an={nr === index || undefined} />
            ))}
          </span>
          <span>
            {t("schirm.rotation", {
              nr: index + 1,
              anzahl,
              naechste: naechste ?? "",
              sekunden: restSekunden(takt, jetzt),
            })}
          </span>
          <span
            key={`${index}@${takt.start}`}
            className={s.fortschritt}
            style={{ "--dauer": `${takt.dauer}ms` } as CSSProperties}
            aria-hidden="true"
          />
        </div>
      ) : (
        <span />
      )}
      {vorlaeufig && <span className={s.vorlaeufigHinweis}>{vorlaeufig}</span>}
    </footer>
  );
}

/** Laufzeile am unteren Rand; ohne Bewegung (reduced motion) steht der Text still. */
function Laufzeile({ text }: { text: string }) {
  const dauer = Math.max(12, Math.round(text.length * 0.28));
  return (
    <div className={s.laufzeile}>
      <div className={s.laufband} style={{ "--lauf": `${dauer}s` } as CSSProperties}>
        <span>{text}</span>
        <span aria-hidden="true">{text}</span>
      </div>
    </div>
  );
}

function GetrenntMarke({ seit }: { seit: Date }) {
  const { t } = useTranslation("anzeige");
  const { sprache, versatzMs } = useSchirm();
  return (
    <p className={s.getrennt} role="status">
      <Unplug aria-hidden />
      {t("schirm.getrennt", { zeit: formatUhrzeit(new Date(seit.getTime() + versatzMs), sprache) })}
    </p>
  );
}

/** Ruhiger Bildschirm vor dem ersten Feed (oder ohne Verbindung beim Start). */
function Ruhe({ getrenntSeit }: { getrenntSeit?: Date | null }) {
  const { t } = useTranslation("anzeige");
  return (
    <div className={s.schirmLeer}>
      <img src="/icons/app-icon.svg" alt="" className={s.ruheLogo} />
      <p className={s.sperrText}>{getrenntSeit ? t("schirm.verbinde") : t("schirm.laedt")}</p>
      {getrenntSeit && <GetrenntMarke seit={getrenntSeit} />}
    </div>
  );
}

/** 401, 403, 404: eine klare Zeile, was zu tun ist. Der Bildschirm prüft von selbst weiter. */
function Sperre({ sperre, quelle }: { sperre: SperrFehler; quelle: FeedQuelle }) {
  const { t } = useTranslation("anzeige");
  const art = quelle.art === "geraet" ? "geraet" : "anzeige";
  return (
    <div className={s.schirmLeer}>
      <MonitorOff aria-hidden className={s.sperrSymbol} />
      <p className={s.sperrText} role="alert">
        {t(`schirm.sperre.${art}_${sperre}`)}
      </p>
      <p className={s.sperrHinweis}>{t("schirm.sperre.hinweis")}</p>
    </div>
  );
}
