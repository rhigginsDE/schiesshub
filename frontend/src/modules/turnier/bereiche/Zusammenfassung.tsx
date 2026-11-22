import { useQuery } from "@tanstack/react-query";
import { CircleCheck, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { disziplinAbfrage } from "../../../api/abfragen";
import { Chip } from "../../../components/Chip";
import { ExportKnoepfe } from "../../../components/ExportKnoepfe";
import { formatGeld } from "../../../components/geld";
import { formatZahl } from "../../../lib/format";
import { katalogDiffAbfrage } from "../abfragen";
import { planungKurz, startsKurz, zeitraum } from "../klartext";
import { StatusAktionen, StatusChip } from "../Status";
import s from "../turnier.module.css";
import type { TurnierUebersicht, Wettbewerb } from "../typen";
import type { Bereich, OffenerPunkt } from "../vollstaendigkeit";
import { abweichungen } from "../wettbewerbFormular";
import { BereichKopf } from "./Bausteine";

interface ZusammenfassungProps {
  turnier: TurnierUebersicht;
  punkte: OffenerPunkt[];
  onBereich: (bereich: Bereich) => void;
}

export function Zusammenfassung({ turnier, punkte, onBereich }: ZusammenfassungProps) {
  const { t, i18n } = useTranslation("turnier");
  const sprache = i18n.language;
  const hinweise = punkte.map((punkt) => t(`offen.${punkt.schluessel}`, punkt.werte ?? {}));

  return (
    <div className={s.bereich}>
      <BereichKopf
        titel={t("bereich.zusammenfassung.titel")}
        text={t("bereich.zusammenfassung.text")}
      />

      <section className={`panel ${s.formular}`} aria-labelledby="zf-kopf">
        <div className={s.zfKopf}>
          <div>
            <h3 className="h-section" id="zf-kopf">
              {turnier.name}
            </h3>
            <p className="gedaempft">
              <span className="num">{zeitraum(turnier, sprache)}</span>
              {turnier.organizer && ` · ${turnier.organizer}`}
              {` · ${t(`vorlage.${turnier.template}.name`)}`}
            </p>
          </div>
          <StatusChip status={turnier.status} />
        </div>
        <dl className={s.kennzahlen}>
          <div>
            <dt>{t("zusammenfassung.staende")}</dt>
            <dd>
              {turnier.ranges.length === 0
                ? t("zusammenfassung.keine")
                : turnier.ranges
                    .map((r) => t("zusammenfassung.stand", { name: r.name, count: r.lane_count }))
                    .join(", ")}
            </dd>
          </div>
          <div>
            <dt>{t("zusammenfassung.klassen")}</dt>
            <dd>
              {turnier.classes.length === 0
                ? t("zusammenfassung.keine")
                : turnier.classes.map((k) => k.short).join(", ")}
            </dd>
          </div>
          <div>
            <dt>{t("zusammenfassung.einspruch")}</dt>
            <dd>
              {turnier.settings.protest_minutes
                ? t("zusammenfassung.minuten", {
                    wert: formatZahl(turnier.settings.protest_minutes, {}, sprache),
                  })
                : t("zusammenfassung.aus")}
            </dd>
          </div>
        </dl>
      </section>

      <section className="panel" aria-labelledby="zf-wettbewerbe">
        <h3 className="h-section" id="zf-wettbewerbe">
          {t("wettbewerb.im_turnier", { count: turnier.competitions.length })}
        </h3>
        {turnier.competitions.length === 0 ? (
          <p className="gedaempft">{t("offen.kein_wettbewerb")}</p>
        ) : (
          <ul className={s.zfListe}>
            {turnier.competitions.map((wettbewerb) => (
              <ZusammenfassungZeile key={wettbewerb.id} turnier={turnier} wettbewerb={wettbewerb} />
            ))}
          </ul>
        )}
      </section>

      <ExportKnoepfe turnierId={turnier.id} uebersicht={turnier} darstellung="abschnitt" />

      <section className={`panel ${s.formular}`} aria-labelledby="zf-status">
        <h3 className="h-section" id="zf-status">
          {t("zusammenfassung.status_titel")}
        </h3>
        {punkte.length === 0 ? (
          <p className={s.okText}>
            <CircleCheck aria-hidden />
            {t("zusammenfassung.vollstaendig")}
          </p>
        ) : (
          <div className={s.warnKasten}>
            <TriangleAlert aria-hidden />
            <div>
              <strong>{t("zusammenfassung.offen_titel")}</strong>
              <ul className={s.punktListe}>
                {punkte.map((punkt, nr) => (
                  <li key={`${punkt.schluessel}-${punkt.werte?.name ?? ""}`}>
                    <button
                      type="button"
                      className={s.textKnopf}
                      onClick={() => onBereich(punkt.bereich)}
                    >
                      {hinweise[nr]}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
        <p className={s.hilfe}>{t(`zusammenfassung.status_text.${turnier.status}`)}</p>
        <StatusAktionen
          turnier={turnier}
          darstellung="knoepfe"
          startenPrimaer
          hinweiseVorStart={hinweise}
        />
      </section>
    </div>
  );
}

function ZusammenfassungZeile({
  turnier,
  wettbewerb,
}: {
  turnier: TurnierUebersicht;
  wettbewerb: Wettbewerb;
}) {
  const { t, i18n } = useTranslation("turnier");
  const sprache = i18n.language;
  const waehrung = turnier.settings.currency;
  const stand = turnier.ranges.find((r) => r.id === wettbewerb.range_id);
  const ausKatalog = Boolean(wettbewerb.catalog_federation && wettbewerb.catalog_code);
  const diff = useQuery({ ...katalogDiffAbfrage(turnier.id, wettbewerb.id), enabled: ausKatalog });
  // Fehlt der Endpunkt, vergleicht die Oberfläche selbst mit dem Katalog.
  const katalog = useQuery({
    ...disziplinAbfrage(wettbewerb.catalog_federation ?? "", wettbewerb.catalog_code ?? ""),
    enabled: ausKatalog && diff.isSuccess && diff.data === null,
  });
  const eigeneZaehlung = abweichungen(
    wettbewerb.definition.variant.abschnitte,
    katalog.data?.ablauf.varianten.find((v) => v.id === wettbewerb.definition.variant.id),
  );
  const anzahl = diff.data
    ? diff.data.differences.length
    : eigeneZaehlung
      ? eigeneZaehlung.length
      : null;

  return (
    <li className={s.zfZeile}>
      <span className={`num ${s.kennziffer}`}>
        {wettbewerb.catalog_code ?? <span className={s.eigen}>{t("wettbewerb.eigen")}</span>}
      </span>
      <span className={s.zeileText}>
        <strong>{wettbewerb.name}</strong>
        <span className="gedaempft">
          {stand ? stand.name : t("wettbewerb.ohne_stand")} · {planungKurz(wettbewerb, sprache)} ·{" "}
          {startsKurz(wettbewerb, sprache)}
        </span>
      </span>
      <span className={`num ${s.zfGeld}`}>
        {formatGeld(wettbewerb.fee_first_cents, waehrung, sprache)}
        {wettbewerb.multi_start && (
          <span className="gedaempft">
            {" "}
            / {formatGeld(wettbewerb.fee_repeat_cents, waehrung, sprache)}
          </span>
        )}
      </span>
      <span>
        {!ausKatalog ? (
          <Chip>{t("wettbewerb.eigen_lang")}</Chip>
        ) : anzahl === null ? null : anzahl === 0 ? (
          <Chip ton="gruen">{t("zusammenfassung.wie_katalog")}</Chip>
        ) : (
          <Chip ton="info">{t("wettbewerb.abweichungen", { count: anzahl })}</Chip>
        )}
      </span>
    </li>
  );
}
