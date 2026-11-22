import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { feedUhrzeit } from "../format";
import type { Takt } from "../rotation";
import type { FeedPerson, SzeneVon } from "../typen";
import { AbschnittKopf, LivePunkt, SeitenMarke, useName, WettbewerbTitel } from "./Bausteine";
import { useSchirm, useSeiten } from "./messen";
import s from "./schirm.module.css";

/** Wo und wann jemand schießt: Durchgang mit Uhrzeit und Bahn, sonst nur die Bahn. */
export function usePlatzText(): (person: FeedPerson) => string {
  const { t } = useTranslation("anzeige");
  const { sprache } = useSchirm();
  return (person) => {
    const zeit = feedUhrzeit(person.heat_starts_at_local, person.heat_starts_at, sprache);
    if (person.heat_number != null && zeit) {
      return person.lane != null
        ? t("schirm.platz.durchgang_bahn", { nummer: person.heat_number, zeit, bahn: person.lane })
        : t("schirm.platz.durchgang", { nummer: person.heat_number, zeit });
    }
    if (person.lane != null) return t("schirm.platz.bahn", { bahn: person.lane });
    return "";
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
  const platzText = usePlatzText();
  const liste = szene.startlist;
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
        titel={<WettbewerbTitel code={liste.competition_code} name={liste.competition_name} />}
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
                    {person.status === "aborted" && person.abort_reason
                      ? t(`abbruch.${person.abort_reason}`)
                      : t(`status.${person.status}`)}
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
