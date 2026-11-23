import { ArrowRight, Check, Delete, X } from "lucide-react";
import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { feldBereich } from "./anzeige";
import {
  type Ablehnung,
  istJeZiel,
  istKommaFeld,
  kommaBereich,
  type Taste,
  wertText,
  type ZahlEingabe,
  zifferErlaubt,
} from "./eingabe";
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

/** Treffer je Ziel mit genau „1“ und „0“: zwei große Tasten „Treffer“ und „Fehler“. */
function trefferFehler(erlaubt: readonly Schusswert[]): boolean {
  return erlaubt.length === 2 && erlaubt.includes(1) && erlaubt.includes(0);
}

/**
 * Großes Ziffernfeld passend zum aktiven Feld: erlaubte Ringwerte, Treffer/Fehler je Ziel, Ziffern
 * oder Zahl mit Komma (Zeit, Zehntelwertung).
 */
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
  const komma = feld !== null && istKommaFeld(feld);
  // Schüsse mit festen Werten als eigene Tasten; Zehntel wie eine Zahl mit Komma.
  const wertTasten = feld?.kind === "shots" && !komma;
  const erlaubt = feld?.allowed_values ?? [];
  const jeZiel = feld !== null && istJeZiel(feld) && trefferFehler(erlaubt);

  const anzeige =
    feld === null
      ? ""
      : wertTasten
        ? schussPuffer || wertText(feld, wert)
        : eingabe.frisch
          ? wertText(feld, wert)
          : eingabe.text;

  const hinweisText = (() => {
    if (!hinweis || !feld) return null;
    if (komma) {
      const bereich = kommaBereich(feld);
      if (hinweis === "zu_gross") return t("tasten.abgelehnt.zu_gross", { max: bereich.max ?? "" });
      if (hinweis === "zu_klein")
        return t("tasten.abgelehnt.zu_klein", { bereich: feldBereich(feld, t) ?? "" });
    }
    return t(`tasten.abgelehnt.${hinweis}`, {
      max: feld.max ?? "",
      bereich: feldBereich(feld, t) ?? "",
    });
  })();

  const tastaturHilfe = jeZiel
    ? t("tasten.tastatur_ziel")
    : komma
      ? t("tasten.tastatur_komma")
      : wertTasten && erlaubt.includes("X")
        ? t("tasten.tastatur_x")
        : t("tasten.tastatur");

  return (
    <section className={`panel ${s.tastenPanel}`} aria-label={t("tasten.titel")}>
      <div className={s.tastenKopf}>
        <span className="h-label">{t("tasten.aktiv")}</span>
        <strong className={s.tastenTitel} aria-live="polite" data-leer={!titel || undefined}>
          {titel ?? t("tasten.kein_feld")}
        </strong>
        {feld && !wertTasten && (
          <output className={`${s.tastenAnzeige} num`} aria-live="polite">
            {anzeige || " "}
            {feld.kind === "time" && <span className={s.einheit}>{t("einheit.sekunden")}</span>}
          </output>
        )}
      </div>

      {jeZiel ? (
        <div className={`${s.tasten} ${s.tastenZiel}`}>
          <button
            type="button"
            onMouseDown={ohneFokus}
            className={`${s.taste} ${s.tasteZiel}`}
            data-art="treffer"
            disabled={aus}
            onClick={() => onSchuss(1)}
          >
            <Check aria-hidden />
            {t("ziel.treffer")}
            <small className="num">1</small>
          </button>
          <button
            type="button"
            onMouseDown={ohneFokus}
            className={`${s.taste} ${s.tasteZiel}`}
            data-art="fehler"
            disabled={aus}
            onClick={() => onSchuss(0)}
          >
            <X aria-hidden />
            {t("ziel.fehler")}
            <small className="num">0</small>
          </button>
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
      ) : wertTasten ? (
        <div className={s.tasten}>
          {erlaubt.map((ring) => (
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
          {feld?.kind === "time" || komma ? (
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
      {hinweisText && (
        <p className={s.tastenHinweis} role="status">
          {hinweisText}
        </p>
      )}
      {komma && feld && feldBereich(feld, t) && (
        <p className={s.klein}>{t("tasten.erlaubt", { bereich: feldBereich(feld, t) })}</p>
      )}
      <p className={s.klein}>{tastaturHilfe}</p>
    </section>
  );
}
