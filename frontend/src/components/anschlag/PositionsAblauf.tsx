import { ChevronRight } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { formatDauer, formatZahl } from "../../lib/format";
import { Piktogramm } from "./Piktogramm";
import s from "./PositionsAblauf.module.css";
import { anschlagText, positionAnschlagText } from "./text";
import type { Position } from "./typen";

export interface PositionsAblaufProps {
  positionen: Position[];
  /** Trefferaufnahme nach diesen Serien (1-basiert). */
  trefferaufnahmeNach?: number[] | null;
  /** Nur die ersten N Serien zählen; die übrigen erscheinen durchgestrichen. */
  serienGewertet?: number | null;
  schussJeSerie?: number | null;
  /** Feste Zeit je Serie; erscheint als Marke, wenn die Position keine Scheibe nennt. */
  zeitJeSerieS?: number | null;
  /** Hervorgehobene Position (Index in `positionen`), z. B. auf der Standanzeige. */
  aktivIndex?: number | null;
  /** Farbton: `a` für den ersten Abschnitt (Fertigkeit), `b` für den zweiten (Parcours). */
  ton?: "a" | "b";
  /** Hinweis über dem Ablauf, z. B. „abweichend vom Sporthandbuch“. */
  hinweis?: ReactNode;
  /** Zugänglicher Name der Liste, z. B. der Abschnittsname. */
  label: string;
}

/**
 * Ablauf der Positionen als Folge von Karten. Die Größe richtet sich nach dem Container,
 * daher passt dieselbe Komponente in die Detailansicht, auf den A4-Aushang und auf einen Fernseher.
 */
export function PositionsAblauf({
  positionen,
  trefferaufnahmeNach,
  serienGewertet,
  schussJeSerie,
  zeitJeSerieS,
  aktivIndex,
  ton = "a",
  hinweis,
  label,
}: PositionsAblaufProps) {
  const { t, i18n } = useTranslation("katalog");
  const sprache = i18n.language;
  const aufnahme = new Set(trefferaufnahmeNach ?? []);

  return (
    <div className={s.wurzel} data-ton={ton}>
      {hinweis && <p className={s.hinweis}>{hinweis}</p>}
      <ol
        className={s.ablauf}
        aria-label={label}
        style={{ "--spalten": positionen.length } as CSSProperties}
      >
        {positionen.map((position, index) => {
          const serie = index + 1;
          const gestrichen = serienGewertet != null && serie > serienGewertet;
          const letzte = index === positionen.length - 1;
          const nachAufnahme = aufnahme.has(serie);
          const aktiv = aktivIndex === index;
          const marke =
            position.scheibe != null
              ? t("anschlag.scheibe", { nr: formatZahl(position.scheibe, {}, sprache) })
              : zeitJeSerieS != null
                ? formatDauer(zeitJeSerieS, sprache)
                : null;
          return (
            <li
              key={position.nr}
              className={s.eintrag}
              data-gestrichen={gestrichen || undefined}
              data-aktiv={aktiv || undefined}
              aria-current={aktiv ? "step" : undefined}
            >
              <div className={s.karte}>
                <div className={s.kopf}>
                  <span>{t("anschlag.position", { nr: position.nr })}</span>
                  {schussJeSerie != null && (
                    <span className="num">{t("ablauf.schuss", { count: schussJeSerie })}</span>
                  )}
                </div>
                <p className={`num ${s.distanz}`}>
                  {position.distanz_m != null
                    ? t("allgemein:einheit.meter", {
                        wert: formatZahl(position.distanz_m, {}, sprache),
                      })
                    : "–"}
                </p>
                <div className={s.bilder} data-anzahl={position.anschlaege.length}>
                  {position.anschlaege.map((anschlag, nr) => (
                    <span key={`${anschlag.haltung}-${anschlag.hand ?? ""}`} className={s.bildPaar}>
                      {nr > 0 && <span className={s.oder}>{t("anschlag.oder")}</span>}
                      <span className={s.kachel}>
                        <Piktogramm
                          haltung={anschlag.haltung}
                          hand={anschlag.hand}
                          label={anschlagText(anschlag, t)}
                        />
                      </span>
                    </span>
                  ))}
                </div>
                <p className={s.anschlag}>{positionAnschlagText(position, t)}</p>
                {marke && <p className={`num ${s.marke}`}>{marke}</p>}
                {gestrichen && <p className={s.gestrichenText}>{t("anschlag.gestrichen")}</p>}
                {nachAufnahme && <p className={s.aufnahmeKlein}>{t("anschlag.trefferaufnahme")}</p>}
              </div>
              <div className={s.trenner} aria-hidden="true">
                {nachAufnahme ? (
                  <span className={s.aufnahme}>{t("anschlag.trefferaufnahme")}</span>
                ) : (
                  !letzte && <ChevronRight className={s.pfeil} />
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
