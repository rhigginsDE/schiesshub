import { Collapse, Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, History } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FehlerHinweis } from "../../components/FehlerHinweis";
import { formatDatum, formatUhrzeit } from "../../lib/format";
import { type Formular, type VerlaufEintrag, verlaufAbfrage } from "./api";
import { wertText } from "./eingabe";
import s from "./erfassung.module.css";
import { aenderungsOrt } from "./rohwerte";

interface VerlaufProps {
  turnierId: string;
  startId: string;
  form: Formular;
  /** Aufgeklappt beginnen (abgeschlossene Ergebnisse) */
  offen?: boolean;
}

function wertKurz(wert: unknown, feld: Parameters<typeof wertText>[0] | null): string {
  if (wert === null || wert === undefined) return "–";
  if (typeof wert === "object") return JSON.stringify(wert);
  if (feld?.kind === "choice")
    return feld.options?.find((o) => o.key === wert)?.label ?? String(wert);
  return feld ? wertText(feld, wert) : String(wert);
}

/** Verlauf eines Ergebnisses: wer, wann, was, Grund und geänderte Rohwerte. */
export function Verlauf({ turnierId, startId, form, offen: anfangsOffen = false }: VerlaufProps) {
  const { t } = useTranslation("erfassung");
  const [offen, setOffen] = useState(anfangsOffen);
  const verlauf = useQuery({ ...verlaufAbfrage(turnierId, startId), enabled: offen });
  const anzahl = verlauf.data?.length;

  return (
    <section className={s.verlauf} aria-labelledby="erf-verlauf">
      <button
        type="button"
        className={s.aufklappen}
        onClick={() => setOffen((o) => !o)}
        aria-expanded={offen}
        id="erf-verlauf"
      >
        <History aria-hidden />
        {anzahl !== undefined ? t("verlauf.titel_anzahl", { count: anzahl }) : t("verlauf.titel")}
        {offen ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />}
      </button>
      <Collapse expanded={offen}>
        {verlauf.isPending ? (
          <Skeleton height={80} radius="md" />
        ) : verlauf.isError ? (
          <FehlerHinweis fehler={verlauf.error} />
        ) : verlauf.data.length === 0 ? (
          <p className="gedaempft">{t("verlauf.leer")}</p>
        ) : (
          <ol className={s.verlaufListe}>
            {[...verlauf.data].reverse().map((eintrag) => (
              <VerlaufZeile key={eintrag.seq} eintrag={eintrag} form={form} />
            ))}
          </ol>
        )}
      </Collapse>
    </section>
  );
}

function VerlaufZeile({ eintrag, form }: { eintrag: VerlaufEintrag; form: Formular }) {
  const { t } = useTranslation("erfassung");
  const zeit = new Date(eintrag.created_at);
  const wer =
    [eintrag.user_name, eintrag.device_name].filter(Boolean).join(" · ") || t("verlauf.unbekannt");
  return (
    <li className={s.verlaufEintrag} data-art={eintrag.type}>
      <div className={s.verlaufKopf}>
        <strong>{eintrag.type_label}</strong>
        <span className="num gedaempft">
          {formatDatum(zeit)} {formatUhrzeit(zeit)}
        </span>
      </div>
      <p className="gedaempft">{wer}</p>
      {eintrag.abort_reason && <p>{t(`abbruch.lang.${eintrag.abort_reason}`)}</p>}
      {eintrag.reason && (
        <p className={s.verlaufGrund}>{t("verlauf.grund", { grund: eintrag.reason })}</p>
      )}
      {eintrag.changes.length > 0 && (
        <ul className={s.aenderungen}>
          {eintrag.changes.slice(0, 8).map((aenderung) => {
            const ort = aenderungsOrt(form, aenderung.path, (nr) => t("tasten.schuss", { nr }));
            return (
              <li key={aenderung.path}>
                <span className="gedaempft">{ort.text}</span>{" "}
                <span className="num">
                  {wertKurz(aenderung.before, ort.feld)} → {wertKurz(aenderung.after, ort.feld)}
                </span>
              </li>
            );
          })}
          {eintrag.changes.length > 8 && (
            <li className="gedaempft">
              {t("verlauf.weitere", { count: eintrag.changes.length - 8 })}
            </li>
          )}
        </ul>
      )}
    </li>
  );
}
