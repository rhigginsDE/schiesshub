import { type CSSProperties, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  gesamtTeile,
  laengstesWort,
  mitErgebnis,
  mitWeiterenPlaetzen,
  podestReihenfolge,
  podestStufe,
  type RanglistenEintrag,
  ranglistenEintraege,
  ranglistenSeiten,
  serienAnzahl,
  serienBreite,
  serienPassen,
  serienWert,
  siegerAufteilung,
} from "../format";
import { inSeiten, seiteZurZeit, type Takt, teilTakt } from "../rotation";
import type { FeedGruppe, FeedZeile, SzeneVon } from "../typen";
import {
  AbschnittKopf,
  KatalogAbweichung,
  LivePunkt,
  SeitenMarke,
  useName,
  WettbewerbTitel,
} from "./Bausteine";
import { useSchirm, useSeiten } from "./messen";
import s from "./schirm.module.css";

function spaltenVorlage(serien: number): string {
  const teile = ["var(--platz-breite)", "minmax(0, 1fr)"];
  if (serien > 0) teile.push(`repeat(${serien}, var(--serie-breite))`);
  teile.push("var(--gesamt-breite)");
  return teile.join(" ");
}

function Gesamt({ zeile, einheit }: { zeile: FeedZeile; einheit: string | null }) {
  const teile = gesamtTeile(mitErgebnis(zeile) ? zeile.score_text : null, einheit);
  return (
    <span className={`num ${s.gesamt}`}>
      {teile.wert}
      {teile.einheit && <small>{teile.einheit}</small>}
    </span>
  );
}

function Platz({ zeile }: { zeile: FeedZeile }) {
  const { t } = useTranslation("anzeige");
  return (
    <span className={`num ${s.platz}`}>
      {zeile.running && <LivePunkt />}
      <span>{zeile.place ?? "–"}</span>
      {zeile.tied && zeile.place !== null && <small>{t("schirm.geteilt")}</small>}
    </span>
  );
}

function Unterzeile({ zeile }: { zeile: FeedZeile }) {
  const { t } = useTranslation("anzeige");
  const teile: string[] = [];
  if (zeile.club) teile.push(zeile.club);
  if (zeile.attempt > 1) teile.push(t("schirm.versuch", { nr: zeile.attempt }));
  return (
    <span className={s.unter}>
      {teile.join(" · ")}
      {/* Leerzeichen vor jedem Zusatz: Vorlesen und Kopieren trennen „e. V.“ und „aufgegeben“. */}
      {zeile.running && (
        <>
          {" "}
          <em className={s.live}>{t("schirm.laeuft")}</em>
        </>
      )}
      {zeile.abort_reason && (
        <>
          {" "}
          <em className={s.abbruch}>{t(`abbruch.${zeile.abort_reason}`)}</em>
        </>
      )}
      {zeile.provisional && (
        <>
          {" "}
          <em className={s.vorlaeufig}>{t("schirm.vorlaeufig")}</em>
        </>
      )}
    </span>
  );
}

function RangZeile({
  zeile,
  serien,
  einheit,
}: {
  zeile: FeedZeile;
  serien: number;
  einheit: string | null;
}) {
  const { sprache } = useSchirm();
  const name = useName();
  return (
    <div
      className={s.rang}
      data-zeile=""
      data-erster={zeile.place === 1 || undefined}
      data-live={zeile.running || undefined}
      data-gruppe={zeile.group}
    >
      <Platz zeile={zeile} />
      <span className={s.wer}>
        <b>
          <span className={`num ${s.startnr}`}>{zeile.start_number}</span>
          {name(zeile)}
        </b>
        <Unterzeile zeile={zeile} />
      </span>
      {Array.from({ length: serien }, (_, nr) => {
        const serie = zeile.series[nr];
        return (
          <span
            // Serien haben keine eigene ID; die Stelle ist der Schlüssel.
            // biome-ignore lint/suspicious/noArrayIndexKey: feste Spaltenposition
            key={nr}
            className={`num ${s.serie}`}
            data-gestrichen={serie?.struck || undefined}
          >
            {serienWert(serie, sprache)}
          </span>
        );
      })}
      <Gesamt zeile={zeile} einheit={einheit} />
    </div>
  );
}

function Eintrag({
  eintrag,
  serien,
  einheit,
}: {
  eintrag: RanglistenEintrag;
  serien: number;
  einheit: string | null;
}) {
  const { t } = useTranslation("anzeige");
  if (eintrag.art === "zeile") {
    return <RangZeile zeile={eintrag.zeile} serien={serien} einheit={einheit} />;
  }
  if (eintrag.art === "klasse") {
    return (
      <div className={s.klassenKopf} data-zeile="">
        {eintrag.gruppe.class_name ?? eintrag.gruppe.class_short}
        {eintrag.gruppe.class_name && eintrag.gruppe.class_short && (
          <span className="num">{eintrag.gruppe.class_short}</span>
        )}
        {eintrag.fortsetzung && <small>{t("schirm.fortsetzung")}</small>}
      </div>
    );
  }
  return (
    <div className={s.mehr} data-zeile="">
      {t("schirm.weitere", { count: eintrag.anzahl })}
    </div>
  );
}

/** Live-Wertung: Rang, Name, Verein, Teilwerte je Serie, Gesamt groß; blättert bei langen Listen. */
export function LiveWertung({ szene, takt }: { szene: SzeneVon<"live_ranking">; takt: Takt }) {
  const { t } = useTranslation("anzeige");
  const { hochkant } = useSchirm();
  const rangliste = szene.ranking;
  const { sprache } = useSchirm();
  const anzahl = serienAnzahl(rangliste);
  const breite = serienBreite(rangliste, sprache);
  const serien = serienPassen(anzahl, breite, hochkant) ? anzahl : 0;
  const eintraege = useMemo(() => ranglistenEintraege(rangliste), [rangliste]);
  const seiten = useSeiten(eintraege, takt, ranglistenSeiten);
  const stil = {
    "--spalten": spaltenVorlage(serien),
    "--serie-breite": `${breite}cqmin`,
  } as CSSProperties;

  return (
    <section className={s.szeneRangliste} aria-label={szene.title} style={stil}>
      <AbschnittKopf
        titel={
          <WettbewerbTitel code={rangliste.competition_code} name={rangliste.competition_name} />
        }
        zusatz={
          <KatalogAbweichung deviates={rangliste.deviates} deviations={rangliste.deviations} />
        }
        meta={
          <>
            {rangliste.combined && <span>{t("schirm.gemeinsame_wertung")}</span>}
            <SeitenMarke seite={seiten.seite} seiten={seiten.seiten} />
          </>
        }
      />
      <div className={s.rangSpalten} aria-hidden="true">
        <span>{t("schirm.spalte.platz")}</span>
        <span>{t("schirm.spalte.name")}</span>
        {Array.from({ length: serien }, (_, nr) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: feste Spaltenposition
          <span key={nr} className={s.rechts}>
            {t("schirm.spalte.serie", { nr: nr + 1 })}
          </span>
        ))}
        <span className={s.rechts}>{t("schirm.spalte.gesamt")}</span>
      </div>
      <div ref={seiten.ref} className={s.rangListe}>
        {seiten.eintraege.map((eintrag) => (
          <Eintrag
            key={eintrag.schluessel}
            eintrag={eintrag}
            serien={serien}
            einheit={rangliste.unit}
          />
        ))}
      </div>
    </section>
  );
}

// --- Siegerliste ------------------------------------------------------------------

function PodestStufe({
  zeile,
  rang,
  einheit,
}: {
  zeile: FeedZeile;
  rang: number;
  einheit: string | null;
}) {
  const name = useName();
  const teile = gesamtTeile(zeile.score_text, einheit);
  const text = name(zeile);
  return (
    <div
      className={s.stufe}
      data-rang={rang}
      data-stufe={podestStufe(zeile.place, rang)}
      data-erster={zeile.place === 1 || undefined}
    >
      <div className={s.stufeName} style={{ "--wort": laengstesWort(text) } as CSSProperties}>
        <b className={s.stufeNameText}>{text}</b>
        {zeile.club && <span>{zeile.club}</span>}
      </div>
      <div className={s.sockel} style={{ "--zeichen": teile.wert.length } as CSSProperties}>
        <span className={`num ${s.sockelPlatz}`}>{zeile.place ?? "–"}</span>
        <span className={`num ${s.sockelWert}`}>{teile.wert}</span>
        {teile.einheit && <span className={s.sockelEinheit}>{teile.einheit}</span>}
      </div>
    </div>
  );
}

function WeitereListe({
  zeilen,
  takt,
  einheit,
}: {
  zeilen: FeedZeile[];
  takt: Takt;
  einheit: string | null;
}) {
  const { t } = useTranslation("anzeige");
  const name = useName();
  const seiten = useSeiten(zeilen, takt);
  // Nur Abgebrochene: Sie haben keinen Platz, „Weitere Plätze“ wäre falsch.
  const ohnePlatz = zeilen.every((zeile) => zeile.group === "unranked");
  return (
    <div className={s.weitere}>
      <div className={s.weitereKopf}>
        <span className={s.kicker}>
          {ohnePlatz ? t("schirm.ohne_platzierung") : t("schirm.weitere_plaetze")}
        </span>
        <SeitenMarke seite={seiten.seite} seiten={seiten.seiten} />
      </div>
      <div ref={seiten.ref} className={s.weitereListe}>
        {seiten.eintraege.map((zeile) => (
          <div
            key={zeile.start_id}
            className={s.weitereZeile}
            data-zeile=""
            data-abgebrochen={zeile.abort_reason ? "" : undefined}
          >
            {!zeile.abort_reason && <span className={`num ${s.platz}`}>{zeile.place ?? "–"}</span>}
            <span className={s.wer}>
              <b className={s.weitereName}>{name(zeile)}</b>
              {(zeile.club || zeile.abort_reason) && (
                <span className={s.unter}>
                  {zeile.club}
                  {zeile.abort_reason && (
                    <>
                      {" "}
                      <em className={s.abbruch}>{t(`abbruch.${zeile.abort_reason}`)}</em>
                    </>
                  )}
                </span>
              )}
            </span>
            {mitErgebnis(zeile) && (
              <span className={`num ${s.gesamt} ${s.gesamtKlein}`}>
                {gesamtTeile(zeile.score_text, einheit).wert}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function KlassenSieger({
  gruppe,
  takt,
  einheit,
  allein,
}: {
  gruppe: FeedGruppe;
  takt: Takt;
  einheit: string | null;
  allein: boolean;
}) {
  const { podest: erste, rest } = siegerAufteilung(gruppe.rows);
  return (
    <section
      className={s.klassenSieger}
      data-allein={allein || undefined}
      // Mehrere Klassen nebeneinander: Abgebrochene unter dem Podest statt daneben (sonst zu schmal).
      data-gestapelt={(!allein && rest.length > 0) || undefined}
    >
      {(gruppe.class_name || gruppe.class_short) && (
        <h3 className={s.klassenTitel}>
          {gruppe.class_name ?? gruppe.class_short}
          {gruppe.class_name && gruppe.class_short && (
            <span className="num">{gruppe.class_short}</span>
          )}
        </h3>
      )}
      <div className={s.siegerInhalt}>
        <div className={s.podest}>
          {podestReihenfolge(erste).map(({ eintrag, rang }) => (
            <PodestStufe key={eintrag.start_id} zeile={eintrag} rang={rang} einheit={einheit} />
          ))}
        </div>
        {rest.length > 0 && <WeitereListe zeilen={rest} takt={takt} einheit={einheit} />}
      </div>
    </section>
  );
}

/** Siegerliste: Podest für die ersten drei je Klasse, weitere Plätze kleiner daneben. */
export function Siegerliste({ szene, takt }: { szene: SzeneVon<"winners">; takt: Takt }) {
  const { t } = useTranslation("anzeige");
  const { hochkant, jetzt } = useSchirm();
  const rangliste = szene.ranking;
  const gruppen = rangliste.groups.filter((gruppe) => gruppe.rows.length > 0);
  // Mit weiteren Plätzen (ab Platz 4) oder hochkant: eine Klasse je Seite; sonst bis zu drei
  // nebeneinander. Abgebrochene allein zählen nicht: Sie stehen dann unter dem Podest.
  const mitRest = gruppen.some((gruppe) => mitWeiterenPlaetzen(gruppe.rows));
  const proSeite = hochkant || mitRest ? 1 : 3;
  const seiten = inSeiten(gruppen, proSeite);
  const seite = seiteZurZeit(takt, jetzt, seiten.length);
  const teil = teilTakt(takt, seite, seiten.length);
  const sichtbar = seiten[seite] ?? [];

  return (
    <section className={s.szeneSieger} aria-label={szene.title}>
      <AbschnittKopf
        titel={
          <WettbewerbTitel code={rangliste.competition_code} name={rangliste.competition_name} />
        }
        zusatz={
          <KatalogAbweichung deviates={rangliste.deviates} deviations={rangliste.deviations} />
        }
        meta={
          <>
            {rangliste.combined && <span>{t("schirm.gemeinsame_wertung")}</span>}
            <SeitenMarke seite={seite} seiten={seiten.length} />
          </>
        }
      />
      <div className={s.siegerGruppen} style={{ "--anzahl": sichtbar.length } as CSSProperties}>
        {sichtbar.map((gruppe, nr) => (
          <KlassenSieger
            key={gruppe.class_id ?? `gruppe-${nr}`}
            gruppe={gruppe}
            takt={teil}
            einheit={rangliste.unit}
            allein={sichtbar.length === 1}
          />
        ))}
      </div>
    </section>
  );
}
