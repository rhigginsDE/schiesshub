import { ArrowRight, Delete } from "lucide-react";
import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { type Ablehnung, type Taste, wertText, type ZahlEingabe, zifferErlaubt } from "./eingabe";
import s from "./erfassung.module.css";
import type { FeldRef, Schusswert } from "./rohwerte";

interface TastenfeldProps {
  aktiv: FeldRef | null;
  /** Bezeichnung des aktiven Feldes, z. B. „Serie 2 · Schuss 7“ */
  titel: string | null;
  eingabe: ZahlEingabe;
  /** Gespeicherter Wert des aktiven Feldes (für die Anzeige) */
  wert: unknown;
  schussPuffer: string;
  gesperrt: boolean;
  /** Letzte Taste passte nicht: kurzer Hinweis, warum */
  hinweis: Ablehnung | null;
  onTaste: (taste: Taste) => void;
  onSchuss: (wert: Schusswert) => void;
}

/** Tasten nehmen keinen Fokus: Enter auf der Tastatur bleibt „weiter“. */
const ohneFokus = (ereignis: MouseEvent) => ereignis.preventDefault();

const ZIFFERN = ["1", "2", "3", "4", "5", "6", "7", "8", "9"] as const;

/** Großes Ziffernfeld passend zum aktiven Feld: erlaubte Ringwerte, Ziffern oder Zeit mit Komma. */
export function Tastenfeld({
  aktiv,
  titel,
  eingabe,
  wert,
  schussPuffer,
  gesperrt,
  hinweis,
  onTaste,
  onSchuss,
}: TastenfeldProps) {
  const { t } = useTranslation("erfassung");
  const feld = aktiv?.feld ?? null;
  const aus = gesperrt || feld === null;

  const anzeige =
    feld === null
      ? ""
      : feld.kind === "shots"
        ? schussPuffer || wertText(feld, wert)
        : eingabe.frisch
          ? wertText(feld, wert)
          : eingabe.text;

  return (
    <section className={`panel ${s.tastenPanel}`} aria-label={t("tasten.titel")}>
      <div className={s.tastenKopf}>
        <span className="h-label">{t("tasten.aktiv")}</span>
        <strong className={s.tastenTitel} aria-live="polite" data-leer={!titel || undefined}>
          {titel ?? t("tasten.kein_feld")}
        </strong>
        {feld && feld.kind !== "shots" && (
          <output className={`${s.tastenAnzeige} num`} aria-live="polite">
            {anzeige || " "}
            {feld.kind === "time" && <span className={s.einheit}>{t("einheit.sekunden")}</span>}
          </output>
        )}
      </div>

      {feld?.kind === "shots" ? (
        <div className={s.tasten}>
          {(feld.allowed_values ?? []).map((ring) => (
            <button
              key={String(ring)}
              type="button"
              onMouseDown={ohneFokus}
              className={`${s.taste} num`}
              data-x={ring === "X" || undefined}
              disabled={aus}
              onClick={() => onSchuss(ring)}
            >
              {String(ring)}
              {ring === "X" && <small>{t("tasten.innenzehner")}</small>}
              {ring === 0 && <small>{t("tasten.fehler")}</small>}
            </button>
          ))}
          <button
            type="button"
            onMouseDown={ohneFokus}
            className={`${s.taste} ${s.tasteBreit}`}
            disabled={aus}
            onClick={() => onTaste({ art: "loeschen" })}
          >
            <Delete aria-hidden />
            {t("tasten.korrektur")}
          </button>
        </div>
      ) : (
        <div className={s.tasten}>
          {ZIFFERN.map((ziffer) => (
            <button
              key={ziffer}
              type="button"
              onMouseDown={ohneFokus}
              className={`${s.taste} num`}
              disabled={aus || (feld !== null && !zifferErlaubt(feld, eingabe, ziffer))}
              onClick={() => onTaste({ art: "ziffer", ziffer })}
            >
              {ziffer}
            </button>
          ))}
          {feld?.kind === "time" ? (
            <button
              type="button"
              onMouseDown={ohneFokus}
              className={`${s.taste} num`}
              disabled={aus}
              onClick={() => onTaste({ art: "komma" })}
              aria-label={t("tasten.komma")}
            >
              ,
            </button>
          ) : (
            // Platz des Kommas bleibt frei: Rück steht immer rechts unten (Muskelgedächtnis).
            <span aria-hidden />
          )}
          <button
            type="button"
            onMouseDown={ohneFokus}
            className={`${s.taste} num`}
            disabled={aus || (feld !== null && !zifferErlaubt(feld, eingabe, "0"))}
            onClick={() => onTaste({ art: "ziffer", ziffer: "0" })}
          >
            0
          </button>
          <button
            type="button"
            onMouseDown={ohneFokus}
            className={`${s.taste} ${s.tasteNeben}`}
            disabled={aus}
            onClick={() => onTaste({ art: "loeschen" })}
            aria-label={t("tasten.korrektur")}
          >
            <Delete aria-hidden />
          </button>
          <button
            type="button"
            onMouseDown={ohneFokus}
            className={`${s.taste} ${s.tasteBreit}`}
            disabled={aus}
            onClick={() => onTaste({ art: "weiter" })}
          >
            {t("tasten.weiter")}
            <ArrowRight aria-hidden />
          </button>
        </div>
      )}
      {hinweis && feld && (
        <p className={s.tastenHinweis} role="status">
          {t(`tasten.abgelehnt.${hinweis}`, { max: feld.max ?? "" })}
        </p>
      )}
      <p className={s.klein}>
        {feld?.kind === "shots" && (feld.allowed_values ?? []).includes("X")
          ? t("tasten.tastatur_x")
          : t("tasten.tastatur")}
      </p>
    </section>
  );
}
