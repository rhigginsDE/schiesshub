import { Button, NativeSelect, Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowLeft, Printer, TriangleAlert } from "lucide-react";
import { type CSSProperties, useEffect } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { disziplinAbfrage, verbaendeAbfrage } from "../../api/abfragen";
import type { DisziplinDetail, Variante, Verband } from "../../api/typen";
import { Piktogramm } from "../../components/anschlag/Piktogramm";
import { PositionsAblauf } from "../../components/anschlag/PositionsAblauf";
import type { Hand } from "../../components/anschlag/typen";
import { Fehlerzustand } from "../../components/Zustand";
import { formatDatum } from "../../lib/format";
import { farbschemata } from "../../theme";
import { beschreibeAbschnitt, schussGesamt } from "./ablauf";
import s from "./aushang.module.css";
import {
  ganzzahl,
  nurZeitVarianten,
  ohneSollzeiten,
  sollzeitTabelle,
  verwendeteHaende,
  zeitTabelle,
} from "./aushangDaten";
import { DISZIPLIN_PFAD } from "./pfade";
import { beschreibeWertung } from "./wertung";

/** Das Blatt ist immer hell, auch im dunklen Farbschema: Farbrollen aus dem hellen Schema. */
const hell = farbschemata.light;
const HELLE_FARBEN = {
  "--sh-bg": hell.bg,
  "--sh-flaeche": hell.flaeche,
  "--sh-flaeche-2": hell.flaeche2,
  "--sh-linie": hell.linie,
  "--sh-linie-stark": hell.linieStark,
  "--sh-text": hell.text,
  "--sh-text-weich": hell.textWeich,
  "--sh-text-gedaempft": hell.textGedaempft,
  "--sh-akzent-text": hell.akzentText,
  "--sh-warn": hell.warn,
  "--sh-warn-flaeche": hell.warnFlaeche,
  "--sh-warn-linie": hell.warnLinie,
  "--sh-info": hell.info,
  "--sh-info-flaeche": hell.infoFlaeche,
} as CSSProperties;

const STAMMDATEN = ["waffe", "munition", "visierung", "anschlag", "scheibe", "hinweis"] as const;

interface AushangProps {
  verband: string;
  kennziffer: string;
  /** Gewählte Variante (id); ohne Angabe die erste */
  variante?: string;
  onVarianteAendern: (variante: string) => void;
}

/**
 * Druckansicht einer Disziplin als A4-Aushang. Liegt als Ebene über der App;
 * beim Drucken erscheint nur das Blatt. Alle Inhalte kommen aus dem Katalog.
 */
export function Aushang({ verband, kennziffer, variante, onVarianteAendern }: AushangProps) {
  const { t } = useTranslation("katalog");
  const abfrage = useQuery(disziplinAbfrage(verband, kennziffer));
  const verbaende = useQuery(verbaendeAbfrage());
  const verbandDaten = verbaende.data?.find((v) => v.id === verband);

  // Druckregeln des Aushangs nur aktiv, solange er offen ist (siehe aushang.module.css)
  useEffect(() => {
    document.documentElement.dataset.druck = "aushang";
    return () => {
      delete document.documentElement.dataset.druck;
    };
  }, []);

  useEffect(() => {
    const vorher = document.title;
    document.title = t("aushang.seitentitel", { kennziffer });
    return () => {
      document.title = vorher;
    };
  }, [t, kennziffer]);

  const varianten = abfrage.data?.ablauf.varianten ?? [];
  const nurZeiten = nurZeitVarianten(varianten);
  const auswahl = varianten.find((v) => v.id === variante) ?? varianten[0];

  return createPortal(
    <div className={s.ebene} data-aushang="">
      <div className={s.werkzeug}>
        <Link to={DISZIPLIN_PFAD} params={{ verband, kennziffer }} className={s.zurueck}>
          <ArrowLeft aria-hidden />
          {t("aushang.zurueck")}
        </Link>
        {varianten.length > 1 && !nurZeiten && auswahl && (
          <NativeSelect
            label={t("aushang.variante")}
            value={auswahl.id}
            onChange={(e) => onVarianteAendern(e.currentTarget.value)}
            data={varianten.map((v) => ({ value: v.id, label: v.name }))}
            className={s.auswahl}
          />
        )}
        <p className={s.druckHinweis}>{t("aushang.drucken_hinweis")}</p>
        <Button
          leftSection={<Printer size={18} aria-hidden />}
          onClick={() => window.print()}
          disabled={!abfrage.isSuccess}
        >
          {t("aushang.drucken")}
        </Button>
      </div>

      <div className={s.blatt} style={HELLE_FARBEN}>
        {abfrage.isPending ? (
          <div className={s.skelett} aria-busy="true">
            <Skeleton height={48} width="70%" />
            <Skeleton height={220} />
            <Skeleton height={220} />
          </div>
        ) : abfrage.isError ? (
          <Fehlerzustand fehler={abfrage.error} onErneut={() => void abfrage.refetch()} />
        ) : auswahl ? (
          <Blatt
            disziplin={abfrage.data}
            variante={auswahl}
            alleVarianten={varianten}
            nurZeiten={nurZeiten}
            verband={verbandDaten}
          />
        ) : null}
      </div>
    </div>,
    document.body,
  );
}

interface BlattProps {
  disziplin: DisziplinDetail;
  variante: Variante;
  alleVarianten: Variante[];
  nurZeiten: boolean;
  verband: Verband | undefined;
}

function Blatt({ disziplin, variante, alleVarianten, nurZeiten, verband }: BlattProps) {
  const { t, i18n } = useTranslation("katalog");
  const sprache = i18n.language;
  const wertung = beschreibeWertung(disziplin.wertung, sprache);
  const gesamt = schussGesamt(variante);
  const haende = verwendeteHaende(variante);
  const mehrereAbschnitte = variante.abschnitte.length > 1;
  const zeigeVariantenName = alleVarianten.length > 1 && !nurZeiten;

  return (
    <article className={s.inhalt} lang={sprache}>
      <header className={s.kopf}>
        <div className={s.kopfText}>
          <p className={s.ueberzeile}>
            {t("aushang.kopf", {
              verband: verband?.kuerzel ?? disziplin.verband.toUpperCase(),
              gruppe: disziplin.gruppe_name,
            })}
            {zeigeVariantenName && ` · ${variante.name}`}
          </p>
          <h1 className={s.titel}>
            <span className="num">{disziplin.kennziffer}</span> {disziplin.name}
          </h1>
        </div>
        {gesamt !== null && (
          <p className={s.gesamt}>
            <span className="num">{ganzzahl(gesamt, sprache)}</span>{" "}
            <span>{t("aushang.schuss")}</span>
          </p>
        )}
      </header>

      {!disziplin.wertung.geprueft && (
        <p className={s.warnung}>
          <TriangleAlert aria-hidden />
          {t("detail.ungeprueft_hinweis")}
        </p>
      )}

      {variante.abschnitte.map((abschnitt, index) => {
        const sollzeiten = nurZeiten ? sollzeitTabelle(alleVarianten, index, sprache) : [];
        const zeiten = zeitTabelle(abschnitt, sprache);
        // Stehen Sollzeit und Abbruch je Variante in der Tabelle darunter, nennt die Kopfzeile
        // sie nicht noch einmal (sonst stünde dort nur der Wert der ersten Variante).
        const teile = beschreibeAbschnitt(
          sollzeiten.length > 0 ? ohneSollzeiten(abschnitt) : abschnitt,
          sprache,
        );
        const abzug = disziplin.wertung.abzug_je_voller_sekunde_ueber_sollzeit;
        return (
          <section key={abschnitt.id} className={s.abschnitt}>
            <div className={s.abschnittKopf} data-ton={index % 2 === 0 ? "a" : "b"}>
              <h2>
                {mehrereAbschnitte
                  ? t("aushang.abschnitt", { nr: index + 1, name: abschnitt.name })
                  : abschnitt.name}
              </h2>
              <p>{teile.join(" · ")}</p>
            </div>

            {abschnitt.positionen && abschnitt.positionen.length > 0 && (
              <PositionsAblauf
                label={abschnitt.name}
                positionen={abschnitt.positionen}
                trefferaufnahmeNach={abschnitt.trefferaufnahme_nach}
                serienGewertet={abschnitt.serien_gewertet}
                schussJeSerie={abschnitt.schuss_je_serie}
                zeitJeSerieS={abschnitt.zeit_je_serie_s}
                ton={index % 2 === 0 ? "a" : "b"}
              />
            )}

            {sollzeiten.length > 0 && (
              <div className={s.kasten}>
                {typeof abzug === "number" && (
                  <p>{t("aushang.sollzeit.erklaerung", { count: abzug })}</p>
                )}
                <table className={s.tabelle}>
                  <thead>
                    <tr>
                      <th scope="col">{t("aushang.sollzeit.variante")}</th>
                      <th scope="col">{t("aushang.sollzeit.sollzeit")}</th>
                      <th scope="col">{t("aushang.sollzeit.abbruch")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sollzeiten.map((zeile) => (
                      <tr key={zeile.variante}>
                        <td>{zeile.variante}</td>
                        <td className="num">
                          <strong>{zeile.sollzeit}</strong>
                        </td>
                        <td className="num">{zeile.abbruch ?? "–"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {zeiten.length > 0 && (
              <div className={s.kasten}>
                {/* Titel bewusst kein <caption>: Chromium streckt eine Tabelle mit caption beim
                    Seitenumbruch für den Druck (Aushang 4403 lief so auf mehrere Seiten). */}
                <p className={s.tabellenTitel} id={`${abschnitt.id}-zeit`}>
                  {t("aushang.zeit.titel")}
                </p>
                <table className={s.tabelle} aria-labelledby={`${abschnitt.id}-zeit`}>
                  <thead>
                    <tr>
                      <th scope="col">{t("aushang.zeit.fall")}</th>
                      <th scope="col">{t("aushang.zeit.ergebnis")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {zeiten.map((zeile) => (
                      <tr key={zeile.fall}>
                        <td>{zeile.fall}</td>
                        <td>
                          <strong>{zeile.zeit}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        );
      })}

      <div className={s.spalten}>
        <section>
          <h2 className={s.spaltenTitel}>{t("aushang.eckdaten")}</h2>
          <dl className={s.daten}>
            {STAMMDATEN.map((feld) =>
              disziplin[feld] ? (
                <div key={feld}>
                  <dt>{t(`detail.feld.${feld}`)}</dt>
                  <dd>{disziplin[feld]}</dd>
                </div>
              ) : null,
            )}
          </dl>
        </section>
        <section>
          <h2 className={s.spaltenTitel}>{t("detail.wertung")}</h2>
          <p className={s.wertungName}>{wertung.name}</p>
          <p>{wertung.saetze.join(" ")}</p>
          {wertung.gleichstand ? (
            <>
              <p>{t("wertung.gleichstand.titel")}:</p>
              <ol className={s.gleichstand}>
                {wertung.gleichstand.map((kriterium) => (
                  <li key={kriterium}>{kriterium}</li>
                ))}
              </ol>
            </>
          ) : (
            <p className={s.gedaempft}>{t("wertung.gleichstand.keine_regel")}</p>
          )}
        </section>
      </div>

      <footer className={s.fuss}>
        {haende.length > 0 && (
          <ul className={s.legende} aria-label={t("anschlag.legende.titel")}>
            {haende.map((hand) => (
              <li key={hand}>
                <span className={s.legendeBild}>
                  <Piktogramm haltung="stehend" hand={hand as Hand} />
                </span>
                {t(`anschlag.legende.${hand}`)}
              </li>
            ))}
          </ul>
        )}
        <p>
          {verband &&
            `${t("aushang.quelle", {
              regelwerk: verband.regelwerk.name,
              stand: formatDatum(verband.regelwerk.stand, sprache),
            })} · `}
          {t("aushang.massgeblich")}
        </p>
      </footer>
    </article>
  );
}
