import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { FeedPerson, FeedZeile } from "../typen";
import s from "./schirm.module.css";

/** Kopf eines Szenen-Abschnitts: kleine Überschrift, Titel, rechts Zusatz. */
export function AbschnittKopf({
  kicker,
  titel,
  meta,
}: {
  kicker: string;
  titel: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <header className={s.abschnittKopf}>
      <div className={s.abschnittTitel}>
        <span className={s.kicker}>{kicker}</span>
        <h2>{titel}</h2>
      </div>
      {meta && <div className={s.meta}>{meta}</div>}
    </header>
  );
}

/** „Seite 2 von 3“, nur wenn es mehrere Seiten gibt. */
export function SeitenMarke({ seite, seiten }: { seite: number; seiten: number }) {
  const { t } = useTranslation("anzeige");
  if (seiten <= 1) return null;
  return (
    <span className={`num ${s.seitenMarke}`}>
      {t("schirm.seite", { seite: seite + 1, seiten })}
    </span>
  );
}

/** Dezenter Live-Punkt für laufende Starts. */
export function LivePunkt() {
  const { t } = useTranslation("anzeige");
  return (
    <span
      className={s.puls}
      role="img"
      aria-label={t("schirm.laeuft")}
      title={t("schirm.laeuft")}
    />
  );
}

/** Name, wie der Server ihn liefert; ohne Namen steht nur die Startnummer da. */
export function useName(): (
  person: Pick<FeedPerson | FeedZeile, "display_name" | "start_number">,
) => string {
  const { t } = useTranslation("anzeige");
  return (person) =>
    person.display_name ?? t("schirm.nur_startnummer", { nummer: person.start_number });
}
