import { Button } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { BookOpenCheck, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Chip } from "../../../components/Chip";
import i18n, { aktiveSprache } from "../../../i18n";
import { formatDatum } from "../../../lib/format";
import { katalogDiffAbfrage } from "../abfragen";
import type { Wettbewerb } from "../typen";
import v from "../vorlagen.module.css";

type StandAngaben = Pick<Wettbewerb, "catalog_stand_then" | "catalog_stand_now">;

/** Fehlt die Disziplin (oder Variante) jetzt im Katalog? Dann gibt es nichts zu übernehmen. */
export function disziplinFehlt(wettbewerb: StandAngaben): boolean {
  return !wettbewerb.catalog_stand_now;
}

/**
 * Katalogstand damals → heute in Klartext, z. B. „Katalogstand damals 30.06.2026, heute
 * 01.11.2026“. Gleicher Stand heißt: Der Katalog wurde ohne neues Regelwerk korrigiert.
 */
export function katalogStandText(
  wettbewerb: StandAngaben,
  sprache: string = aktiveSprache(),
): string {
  const t = i18n.getFixedT(sprache, "turnier", "katalog_stand");
  const damals = wettbewerb.catalog_stand_then
    ? formatDatum(wettbewerb.catalog_stand_then, sprache)
    : null;
  const heute = wettbewerb.catalog_stand_now
    ? formatDatum(wettbewerb.catalog_stand_now, sprache)
    : null;
  if (!heute) return damals ? t("fehlt", { damals }) : t("fehlt_ohne");
  if (!damals) return t("nur_heute", { heute });
  if (damals === heute) return t("korrigiert", { damals });
  return t("neu", { damals, heute });
}

/** Kennzeichen in der Wettbewerbsliste; steht, bis der neue Stand übernommen ist. */
export function KatalogGeaendertChip({ wettbewerb }: { wettbewerb: Wettbewerb }) {
  const { t, i18n: sprachen } = useTranslation("turnier");
  if (!wettbewerb.catalog_changed) return null;
  return (
    <Chip ton="info" icon={BookOpenCheck} title={katalogStandText(wettbewerb, sprachen.language)}>
      {disziplinFehlt(wettbewerb) ? t("katalog_stand.chip_fehlt") : t("katalog_stand.chip")}
    </Chip>
  );
}

/** Unterschiede zum aktuellen Katalog in Klartext, wie der Server sie beschreibt. */
export function useKatalogPunkte(turnierId: string, wettbewerb: Wettbewerb) {
  const diff = useQuery({
    ...katalogDiffAbfrage(turnierId, wettbewerb.id),
    enabled: wettbewerb.catalog_changed && !disziplinFehlt(wettbewerb),
  });
  return diff.data ? diff.data.differences.map((d) => d.text).filter(Boolean) : null;
}

/**
 * Oben im geöffneten Wettbewerb: Der Katalog hat sich seit der Übernahme geändert. Zeigt Stand
 * damals → heute und die Unterschiede; „Neuen Stand übernehmen“ (reset-definition) setzt das
 * Kennzeichen auf dem Server zurück.
 */
export function KatalogGeaendertHinweis({
  turnierId,
  wettbewerb,
  gesperrt,
  onUebernehmen,
}: {
  turnierId: string;
  wettbewerb: Wettbewerb;
  gesperrt: boolean;
  onUebernehmen: () => void;
}) {
  const { t, i18n: sprachen } = useTranslation("turnier");
  const punkte = useKatalogPunkte(turnierId, wettbewerb);
  if (!wettbewerb.catalog_changed) return null;
  const fehlt = disziplinFehlt(wettbewerb);
  return (
    <section className={v.kopieHinweis} aria-labelledby={`katalog-stand-${wettbewerb.id}`}>
      <BookOpenCheck aria-hidden className={v.bannerSymbol} />
      <div className={v.bannerText}>
        <strong id={`katalog-stand-${wettbewerb.id}`}>
          {fehlt ? t("katalog_stand.titel_fehlt") : t("katalog_stand.titel")}
        </strong>
        <span>{katalogStandText(wettbewerb, sprachen.language)}</span>
        <span>{fehlt ? t("katalog_stand.text_fehlt") : t("katalog_stand.text")}</span>
        {!fehlt && punkte !== null && (
          <span>
            {punkte.length > 0
              ? t("katalog_stand.unterschiede", { punkte: punkte.join(" · ") })
              : t("katalog_stand.keine_unterschiede")}
          </span>
        )}
      </div>
      {!fehlt && (
        <Button
          variant="default"
          leftSection={<RefreshCw aria-hidden />}
          disabled={gesperrt}
          onClick={onUebernehmen}
        >
          {t("katalog_stand.uebernehmen")}
        </Button>
      )}
    </section>
  );
}
