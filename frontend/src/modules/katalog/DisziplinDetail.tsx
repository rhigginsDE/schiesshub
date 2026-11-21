import { Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowLeft, MousePointerClick, Printer, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { disziplinAbfrage } from "../../api/abfragen";
import type { DisziplinDetail as DisziplinDetailDaten, Variante } from "../../api/typen";
import { PositionsAblauf } from "../../components/anschlag/PositionsAblauf";
import { Chip } from "../../components/Chip";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { beschreibeAbschnitt, schussGesamt } from "./ablauf";
import s from "./katalog.module.css";
import { AUSHANG_PFAD, KATALOG_PFAD, type KatalogSuche } from "./pfade";
import { beschreibeWertung } from "./wertung";

/** Platzhalter in der Detailspalte, solange keine Disziplin gewählt ist (nur auf breiten Bildschirmen sichtbar). */
export function KeineAuswahl() {
  const { t } = useTranslation("katalog");
  return (
    <div className="panel">
      <Leerzustand icon={MousePointerClick} titel={t("auswahl.titel")} text={t("auswahl.text")} />
    </div>
  );
}

interface DisziplinDetailProps {
  verband: string;
  kennziffer: string;
  /** Aktive Filter, damit „Zur Liste“ dorthin zurückführt */
  suche: KatalogSuche;
}

/** Detailansicht einer Disziplin: Stammdaten, Ablauf und Wertung in Klartext. */
export function DisziplinDetail({ verband, kennziffer, suche }: DisziplinDetailProps) {
  const { t } = useTranslation("katalog");
  const abfrage = useQuery(disziplinAbfrage(verband, kennziffer));

  return (
    <article className={`panel ${s.detailPanel}`}>
      <Link to={KATALOG_PFAD} search={suche} className={s.zurueck}>
        <ArrowLeft aria-hidden />
        {t("detail.zurueck")}
      </Link>

      {abfrage.isSuccess && (
        <Link to={AUSHANG_PFAD} params={{ verband, kennziffer }} className={s.aushangLink}>
          <Printer aria-hidden />
          {t("detail.aushang")}
        </Link>
      )}

      {abfrage.isPending ? (
        <div className={s.skelettListe} aria-busy="true">
          <Skeleton height={34} width="70%" radius="sm" />
          <Skeleton height={150} radius="md" />
          <Skeleton height={120} radius="md" />
          <Skeleton height={90} radius="md" />
        </div>
      ) : abfrage.isError ? (
        <Fehlerzustand
          fehler={abfrage.error}
          onErneut={() => void abfrage.refetch()}
          eigene={{
            nicht_gefunden: {
              titel: t("detail.nicht_gefunden_titel", { kennziffer }),
              text: t("detail.nicht_gefunden_text", { verband: verband.toUpperCase() }),
            },
          }}
        />
      ) : (
        <Inhalt disziplin={abfrage.data} />
      )}
    </article>
  );
}

const STAMMDATEN = ["waffe", "munition", "visierung", "anschlag", "scheibe", "hinweis"] as const;

function Inhalt({ disziplin }: { disziplin: DisziplinDetailDaten }) {
  const { t, i18n } = useTranslation("katalog");
  const sprache = i18n.language;
  const wertung = beschreibeWertung(disziplin.wertung, sprache);
  const unsicher = new Set(disziplin.pruefen ?? []);
  const ungeprueft = !disziplin.wertung.geprueft;

  return (
    <>
      <header className={s.detailKopf}>
        <span className={`num ${s.detailKennziffer}`}>
          <span className="nur-screenreader">{t("detail.kennziffer")} </span>
          {disziplin.kennziffer}
        </span>
        <h2 className="h-display">{disziplin.name}</h2>
        <div className={s.chips}>
          <Chip>{disziplin.gruppe_name}</Chip>
          {disziplin.optional && (
            <Chip ton="info" title={t("liste.optional_hinweis")}>
              {t("liste.optional")}
            </Chip>
          )}
          {ungeprueft && (
            <Chip ton="warn" icon={TriangleAlert}>
              {t("detail.ungeprueft")}
            </Chip>
          )}
        </div>
        {ungeprueft && <p className={s.hinweisWarn}>{t("detail.ungeprueft_hinweis")}</p>}
        {disziplin.optional && <p className={s.hinweis}>{t("liste.optional_hinweis")}.</p>}
      </header>

      <section className={s.abschnitt} aria-labelledby="detail-stammdaten">
        <h3 className="h-label" id="detail-stammdaten">
          {t("detail.stammdaten")}
        </h3>
        <dl className={s.stammdaten}>
          {STAMMDATEN.map((feld) =>
            disziplin[feld] ? (
              <div key={feld}>
                <dt>
                  {t(`detail.feld.${feld}`)}
                  {unsicher.has(feld) && (
                    <span className={s.ungeprueft} title={t("detail.unsicher")}>
                      <TriangleAlert aria-hidden />
                      <span className="nur-screenreader">{t("detail.unsicher")}</span>
                    </span>
                  )}
                </dt>
                <dd>{disziplin[feld]}</dd>
              </div>
            ) : null,
          )}
          {disziplin.fruehere_kennziffer && (
            <div>
              <dt>{t("detail.feld.fruehere_kennziffer")}</dt>
              <dd className="num">{disziplin.fruehere_kennziffer}</dd>
            </div>
          )}
        </dl>
      </section>

      <section className={s.abschnitt} aria-labelledby="detail-ablauf">
        <h3 className="h-label" id="detail-ablauf">
          {t("detail.ablauf")}
        </h3>
        {disziplin.ablauf.beschreibung && <p>{disziplin.ablauf.beschreibung}</p>}
        <ul className={s.varianten}>
          {disziplin.ablauf.varianten.map((variante) => (
            <VarianteKarte
              key={variante.id}
              variante={variante}
              sprache={sprache}
              mitName={disziplin.ablauf.varianten.length > 1}
            />
          ))}
        </ul>
        <p className={s.hinweis}>{t("detail.ablauf_je_serie")}</p>
        <Positionen variante={disziplin.ablauf.varianten[0]} />
      </section>

      <section className={s.abschnitt} aria-labelledby="detail-wertung">
        <h3 className="h-label" id="detail-wertung">
          {t("detail.wertung")}
        </h3>
        <div className={`inset ${s.wertung}`}>
          <strong>{wertung.name}</strong>
          <p>{wertung.saetze.join(" ")}</p>
          {wertung.gleichstand ? (
            <div>
              <p>{t("wertung.gleichstand.titel")}:</p>
              <ol className={s.gleichstand}>
                {wertung.gleichstand.map((kriterium) => (
                  <li key={kriterium}>{kriterium}</li>
                ))}
              </ol>
            </div>
          ) : (
            <p className="gedaempft">{t("wertung.gleichstand.keine_regel")}</p>
          )}
        </div>
      </section>

      <p className={s.hinweis}>{t("detail.haftung")}</p>
    </>
  );
}

/**
 * Anschläge je Position als Ablauf-Darstellung. Die Positionen sind in allen Varianten gleich
 * (Varianten unterscheiden sich in Zeiten), daher genügt die erste Variante.
 */
function Positionen({ variante }: { variante: Variante | undefined }) {
  const mitPositionen = variante?.abschnitte.filter((a) => a.positionen?.length) ?? [];
  if (mitPositionen.length === 0) return null;
  return (
    <div className={s.positionen}>
      {mitPositionen.map((abschnitt, index) => (
        <div key={abschnitt.id} className={s.positionenAbschnitt}>
          <h4 className="h-label">{abschnitt.name}</h4>
          <PositionsAblauf
            label={abschnitt.name}
            positionen={abschnitt.positionen ?? []}
            trefferaufnahmeNach={abschnitt.trefferaufnahme_nach}
            serienGewertet={abschnitt.serien_gewertet}
            schussJeSerie={abschnitt.schuss_je_serie}
            zeitJeSerieS={abschnitt.zeit_je_serie_s}
            ton={index === 0 ? "a" : "b"}
          />
        </div>
      ))}
    </div>
  );
}

interface VarianteKarteProps {
  variante: Variante;
  sprache: string;
  mitName: boolean;
}

function VarianteKarte({ variante, sprache, mitName }: VarianteKarteProps) {
  const { t } = useTranslation("katalog");
  const gesamt = schussGesamt(variante);
  const mitAbschnittName = variante.abschnitte.length > 1;

  return (
    <li className={`inset ${s.variante}`}>
      {(mitName || gesamt !== null) && (
        <div className={s.varianteKopf}>
          {mitName && <strong>{variante.name}</strong>}
          {gesamt !== null && (
            <span className={`num ${s.gesamt}`}>
              {t("detail.schuss_gesamt", { count: gesamt })}
            </span>
          )}
        </div>
      )}
      <ul className={s.abschnitte}>
        {variante.abschnitte.map((abschnitt) => (
          <li key={abschnitt.id} className={s.abschnittZeile}>
            {mitAbschnittName && <span className={s.abschnittName}>{abschnitt.name}</span>}
            <span className={s.teile}>
              {beschreibeAbschnitt(abschnitt, sprache).map((teil) => (
                <span key={teil} className={s.teil}>
                  {teil}
                </span>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </li>
  );
}
