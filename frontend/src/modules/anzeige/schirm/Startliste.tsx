import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { abbruchText, feedUhrzeit } from "../format";
import type { Takt } from "../rotation";
import type { FeedPerson, SzeneVon } from "../typen";
import { AbschnittKopf, LivePunkt, SeitenMarke, useName, WettbewerbTitel } from "./Bausteine";
import { useSchirm, useSeiten, useWoerter } from "./messen";
import s from "./schirm.module.css";

/**
 * Wo und wann jemand schießt: Durchgang mit Uhrzeit und Schützenstand, sonst nur der
 * Schützenstand – mit den Wörtern des Verbands (`verband`, aus `FeedStartlist.federation`).
 */
export function usePlatzText(verband?: string | null): (person: FeedPerson) => string {
  const { t } = useTranslation("anzeige");
  const { sprache } = useSchirm();
  const woerter = useWoerter(verband);
  const wort = { durchgang: woerter.durchgang, stand: woerter.schuetzenstand };
  return (person) => {
    const zeit = feedUhrzeit(person.heat_starts_at_local, person.heat_starts_at, sprache);
    if (person.heat_number != null && zeit) {
      return person.lane != null
        ? t("schirm.platz.durchgang_bahn", {
            ...wort,
            nummer: person.heat_number,
            zeit,
            bahn: person.lane,
          })
        : t("schirm.platz.durchgang", { ...wort, nummer: person.heat_number, zeit });
    }
    if (person.lane != null) return t("schirm.platz.bahn", { ...wort, bahn: person.lane });
    return "";
  };
}

/**
 * Status einer Person in der Startliste. Abgebrochen: das Kennzeichen des Servers
 * (`abort_label`, je Verband), sonst der bisherige Text zum Grund.
 */
function useStatusText(): (person: FeedPerson) => string {
  const { t } = useTranslation("anzeige");
  return (person) => {
    if (person.status === "aborted") {
      const text = abbruchText(person, (grund) => t(`abbruch.${grund}`));
      if (text) return text;
    }
    return t(`status.${person.status}`);
  };
}

/**
 * Zeilen je Spalte: so viele, wie hineinpassen; passt die Seite locker, gleichmäßig auf die Spalten
 * verteilt (7 Starts in 2 Spalten: 4 und 3 statt 7 links und rechts nichts).
 */
export function startlistenZeilen(
  passen: number | null,
  spalten: number,
  anzahl: number,
): number | null {
  if (passen === null) return null;
  return Math.max(1, Math.min(passen, Math.ceil(anzahl / Math.max(1, spalten))));
}

/** Startliste je Wettbewerb; lange Listen in Spalten und seitenweise. */
export function StartlistenSzene({ szene, takt }: { szene: SzeneVon<"startlist">; takt: Takt }) {
  const { t } = useTranslation("anzeige");
  const name = useName();
  const liste = szene.startlist;
  const platzText = usePlatzText(liste.federation);
  const statusText = useStatusText();
  const woerter = useWoerter(liste.federation);
  const seiten = useSeiten(liste.starts, takt);
  const zeilen = startlistenZeilen(seiten.zeilen, seiten.spalten, seiten.eintraege.length);
  // Gemessen: spaltenweise füllen (erst links nach unten, dann rechts), wie man Listen liest.
  const stil =
    zeilen !== null
      ? ({
          gridTemplateRows: `repeat(${zeilen}, max-content)`,
          gridAutoFlow: "column",
        } as CSSProperties)
      : undefined;

  return (
    <section className={s.szeneStartliste} aria-label={szene.title}>
      <AbschnittKopf
        titel={
          <WettbewerbTitel
            code={liste.competition_code}
            name={liste.competition_name}
            kennziffer={woerter.kennziffer}
          />
        }
        meta={
          <>
            {liste.range_name && <span>{liste.range_name}</span>}
            <SeitenMarke seite={seiten.seite} seiten={seiten.seiten} />
          </>
        }
      />
      <div ref={seiten.ref} className={s.startListe} style={stil}>
        {seiten.eintraege.map((person) => {
          const platz = platzText(person);
          return (
            <div
              key={person.start_id}
              className={s.startZeile}
              data-zeile=""
              data-status={person.status}
            >
              <span className={`num ${s.startNummer}`}>{person.start_number}</span>
              <span className={s.wer}>
                <b>{name(person)}</b>
                <span className={s.unter}>
                  {[person.club, person.class_short].filter(Boolean).join(" · ")}
                  {person.attempt > 1 && ` · ${t("schirm.versuch", { nr: person.attempt })}`}
                </span>
              </span>
              <span className={s.startPlatz}>
                {platz && <span className="num">{platz}</span>}
                {person.status !== "registered" && (
                  <span className={s.startStatus} data-status={person.status}>
                    {person.status === "called" && <LivePunkt />}
                    {statusText(person)}
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>
      {liste.more > 0 && (
        <p className={s.fussnote}>{t("schirm.weitere_starts", { count: liste.more })}</p>
      )}
    </section>
  );
}
