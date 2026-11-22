import { Select } from "@mantine/core";
import { ChevronDown, ChevronUp, CircleAlert, Flag, TriangleAlert } from "lucide-react";
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { PositionsAblauf } from "../../components/anschlag/PositionsAblauf";
import type { Position } from "../../components/anschlag/typen";
import { formatWert, formatZeit, serienAnzeige } from "./anzeige";
import type {
  AbschnittForm,
  AbschnittWertung,
  FeldBeschreibung,
  Formular,
  SerieForm,
  Wertung,
} from "./api";
import { wertText, type ZahlEingabe } from "./eingabe";
import s from "./erfassung.module.css";
import {
  type Entwurf,
  type FeldRef,
  feldAktiv,
  feldId,
  meldungenFuer,
  NORMAL,
  type PfadMeldung,
  schuesseAus,
  serieAus,
  serienPfad,
  statusAus,
  statusFeld,
  wertAus,
} from "./rohwerte";

export interface MaskeProps {
  form: Formular;
  entwurf: Entwurf;
  wertung: Wertung | null;
  aktivId: string | null;
  eingabe: ZahlEingabe;
  schussPuffer: string;
  bearbeitbar: boolean;
  fehler: readonly PfadMeldung[];
  warnungen: readonly PfadMeldung[];
  aufgeklappt: ReadonlySet<string>;
  onAufklappen: (pfad: string) => void;
  onFeld: (ref: FeldRef) => void;
  onStatus: (abschnitt: AbschnittForm, serie: SerieForm, status: string) => void;
  /** Eingaben sind noch nicht gerechnet: Werte der Serien gedämpft zeigen */
  veraltet: boolean;
}

/** Abschnitte und Serien genau so, wie die Formularbeschreibung des Servers sie vorgibt. */
export function Maske(props: MaskeProps) {
  const { form, wertung } = props;
  const mehrere = form.sections.length > 1;
  return (
    <div className={s.maske}>
      {form.sections.map((abschnitt) => (
        <Abschnitt
          key={abschnitt.id}
          {...props}
          abschnitt={abschnitt}
          wertungAbschnitt={wertung?.sections.find((w) => w.id === abschnitt.id)}
          mitKopf={mehrere || abschnitt.fields.length > 0 || abschnitt.hints.length > 0}
        />
      ))}
    </div>
  );
}

function positionenAus(abschnitt: AbschnittForm): { positionen: Position[]; serien: number[] } {
  const positionen: Position[] = [];
  const serien: number[] = [];
  for (const serie of abschnitt.series) {
    if (!serie.position) continue;
    positionen.push({
      nr: serie.position.nr,
      distanz_m: serie.position.distance_m != null ? Number(serie.position.distance_m) : null,
      scheibe: serie.position.target,
      anschlaege: serie.position.stances.map((st) => ({
        haltung: st.haltung as Position["anschlaege"][number]["haltung"],
        hand: (st.hand ?? null) as Position["anschlaege"][number]["hand"],
      })),
    });
    serien.push(serie.index);
  }
  return { positionen, serien };
}

interface AbschnittProps extends MaskeProps {
  abschnitt: AbschnittForm;
  wertungAbschnitt: AbschnittWertung | undefined;
  mitKopf: boolean;
}

function Abschnitt(props: AbschnittProps) {
  const { t } = useTranslation("erfassung");
  const { abschnitt, wertungAbschnitt, mitKopf, aktivId, form } = props;
  const { positionen, serien } = positionenAus(abschnitt);
  const aktiveSerie = abschnitt.series.find((serie) =>
    aktivId?.startsWith(`${serienPfad(abschnitt.id, serie.index)}.`),
  );
  const aktivIndex = aktiveSerie ? serien.indexOf(aktiveSerie.index) : -1;
  const schussJeSerie = new Set(abschnitt.series.map((serie) => serie.shots));
  const einheitlich = schussJeSerie.size === 1 ? [...schussJeSerie][0] : null;
  const abschnittsIndex = form.sections.indexOf(abschnitt);

  return (
    <section className={s.abschnitt} aria-label={abschnitt.name}>
      {mitKopf && (
        <header className={s.abschnittKopf}>
          <h3 className="h-section">{abschnitt.name}</h3>
          {abschnitt.hints.length > 0 && (
            <p className={s.hinweise}>{abschnitt.hints.join(" · ")}</p>
          )}
          {wertungAbschnitt && form.sections.length > 1 && (
            <p className={`${s.abschnittWert} num`}>
              {t("abschnitt.ergebnis", { wert: formatWert(wertungAbschnitt.result) })}
              {wertungAbschnitt.time_cs !== null &&
                ` · ${t("abschnitt.zeit", { zeit: formatZeit(wertungAbschnitt.time_cs) })}`}
              {wertungAbschnitt.deduction !== null &&
                Number(wertungAbschnitt.deduction) !== 0 &&
                ` · ${t("abschnitt.abzug", { wert: formatWert(wertungAbschnitt.deduction) })}`}
            </p>
          )}
        </header>
      )}
      {positionen.length > 0 && (
        <div className={s.positionen}>
          <PositionsAblauf
            positionen={positionen}
            label={t("abschnitt.positionen", { name: abschnitt.name })}
            aktivIndex={aktivIndex >= 0 ? aktivIndex : null}
            serienGewertet={abschnitt.series_counted}
            trefferaufnahmeNach={abschnitt.series
              .filter((serie) => serie.scoring_break_after)
              .map((serie) => serie.number)}
            schussJeSerie={einheitlich ?? null}
            ton={abschnittsIndex % 2 === 0 ? "a" : "b"}
          />
        </div>
      )}
      <ol className={s.serien}>
        {abschnitt.series.map((serie) => (
          <li key={serie.index} className={s.serienEintrag}>
            <SerieKarte {...props} serie={serie} />
            {serie.scoring_break_after && (
              <p className={s.trefferaufnahme}>
                <Flag aria-hidden />
                {t("serie.trefferaufnahme")}
              </p>
            )}
          </li>
        ))}
      </ol>
      {abschnitt.fields
        .filter((feld) => feld.kind !== "choice")
        .map((feld) => {
          const ref: FeldRef = {
            id: feldId(abschnitt.id, null, feld.key),
            abschnitt: abschnitt.id,
            serie: null,
            key: feld.key,
            feld,
          };
          return (
            <div key={feld.key} className={s.abschnittFelder}>
              <Feldknopf {...props} feldRef={ref} aktiv />
              <Meldungen
                fehler={meldungenFuer(props.fehler, ref.id)}
                warnungen={meldungenFuer(props.warnungen, ref.id)}
              />
            </div>
          );
        })}
    </section>
  );
}

interface SerieKarteProps extends AbschnittProps {
  serie: SerieForm;
}

function SerieKarte(props: SerieKarteProps) {
  const { t } = useTranslation("erfassung");
  const {
    abschnitt,
    serie,
    entwurf,
    aktivId,
    aufgeklappt,
    onAufklappen,
    bearbeitbar,
    onStatus,
    wertungAbschnitt,
    veraltet,
  } = props;
  const pfad = serienPfad(abschnitt.id, serie.index);
  const offen = !serie.struck || aufgeklappt.has(pfad);
  const option = statusAus(entwurf, abschnitt.id, serie);
  const auswahl = statusFeld(serie);
  const aktiv = aktivId?.startsWith(`${pfad}.`) ?? false;
  const fehler = meldungenFuer(props.fehler, pfad);
  const warnungen = meldungenFuer(props.warnungen, pfad);
  const wertungSerie = wertungAbschnitt?.series[serie.index];
  const anzeige = serienAnzeige(wertungSerie, t);
  const statusText = option && option.key !== NORMAL ? option.label : null;
  const hinweise = serie.hints.filter((h) => !(serie.struck && h.startsWith("gestrichen")));

  return (
    <article
      className={s.serie}
      data-aktiv={aktiv || undefined}
      data-gestrichen={serie.struck || undefined}
      data-fehler={fehler.length > 0 || undefined}
      aria-label={serie.label}
    >
      <div className={s.serieInhalt}>
        <div className={s.serieKopf}>
          <span className={`h-label ${s.serieTitel}`}>{serie.label}</span>
          {serie.struck && <span className={s.gestrichenMarke}>{t("serie.gestrichen")}</span>}
          {hinweise.length > 0 && <span className={s.hinweise}>{hinweise.join(" · ")}</span>}
        </div>
        {serie.struck && (
          <button
            type="button"
            className={s.aufklappen}
            onClick={() => onAufklappen(pfad)}
            aria-expanded={offen}
          >
            {offen ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />}
            {offen ? t("serie.einklappen") : t("serie.aufklappen")}
          </button>
        )}
        {offen && (
          <>
            <div className={s.felder}>
              {auswahl?.options && (
                <Select
                  label={auswahl.label}
                  data={auswahl.options.map((o) => ({ value: o.key, label: o.label }))}
                  value={option?.key ?? NORMAL}
                  onChange={(wert) => wert && onStatus(abschnitt, serie, wert)}
                  allowDeselect={false}
                  disabled={!bearbeitbar}
                  size="md"
                  className={s.statusWahl}
                  classNames={{ input: s.statusFeld, label: s.feldName }}
                  comboboxProps={{ withinPortal: true }}
                />
              )}
              {serie.fields
                .filter((feld) => feld.kind !== "choice")
                .map((feld) =>
                  feld.kind === "shots" ? (
                    <Schussreihe
                      key={feld.key}
                      {...props}
                      feld={feld}
                      aktivFeld={feldAktiv(option, feld.key)}
                    />
                  ) : (
                    <Feldknopf
                      key={feld.key}
                      {...props}
                      feldRef={{
                        id: feldId(abschnitt.id, serie.index, feld.key),
                        abschnitt: abschnitt.id,
                        serie: serie.index,
                        key: feld.key,
                        feld,
                      }}
                      aktiv={feldAktiv(option, feld.key)}
                    />
                  ),
                )}
            </div>
            <Meldungen fehler={fehler} warnungen={warnungen} />
          </>
        )}
      </div>
      <div className={s.serienWert} data-veraltet={veraltet || undefined} aria-live="polite">
        <span className="h-label">{t("serie.wert")}</span>
        <strong className="num">{anzeige.wert}</strong>
        {anzeige.einheit && <span className={s.einheit}>{t(`einheit.${anzeige.einheit}`)}</span>}
        {anzeige.zusatz && <span className={`${s.zusatz} num`}>{anzeige.zusatz}</span>}
        {statusText && <span className={s.statusMarke}>{statusText}</span>}
      </div>
    </article>
  );
}

interface FeldknopfProps extends MaskeProps {
  feldRef: FeldRef;
  /** Vom Status der Serie gebraucht (sonst „entfällt“) */
  aktiv: boolean;
}

function Feldknopf({
  feldRef,
  aktiv,
  entwurf,
  aktivId,
  eingabe,
  bearbeitbar,
  onFeld,
  fehler,
}: FeldknopfProps) {
  const { t } = useTranslation("erfassung");
  const feld = feldRef.feld;
  const istAktiv = aktiv && aktivId === feldRef.id;
  const wert = wertAus(entwurf, feldRef);
  const text = istAktiv && !eingabe.frisch ? eingabe.text : wertText(feld, wert);
  const hatFehler = meldungenFuer(fehler, feldRef.id).length > 0;
  return (
    <button
      type="button"
      className={s.feld}
      data-feld={feldRef.id}
      data-aktiv={istAktiv || undefined}
      data-fehler={hatFehler || undefined}
      data-leer={text === "" || undefined}
      data-entfaellt={!aktiv || undefined}
      disabled={!aktiv || !bearbeitbar}
      aria-pressed={istAktiv}
      aria-label={`${feld.label}: ${!aktiv ? t("feld.entfaellt") : text || t("feld.leer")}`}
      onClick={() => onFeld(feldRef)}
    >
      <span className={s.feldName}>
        {feld.label}
        {!feld.required && aktiv && <span className={s.freiwillig}> · {t("feld.freiwillig")}</span>}
      </span>
      <span className={`${s.feldWert} num`}>
        {!aktiv ? t("feld.entfaellt") : text || " "}
        {istAktiv && <span className={s.cursor} aria-hidden />}
        {aktiv && feld.kind === "time" && text !== "" && (
          <span className={s.einheit}>{t("einheit.sekunden")}</span>
        )}
      </span>
      {aktiv && feld.max != null && feld.kind === "integer" && (
        <span className={s.feldBereich}>
          {t("feld.bereich", { min: feld.min ?? 0, max: feld.max })}
        </span>
      )}
    </button>
  );
}

interface SchussreiheProps extends SerieKarteProps {
  feld: FeldBeschreibung;
  aktivFeld: boolean;
}

function Schussreihe({
  abschnitt,
  serie,
  feld,
  aktivFeld,
  entwurf,
  aktivId,
  schussPuffer,
  bearbeitbar,
  onFeld,
  fehler,
}: SchussreiheProps) {
  const { t } = useTranslation("erfassung");
  const schuesse = schuesseAus(serieAus(entwurf, abschnitt.id, serie.index));
  const anzahl = feld.count ?? 0;
  const spalten = Math.min(anzahl, 10);
  return (
    <div className={s.schussFeld}>
      <span className={s.feldName}>
        {feld.label}
        {!aktivFeld && ` · ${t("feld.entfaellt")}`}
      </span>
      <ol
        className={s.schuesse}
        style={{ "--spalten": spalten } as CSSProperties}
        data-viele={spalten > 5 || undefined}
        aria-label={t("schuss.reihe", { serie: serie.label })}
      >
        {Array.from({ length: anzahl }, (_, index) => {
          const id = feldId(abschnitt.id, serie.index, feld.key, index);
          const wert = schuesse[index];
          const istAktiv = aktivFeld && aktivId === id;
          const text =
            istAktiv && schussPuffer ? schussPuffer : wert !== undefined ? String(wert) : "";
          const ringe = wert === "X" ? 10 : typeof wert === "number" ? wert : null;
          return (
            <li key={id}>
              <button
                type="button"
                className={`${s.schuss} num`}
                data-feld={id}
                data-aktiv={istAktiv || undefined}
                data-leer={text === "" || undefined}
                data-zehn={ringe === 10 || undefined}
                data-null={ringe === 0 || undefined}
                data-fehler={meldungenFuer(fehler, id).length > 0 || undefined}
                disabled={!aktivFeld || !bearbeitbar}
                aria-pressed={istAktiv}
                aria-label={t("schuss.beschriftung", {
                  nr: index + 1,
                  wert: text || t("feld.leer"),
                })}
                onClick={() =>
                  onFeld({
                    id,
                    abschnitt: abschnitt.id,
                    serie: serie.index,
                    key: feld.key,
                    schuss: index,
                    feld,
                  })
                }
              >
                {text}
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Meldungen({
  fehler,
  warnungen,
}: {
  fehler: readonly PfadMeldung[];
  warnungen: readonly PfadMeldung[];
}) {
  if (fehler.length === 0 && warnungen.length === 0) return null;
  return (
    <ul className={s.meldungen}>
      {fehler.map((m) => (
        <li key={`f-${m.pfad}-${m.meldung}`} className={s.meldungFehler} role="alert">
          <CircleAlert aria-hidden />
          {m.meldung}
        </li>
      ))}
      {warnungen.map((m) => (
        <li key={`w-${m.pfad}-${m.meldung}`} className={s.meldungWarnung}>
          <TriangleAlert aria-hidden />
          {m.meldung}
        </li>
      ))}
    </ul>
  );
}
