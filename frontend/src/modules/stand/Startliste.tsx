import { Select, Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ListX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Chip, type ChipTon } from "../../components/Chip";
import { ExportKnoepfe } from "../../components/ExportKnoepfe";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { formatUhrzeit } from "../../lib/format";
import { type StationStart, startlisteAbfrage } from "../anmeldung/api";
import type { TurnierUebersicht } from "../turnier/typen";
import { useAnzeigename } from "./aktionen";
import type { StandSuche } from "./pfade";
import s from "./stand.module.css";

interface StartlisteProps {
  uebersicht: TurnierUebersicht;
  suche: StandSuche;
  onSuche: (suche: StandSuche) => void;
}

const STATUS_TON: Record<StationStart["status"], ChipTon> = {
  registered: "neutral",
  called: "gruen",
  captured: "info",
  final: "info",
  aborted: "krit",
};

/** Startliste des Turniers, gefiltert nach Wettbewerb oder Stand. Namen wie vom Server geliefert. */
export function Startliste({ uebersicht, suche, onSuche }: StartlisteProps) {
  const { t, i18n } = useTranslation("stand");
  const anzeigename = useAnzeigename();
  const filter = { wettbewerb: suche.wettbewerb, stand: suche.stand };
  const abfrage = useQuery(startlisteAbfrage(uebersicht.id, filter));

  const platz = (start: StationStart): string => {
    if (start.heat_number != null && start.heat_starts_at) {
      const zeit = formatUhrzeit(new Date(start.heat_starts_at), i18n.language);
      return start.lane
        ? t("startliste.platz_durchgang", { nummer: start.heat_number, zeit, bahn: start.lane })
        : t("startliste.platz_durchgang_ohne_bahn", { nummer: start.heat_number, zeit });
    }
    if (start.status === "registered" && start.queue_position)
      return t("startliste.platz_reihenfolge", { nr: start.queue_position });
    if (start.lane) return t("startliste.platz_bahn", { bahn: start.lane });
    return t("startliste.platz_offen");
  };
  const status = (start: StationStart) =>
    start.status === "aborted" && start.abort_reason
      ? t(`abbruch.grund.${start.abort_reason}`)
      : t(`status.${start.status}`);

  const spalten = t("startliste.spalte", { returnObjects: true }) as Record<string, string>;

  return (
    <section className={`panel ${s.startliste}`} aria-labelledby="startliste-titel">
      <div className="panel-kopf">
        <h2 className="h-section" id="startliste-titel">
          {t("startliste.titel")}
        </h2>
        {abfrage.data && (
          <Chip>
            <span className="num">{t("startliste.anzahl", { count: abfrage.data.length })}</span>
          </Chip>
        )}
        <ExportKnoepfe turnierId={uebersicht.id} uebersicht={uebersicht} vorbelegung={filter} />
      </div>
      <div className={s.filter}>
        <Select
          size="md"
          label={t("startliste.wettbewerb")}
          value={suche.wettbewerb ?? ""}
          allowDeselect={false}
          onChange={(wert) => onSuche({ ...suche, wettbewerb: wert || undefined })}
          data={[
            { value: "", label: t("startliste.alle_wettbewerbe") },
            ...uebersicht.competitions.map((w) => ({
              value: w.id,
              label: [w.catalog_code, w.name].filter(Boolean).join(" · "),
            })),
          ]}
        />
        <Select
          size="md"
          label={t("startliste.stand")}
          value={suche.stand ?? ""}
          allowDeselect={false}
          onChange={(wert) => onSuche({ ...suche, stand: wert || undefined })}
          data={[
            { value: "", label: t("startliste.alle_staende") },
            ...uebersicht.ranges.map((r) => ({ value: r.id, label: r.name })),
          ]}
        />
      </div>

      {abfrage.isPending ? (
        <Skeleton height={200} radius="md" />
      ) : abfrage.isError ? (
        <Fehlerzustand fehler={abfrage.error} onErneut={() => void abfrage.refetch()} />
      ) : abfrage.data.length === 0 ? (
        <Leerzustand
          icon={ListX}
          titel={t("startliste.leer_titel")}
          text={t("startliste.leer_text")}
        />
      ) : (
        <table className={s.tabelle}>
          <thead>
            <tr>
              <th className={s.rechts}>{spalten.nr}</th>
              <th>{spalten.name}</th>
              <th>{spalten.klasse}</th>
              <th>{spalten.wettbewerb}</th>
              <th className={s.rechts}>{spalten.start}</th>
              <th>{spalten.platz}</th>
              <th>{spalten.status}</th>
            </tr>
          </thead>
          <tbody>
            {abfrage.data.map((start) => (
              <tr key={start.start_id}>
                <td className={`num ${s.rechts} ${s.zelleNr}`} data-label={spalten.nr}>
                  {start.start_number}
                </td>
                <td className={s.zelleName} data-label={spalten.name}>
                  <span className={s.nameInhalt}>
                    <strong data-ohne-name={start.display_name === null || undefined}>
                      {anzeigename(start)}
                    </strong>
                    {start.club && <span className="gedaempft">{start.club}</span>}
                  </span>
                </td>
                <td data-label={spalten.klasse}>{start.class_short}</td>
                <td data-label={spalten.wettbewerb}>{start.competition_name}</td>
                <td className={`num ${s.rechts}`} data-label={spalten.start}>
                  {start.attempt}
                </td>
                <td data-label={spalten.platz}>{platz(start)}</td>
                <td data-label={spalten.status}>
                  <Chip ton={STATUS_TON[start.status]}>{status(start)}</Chip>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
