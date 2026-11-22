import { Button } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, CircleCheck, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { disziplinAbfrage } from "../../../api/abfragen";
import { useModule } from "../../../app/modul";
import { Chip } from "../../../components/Chip";
import { ExportKnoepfe } from "../../../components/ExportKnoepfe";
import { formatGeld } from "../../../components/geld";
import { merkeTurnier } from "../../../components/useAktivesTurnier";
import { formatZahl } from "../../../lib/format";
import { katalogDiffAbfrage } from "../abfragen";
import a from "../aufgaben.module.css";
import { planungKurz, startsKurz, zeitraum } from "../klartext";
import { StatusAktionen, StatusChip } from "../Status";
import s from "../turnier.module.css";
import type { TurnierUebersicht, Wettbewerb } from "../typen";
import {
  type Bereich,
  ersterOffenerSchritt,
  type OffenerPunkt,
  type SchrittZustand,
} from "../vollstaendigkeit";
import { KatalogAbweichung } from "../wettbewerbe/KatalogAbweichung";
import { abweichungen } from "../wettbewerbFormular";
import { BereichKopf } from "./Bausteine";

interface ZusammenfassungProps {
  turnier: TurnierUebersicht;
  punkte: OffenerPunkt[];
  schritte: readonly Bereich[];
  zustaende: Record<Bereich, SchrittZustand>;
  onBereich: (bereich: Bereich) => void;
}

/**
 * Letzter Schritt: was noch fehlt und was als Nächstes zu tun ist, mit genau einer Hauptaktion –
 * „Weiter mit …“, solange etwas fehlt, sonst „Turnier starten“. Darunter das Turnier auf einen Blick.
 */
export function Zusammenfassung({
  turnier,
  punkte,
  schritte,
  zustaende,
  onBereich,
}: ZusammenfassungProps) {
  const { t, i18n } = useTranslation("turnier");
  const sprache = i18n.language;
  const hinweise = punkte.map((punkt) => t(`offen.${punkt.schluessel}`, punkt.werte ?? {}));
  const offen = ersterOffenerSchritt(zustaende, schritte);
  const entwurf = turnier.status === "draft";
  const fehlt = entwurf && punkte.length > 0;
  const mitAnmeldung = useModule().some((modul) => modul.id === "anmeldung");

  return (
    <div className={s.bereich}>
      <BereichKopf
        titel={t("bereich.zusammenfassung.titel")}
        text={t("bereich.zusammenfassung.text")}
      />

      <section className={`panel ${a.naechster}`} aria-labelledby="zf-naechster">
        <h3 className="h-section" id="zf-naechster">
          {t("zusammenfassung.naechster_titel")}
        </h3>
        {fehlt ? (
          <>
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
            <p>{t("zusammenfassung.naechster_fehlt", { name: t(`bereich.${offen}.titel`) })}</p>
            <div className={a.naechsterAktionen}>
              <Button
                size="md"
                rightSection={<ArrowRight aria-hidden />}
                onClick={() => onBereich(offen)}
              >
                {t("aufgaben.weiter_mit", { name: t(`bereich.${offen}.titel`) })}
              </Button>
              <StatusAktionen turnier={turnier} darstellung="knoepfe" hinweiseVorStart={hinweise} />
            </div>
            <p className={s.hilfe}>{t("zusammenfassung.trotzdem")}</p>
          </>
        ) : (
          <>
            {entwurf && (
              <p className={s.okText}>
                <CircleCheck aria-hidden />
                {t("zusammenfassung.vollstaendig")}
              </p>
            )}
            {turnier.status === "active" ? (
              // Gestartet: klar sagen, dass es läuft, und den nächsten Schritt anbieten. Abschließen
              // und Zurück in den Entwurf bleiben nachrangig.
              <>
                <p className={s.okText} role="status">
                  <CircleCheck aria-hidden />
                  {t("zusammenfassung.laeuft_titel")}
                </p>
                <p>{t("zusammenfassung.status_text.active")}</p>
                <div className={a.naechsterAktionen}>
                  {mitAnmeldung && (
                    <Button
                      size="md"
                      rightSection={<ArrowRight aria-hidden />}
                      renderRoot={(props) => (
                        <Link {...props} to="/anmeldung" onClick={() => merkeTurnier(turnier.id)} />
                      )}
                    >
                      {t("zusammenfassung.zur_anmeldung")}
                    </Button>
                  )}
                  <StatusAktionen turnier={turnier} darstellung="knoepfe" />
                </div>
              </>
            ) : (
              <>
                <p>{t(`zusammenfassung.status_text.${turnier.status}`)}</p>
                <StatusAktionen
                  turnier={turnier}
                  darstellung="knoepfe"
                  startenPrimaer
                  hinweiseVorStart={hinweise}
                />
              </>
            )}
          </>
        )}
      </section>

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
          <p className="gedaempft">
            {t("offen.kein_wettbewerb")}{" "}
            <button type="button" className={s.textKnopf} onClick={() => onBereich("wettbewerbe")}>
              {t("zusammenfassung.zu_wettbewerben")}
            </button>
          </p>
        ) : (
          <ul className={s.zfListe}>
            {turnier.competitions.map((wettbewerb) => (
              <ZusammenfassungZeile key={wettbewerb.id} turnier={turnier} wettbewerb={wettbewerb} />
            ))}
          </ul>
        )}
      </section>

      <ExportKnoepfe turnierId={turnier.id} uebersicht={turnier} darstellung="abschnitt" />
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
        {wettbewerb.catalog_code ?? <span className={s.eigen}>{t("zusammenfassung.frei")}</span>}
      </span>
      <span className={s.zeileText}>
        <strong>{wettbewerb.name}</strong>
        <span className="gedaempft">
          {stand ? stand.name : t("wettbewerb.ohne_stand")} · {planungKurz(wettbewerb, sprache)} ·{" "}
          {startsKurz(wettbewerb, sprache)}
        </span>
        <KatalogAbweichung turnierId={turnier.id} wettbewerb={wettbewerb} />
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
          <Chip>{t("zusammenfassung.frei_lang")}</Chip>
        ) : anzahl === null ? null : anzahl === 0 ? (
          <Chip ton="gruen">{t("zusammenfassung.wie_katalog")}</Chip>
        ) : (
          <Chip ton="info">{t("wettbewerb.abweichungen", { count: anzahl })}</Chip>
        )}
      </span>
    </li>
  );
}
