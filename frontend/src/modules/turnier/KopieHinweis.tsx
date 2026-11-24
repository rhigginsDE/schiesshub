import { Button } from "@mantine/core";
import { Link } from "@tanstack/react-router";
import { ArrowRight, BookOpenCheck } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { hinweisAusblenden, hinweisAusgeblendet, hinweisKennung, katalogGeaendert } from "./anfang";
import { EINRICHTEN_PFAD } from "./pfade";
import type { TurnierUebersicht } from "./typen";
import v from "./vorlagen.module.css";
import { katalogStandText } from "./wettbewerbe/KatalogStand";

/**
 * Oben in der Einrichtung: Bei welchen Wettbewerben sich der Katalog seit der Übernahme geändert
 * hat (typisch nach „Wie ein früheres Turnier“), mit Katalogstand damals → heute und dem Weg zum
 * Prüfen. Die Angabe kommt vom Server (`catalog_changed`) und gilt damit auf jedem Gerät; ein
 * Wettbewerb fällt heraus, sobald sein neuer Stand übernommen ist. „Ausblenden“ gilt nur auf
 * diesem Gerät und nur hier – das Kennzeichen am Wettbewerb bleibt.
 */
export function KopieHinweis({ turnier }: { turnier: TurnierUebersicht }) {
  const { t, i18n } = useTranslation("turnier");
  const offen = katalogGeaendert(turnier.competitions);
  const kennung = hinweisKennung(offen);
  const [ausgeblendet, setAusgeblendet] = useState<string | null>(() =>
    hinweisAusgeblendet(turnier.id, kennung) ? kennung : null,
  );
  if (offen.length === 0 || ausgeblendet === kennung) return null;

  const ausblenden = () => {
    hinweisAusblenden(turnier.id, kennung);
    setAusgeblendet(kennung);
  };

  return (
    <section className={v.kopieHinweis} aria-labelledby="kopie-hinweis-titel">
      <BookOpenCheck aria-hidden className={v.bannerSymbol} />
      <div className={v.bannerText}>
        <strong id="kopie-hinweis-titel">
          {t("kopie_hinweis.titel", { count: offen.length })}
        </strong>
        <span>{t("kopie_hinweis.text", { count: offen.length })}</span>
        <ul className={v.kopieListe}>
          {offen.map((wettbewerb) => (
            <li key={wettbewerb.id} className={v.kopieEintrag}>
              <span className={v.kopieEintragText}>
                <strong>
                  {wettbewerb.catalog_code ? `${wettbewerb.catalog_code} · ` : ""}
                  {wettbewerb.name}
                </strong>
                <span>{katalogStandText(wettbewerb, i18n.language)}</span>
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
