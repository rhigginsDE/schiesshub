import { Button, NumberInput, SegmentedControl, Select, Switch } from "@mantine/core";
import { useMutation } from "@tanstack/react-query";
import { Download, FileSpreadsheet, FileText, ShieldAlert } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { type AbfrageParameter, ApiFehler, apiDatei, serverMeldung } from "../api/client";
import { useDarf } from "../app/berechtigungen";
import type { TurnierUebersicht } from "../modules/turnier/typen";
import { Dialog } from "./Dialog";
import s from "./ExportKnoepfe.module.css";
import { useFehlerText } from "./FehlerHinweis";
import { zeigeMeldung } from "./Meldungen";

/** Welche Datei: Startliste, Siegerliste, Ergebnis-Rohexport. */
export type ExportArt = "startlist" | "winners" | "results";
export type ExportFormat = "pdf" | "csv";

const ALLE = "";

/** Pfad des Exports, wie ihn das Backend anbietet (`/tournaments/{id}/export/…`). */
export function exportPfad(turnierId: string, art: ExportArt, format: ExportFormat): string {
  return `/tournaments/${encodeURIComponent(turnierId)}/export/${art}.${format}`;
}

/** Enthält eine CSV-Datei nur die Kopfzeile (oder gar nichts)? */
export function csvIstLeer(text: string): boolean {
  const zeilen = text
    .replace(/^﻿/, "")
    .split(/\r?\n/)
    .filter((zeile) => zeile.trim() !== "");
  return zeilen.length <= 1;
}

/** Datei im Browser speichern (Download über einen temporären Link). */
function speichernUnter(inhalt: Blob, name: string) {
  const url = URL.createObjectURL(inhalt);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

interface ExportKnoepfeProps {
  turnierId: string;
  /** Wettbewerbe, Stände und Klassen für die Filter */
  uebersicht?: TurnierUebersicht;
  /** Filter der aufrufenden Ansicht, z. B. der Startliste */
  vorbelegung?: { wettbewerb?: string; stand?: string };
  /** `abschnitt`: eigenes Panel mit Überschrift; `knopf`: nur der Knopf (z. B. im Panel-Kopf) */
  darstellung?: "knopf" | "abschnitt";
  /** Eigene Beschriftung des Knopfs, z. B. „Siegerliste drucken“ */
  knopfText?: string;
  /** Nur diese Liste anbieten (z. B. die Siegerliste von der Startseite aus) */
  nur?: ExportArt;
}

/**
 * Startliste und Siegerliste als PDF und CSV sowie der Ergebnis-Rohexport. Braucht `export.read`;
 * volle Namen nur mit `export.full_names`. Ein Dialog sammelt die Filter.
 */
export function ExportKnoepfe({
  turnierId,
  uebersicht,
  vorbelegung,
  darstellung = "knopf",
  knopfText,
  nur,
}: ExportKnoepfeProps) {
  const { t } = useTranslation("anzeige");
  const darf = useDarf("export.read");
  const [offen, setOffen] = useState(false);
  if (!darf) return null;

  const knopf = (
    <Button variant="default" leftSection={<Download aria-hidden />} onClick={() => setOffen(true)}>
      {knopfText ?? t("export.knopf")}
    </Button>
  );
  const dialog = offen && (
    <ExportDialog
      turnierId={turnierId}
      uebersicht={uebersicht}
      vorbelegung={vorbelegung}
      nur={nur}
      onSchliessen={() => setOffen(false)}
    />
  );

  if (darstellung === "knopf") {
    return (
      <>
        {knopf}
        {dialog}
      </>
    );
  }
  return (
    <section className={`panel ${s.abschnitt}`} aria-labelledby="export-titel">
      <div className="panel-kopf">
        <h3 className="h-section" id="export-titel">
          {t("export.titel")}
        </h3>
        {knopf}
      </div>
      <p className={s.hilfe}>{t("export.einleitung")}</p>
      {dialog}
    </section>
  );
}

interface Auftrag {
  art: ExportArt;
  format: ExportFormat;
  parameter: AbfrageParameter;
}

function ExportDialog({
  turnierId,
  uebersicht,
  vorbelegung,
  nur,
  onSchliessen,
}: {
  turnierId: string;
  uebersicht?: TurnierUebersicht;
  vorbelegung?: { wettbewerb?: string; stand?: string };
  nur?: ExportArt;
  onSchliessen: () => void;
}) {
  const { t } = useTranslation("anzeige");
  const fehlerText = useFehlerText();
  const darfVoll = useDarf("export.full_names");
  const [namen, setNamen] = useState<"public" | "full">("public");
  const [wettbewerb, setWettbewerb] = useState(vorbelegung?.wettbewerb ?? ALLE);
  const [stand, setStand] = useState(vorbelegung?.stand ?? ALLE);
  const [sortierung, setSortierung] = useState("competition");
  const [klasse, setKlasse] = useState(ALLE);
  const [top, setTop] = useState<number | "">("");
  const [zusammen, setZusammen] = useState(false);
  const [vorlaeufig, setVorlaeufig] = useState(true);
  const [fehler, setFehler] = useState<{ art: ExportArt; text: string } | null>(null);

  const laden = useMutation({
    mutationFn: async ({ art, format, parameter }: Auftrag) => {
      const rueckfall = `${t(`export.datei.${art}`)}.${format}`;
      const datei = await apiDatei(exportPfad(turnierId, art, format), rueckfall, {
        parameter: { ...parameter, names: namen },
        still: true,
      });
      const leer = format === "csv" && csvIstLeer(await datei.inhalt.text());
      speichernUnter(datei.inhalt, datei.name);
      return { name: datei.name, leer };
    },
    onMutate: () => setFehler(null),
    onSuccess: ({ name, leer }) =>
      zeigeMeldung(
        leer
          ? { ton: "warn", titel: t("export.leer_titel"), text: t("export.leer_text", { name }) }
          : {
              ton: "erfolg",
              titel: t("export.gespeichert"),
              text: t("export.gespeichert_text", { name }),
            },
      ),
    onError: (grund, auftrag) => {
      let text = fehlerText(grund);
      if (grund instanceof ApiFehler) {
        if (grund.art === "verboten") text = serverMeldung(grund) ?? t("export.fehler_verboten");
        else if (grund.art === "nicht_gefunden") {
          text = serverMeldung(grund) ?? t("export.fehler_nicht_gefunden");
        }
      }
      setFehler({ art: auftrag.art, text });
    },
  });

  const wettbewerbe = [
    { value: ALLE, label: t("export.alle_wettbewerbe") },
    ...(uebersicht?.competitions ?? []).map((w) => ({
      value: w.id,
      label: [w.catalog_code, w.name].filter(Boolean).join(" · "),
    })),
  ];
  const staende = [
    { value: ALLE, label: t("export.alle_staende") },
    ...(uebersicht?.ranges ?? []).map((r) => ({ value: r.id, label: r.name })),
  ];
  const klassen = [
    { value: ALLE, label: t("export.alle_klassen") },
    ...(uebersicht?.classes ?? []).map((k) => ({ value: k.id, label: `${k.short} · ${k.name}` })),
  ];
  const wettbewerbWahl = (
    <Select
      label={t("export.wettbewerb")}
      data={wettbewerbe}
      value={wettbewerb}
      allowDeselect={false}
      onChange={(wert) => setWettbewerb(wert ?? ALLE)}
    />
  );

  const starten = (art: ExportArt, format: ExportFormat, parameter: AbfrageParameter) =>
    laden.mutate({ art, format, parameter: { competition_id: wettbewerb, ...parameter } });
  const laeuft = (art: ExportArt, format: ExportFormat) =>
    laden.isPending && laden.variables?.art === art && laden.variables.format === format;

  const dateiKnoepfe = (art: ExportArt, formate: ExportFormat[], parameter: AbfrageParameter) => (
    <div className={s.knoepfe}>
      {formate.map((format) => (
        <Button
          key={format}
          variant="default"
          leftSection={
            format === "pdf" ? <FileText aria-hidden /> : <FileSpreadsheet aria-hidden />
          }
          loading={laeuft(art, format)}
          disabled={laden.isPending && !laeuft(art, format)}
          onClick={() => starten(art, format, parameter)}
        >
          {t(`export.format.${format}`)}
        </Button>
      ))}
    </div>
  );

  const block = (art: ExportArt, inhalt: ReactNode) =>
    nur && nur !== art ? null : (
      <section className={`inset ${s.block}`} aria-labelledby={`export-${art}`}>
        <h4 className={s.blockTitel} id={`export-${art}`}>
          {t(`export.${art}.titel`)}
        </h4>
        <p className={s.hilfe}>{t(`export.${art}.text`)}</p>
        {inhalt}
        {fehler?.art === art && (
          <p className={s.fehler} role="alert">
            {fehler.text}
          </p>
        )}
      </section>
    );

  return (
    <Dialog opened onClose={onSchliessen} title={t("export.dialog_titel")} size="xl" centered>
      <div className={s.dialog}>
        {darfVoll && (
          <div className={s.namen}>
            <span className="h-label">{t("export.namen")}</span>
            <SegmentedControl
              value={namen}
              onChange={(wert) => setNamen(wert as "public" | "full")}
              data={[
                { value: "public", label: t("export.namen_oeffentlich") },
                { value: "full", label: t("export.namen_voll") },
              ]}
            />
            {namen === "full" && (
              <p className={s.datenschutz}>
                <ShieldAlert aria-hidden />
                {t("export.datenschutz")}
              </p>
            )}
          </div>
        )}
        <div className={s.felder}>{wettbewerbWahl}</div>
        {block(
          "startlist",
          <>
            <div className={s.felder}>
              <Select
                label={t("export.stand")}
                data={staende}
                value={stand}
                allowDeselect={false}
                onChange={(wert) => setStand(wert ?? ALLE)}
              />
              <Select
                label={t("export.sortierung")}
                data={[
                  { value: "competition", label: t("export.sortierung_wettbewerb") },
                  { value: "start_number", label: t("export.sortierung_startnummer") },
                  { value: "range", label: t("export.sortierung_stand") },
                ]}
                value={sortierung}
                allowDeselect={false}
                onChange={(wert) => setSortierung(wert ?? "competition")}
              />
            </div>
            {dateiKnoepfe("startlist", ["pdf", "csv"], { range_id: stand, sort: sortierung })}
          </>,
        )}
        {block(
          "winners",
          <>
            <div className={s.felder}>
              <Select
                label={t("export.klasse")}
                data={klassen}
                value={klasse}
                allowDeselect={false}
                onChange={(wert) => setKlasse(wert ?? ALLE)}
              />
              <NumberInput
                label={t("export.top")}
                description={t("export.top_hilfe")}
                min={1}
                allowDecimal={false}
                value={top}
                onChange={(wert) => setTop(typeof wert === "number" ? wert : "")}
              />
              <Switch
                label={t("export.zusammen")}
                description={t("export.zusammen_hilfe")}
                checked={zusammen}
                onChange={(e) => setZusammen(e.currentTarget.checked)}
              />
              <Switch
                label={t("export.vorlaeufig")}
                description={t("export.vorlaeufig_hilfe")}
                checked={vorlaeufig}
                onChange={(e) => setVorlaeufig(e.currentTarget.checked)}
              />
            </div>
            {dateiKnoepfe("winners", ["pdf", "csv"], {
              class_id: klasse,
              top: top === "" ? undefined : top,
              merged: zusammen,
              include_provisional: vorlaeufig,
            })}
          </>,
        )}
        {block("results", dateiKnoepfe("results", ["csv"], {}))}
      </div>
    </Dialog>
  );
}
