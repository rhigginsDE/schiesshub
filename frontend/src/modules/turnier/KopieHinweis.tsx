import { Button } from "@mantine/core";
import { useQueries } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, BookOpenCheck } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { katalogDiffAbfrage } from "./abfragen";
import { leseKopieHinweis, vergissKopieHinweis } from "./anfang";
import { EINRICHTEN_PFAD } from "./pfade";
import type { TurnierUebersicht } from "./typen";
import v from "./vorlagen.module.css";

/**
 * Nach „Wie ein früheres Turnier“: Welche Wettbewerbe sich seit dem Vorbild im Katalog geändert
 * haben, mit dem Weg zum Prüfen. Steht nur in der Turnierverwaltung (Entscheidung 22.11.2026).
 * Ein Wettbewerb fällt heraus, sobald er dem Katalog entspricht (Stand übernommen); der ganze
 * Hinweis auf „Geprüft, ausblenden“.
 */
export function KopieHinweis({ turnier }: { turnier: TurnierUebersicht }) {
  const { t } = useTranslation("turnier");
  const [daten, setDaten] = useState(() => leseKopieHinweis(turnier.id));
  const vorhanden = new Set(turnier.competitions.map((w) => w.id));
  const wettbewerbe = daten?.wettbewerbe.filter((w) => vorhanden.has(w.id)) ?? [];
  // Der aktuelle Vergleich mit dem Katalog; ohne Antwort gilt, was beim Kopieren gemeldet wurde.
  const vergleiche = useQueries({
    queries: wettbewerbe.map((w) => katalogDiffAbfrage(turnier.id, w.id)),
  });
  const offen = wettbewerbe.flatMap((wettbewerb, nr) => {
    const vergleich = vergleiche[nr]?.data;
    if (vergleich?.deviates === false) return [];
    const punkte = vergleich
      ? vergleich.differences.map((d) => d.text).filter(Boolean)
      : wettbewerb.punkte;
    return [{ ...wettbewerb, punkte }];
  });
  if (!daten || offen.length === 0) return null;

  const ausblenden = () => {
    vergissKopieHinweis(turnier.id);
    setDaten(null);
  };

  return (
    <section className={v.kopieHinweis} aria-labelledby="kopie-hinweis-titel">
      <BookOpenCheck aria-hidden className={v.bannerSymbol} />
      <div className={v.bannerText}>
        <strong id="kopie-hinweis-titel">
          {t("kopie_hinweis.titel", { quelle: daten.quelle })}
        </strong>
        <span>{t("kopie_hinweis.text", { count: offen.length })}</span>
        <ul className={v.kopieListe}>
          {offen.map((wettbewerb) => (
            <li key={wettbewerb.id} className={v.kopieEintrag}>
              <span className={v.kopieEintragText}>
                <strong>{wettbewerb.name}</strong>
                <span>
                  {wettbewerb.punkte.length > 0
                    ? t("kopie_hinweis.unterschied", { punkte: wettbewerb.punkte.join(" · ") })
                    : t("kopie_hinweis.ohne_punkte")}
                </span>
              </span>
              <Button
                variant="default"
                rightSection={<ArrowRight aria-hidden />}
                aria-label={t("kopie_hinweis.pruefen_lang", { name: wettbewerb.name })}
                renderRoot={(props) => (
                  <Link
                    {...props}
                    to={EINRICHTEN_PFAD}
                    params={{ turnierId: turnier.id }}
                    search={{ bereich: "wettbewerbe", wettbewerb: wettbewerb.id }}
                  />
                )}
              >
                {t("kopie_hinweis.pruefen")}
              </Button>
            </li>
          ))}
        </ul>
        <div className={v.kopieAktionen}>
          <Button variant="subtle" color="gray" onClick={ausblenden}>
            {t("kopie_hinweis.ausblenden")}
          </Button>
        </div>
      </div>
    </section>
  );
}
