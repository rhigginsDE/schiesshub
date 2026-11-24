import { Link } from "@tanstack/react-router";
import { BookX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { KATALOG_PFAD } from "../katalog/pfade";
import type { VorlagenLuecke } from "./senden";
import s from "./turnier.module.css";
import v from "./vorlagen.module.css";

/**
 * 409 `template_unavailable` in Klartext: was im Katalog fehlt („Kennziffer 4403 (BDS) fehlt im
 * Katalog.“), dass nichts angelegt wurde und was man stattdessen tun kann.
 */
export function VorlageFehlt({
  luecken,
  vorlage,
  uebung = false,
  onKatalog,
}: {
  luecken: readonly VorlagenLuecke[];
  /** Name der Vorlage; beim Übungsturnier leer */
  vorlage?: string;
  uebung?: boolean;
  /** Vor dem Wechsel in den Katalog, z. B. einen Dialog schließen */
  onKatalog?: () => void;
}) {
  const { t } = useTranslation("turnier");
  return (
    <div className={v.vorlageFehltKasten} role="alert">
      <BookX aria-hidden className={v.vorlageFehltSymbol} />
      <div className={v.bannerText}>
        <strong>
          {uebung
            ? t("vorlage_fehlt.titel_uebung")
            : vorlage
              ? t("vorlage_fehlt.titel", { name: vorlage })
              : t("vorlage_fehlt.titel_ohne")}
        </strong>
        {luecken.length > 0 && (
          <ul className={v.lueckenListe}>
            {luecken.map((luecke) => (
              <li key={`${luecke.kind}-${luecke.federation}-${luecke.code}-${luecke.variant_id}`}>
                {t(`vorlage_fehlt.eintrag_${luecke.kind}`, { was: luecke.message_de })}
              </li>
            ))}
          </ul>
        )}
        <span>{uebung ? t("vorlage_fehlt.rat_uebung") : t("vorlage_fehlt.rat")}</span>
        <Link to={KATALOG_PFAD} className={s.textLink} onClick={onKatalog}>
          {t("vorlage_fehlt.katalog")}
        </Link>
      </div>
    </div>
  );
}
