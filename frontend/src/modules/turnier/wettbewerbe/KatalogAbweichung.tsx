import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { katalogDiffAbfrage } from "../abfragen";
import s from "../turnier.module.css";
import type { Wettbewerb } from "../typen";

/**
 * „Weicht vom Katalog ab: …“ mit den Punkten in Klartext, so wie der Server sie beschreibt
 * (`GET …/competitions/{id}/catalog-diff`). Nichts, solange der Wettbewerb dem Katalog entspricht,
 * er nicht aus dem Katalog stammt oder der Server den Vergleich nicht kennt.
 */
export function KatalogAbweichung({
  turnierId,
  wettbewerb,
}: {
  turnierId: string;
  wettbewerb: Wettbewerb;
}) {
  const { t } = useTranslation("turnier");
  const ausKatalog = Boolean(wettbewerb.catalog_federation && wettbewerb.catalog_code);
  const diff = useQuery({ ...katalogDiffAbfrage(turnierId, wettbewerb.id), enabled: ausKatalog });
  if (!ausKatalog || !diff.data?.deviates) return null;
  const punkte = diff.data.differences.map((eintrag) => eintrag.text).filter(Boolean);
  return (
    <span className={s.katalogAbweichung}>
      <Info aria-hidden size={16} className={s.katalogAbweichungIcon} />
      <span>
        {punkte.length > 0
          ? t("wettbewerb.weicht_ab", { punkte: punkte.join(" · ") })
          : t("wettbewerb.weicht_ab_ohne")}
      </span>
    </span>
  );
}
