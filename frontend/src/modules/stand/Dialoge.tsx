import { Button, NumberInput, Select, TextInput } from "@mantine/core";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "../../components/Dialog";
import { FehlerHinweis } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { formatUhrzeit } from "../../lib/format";
import {
  type Durchgang,
  type StationStart,
  useDurchgangAendern,
  usePlatzZuweisen,
  useSerieAnlegen,
} from "../anmeldung/api";
import { feldFehlerFuer } from "../turnier/senden";
import type { Turnier, Wettbewerb } from "../turnier/typen";
import {
  freieBahnenDurchgang,
  lokalesDatum,
  lokaleUhrzeit,
  sortiereDurchgaenge,
  vorschlagDatum,
  zeitpunktAusEingabe,
} from "./logik";
import s from "./stand.module.css";

function Knoepfe({
  abbrechen,
  speichern,
  laedt,
  onAbbrechen,
}: {
  abbrechen: string;
  speichern: string;
  laedt: boolean;
  onAbbrechen: () => void;
}) {
  return (
    <div className={s.dialogKnoepfe}>
      <Button variant="default" size="md" onClick={onAbbrechen} disabled={laedt}>
        {abbrechen}
      </Button>
      <Button type="submit" size="md" loading={laedt}>
        {speichern}
      </Button>
    </div>
  );
}

// --- Serie ---------------------------------------------------------------------------------------

interface SerieDialogProps {
  offen: boolean;
  turnier: Turnier;
  standId: string;
  wettbewerbe: readonly Wettbewerb[];
  /** Vorschlag für den Beginn: Ende des letzten Durchgangs */
  ab?: string | null;
  onSchliessen: () => void;
}

/** Durchgänge als Serie anlegen: ab Datum und Uhrzeit, Anzahl, Dauer aus dem Wettbewerb. */
export function SerieDialog(props: SerieDialogProps) {
  const { t } = useTranslation("stand");
  return (
    <Dialog
      opened={props.offen}
      onClose={props.onSchliessen}
      title={t("serie.titel")}
      centered
      size="md"
      closeButtonProps={{ "aria-label": t("dialog_schliessen") }}
    >
      {props.offen && <SerieFormular {...props} />}
    </Dialog>
  );
}

function SerieFormular({ turnier, standId, wettbewerbe, ab, onSchliessen }: SerieDialogProps) {
  const { t, i18n } = useTranslation("stand");
  const anlegen = useSerieAnlegen(turnier.id, standId);
  const [wettbewerbId, setWettbewerbId] = useState(wettbewerbe[0]?.id ?? null);
  const [datum, setDatum] = useState(
    ab ? lokalesDatum(ab) : vorschlagDatum(turnier.date_from, turnier.date_to),
  );
  const [uhrzeit, setUhrzeit] = useState(ab ? lokaleUhrzeit(ab) : "09:00");
  const [anzahl, setAnzahl] = useState<number | "">(8);
  const [geprueft, setGeprueft] = useState(false);

  const wettbewerb = wettbewerbe.find((w) => w.id === wettbewerbId);
  const minuten = wettbewerb?.heat_minutes ?? null;
  const beginn = zeitpunktAusEingabe(datum, uhrzeit);
  const server = anlegen.isError
    ? feldFehlerFuer(anlegen.error, ["competition_id", "starts_at", "count"])
    : {};
  const zeitFehler = geprueft && !beginn ? t("serie.zeit_fehlt") : server.starts_at;

  let vorschau: string | null = null;
  if (beginn && minuten && typeof anzahl === "number" && anzahl >= 1) {
    const von = new Date(beginn);
    const bis = new Date(von.getTime() + anzahl * minuten * 60_000);
    vorschau = t("serie.vorschau", {
      anzahl,
      von: formatUhrzeit(von, i18n.language),
      bis: formatUhrzeit(bis, i18n.language),
    });
  }

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    setGeprueft(true);
    if (!beginn || !wettbewerbId || anzahl === "") return;
    anlegen.mutate(
      { competition_id: wettbewerbId, starts_at: beginn, count: anzahl },
      {
        onSuccess: (neu) => {
          zeigeMeldung({ ton: "erfolg", titel: t("serie.angelegt", { count: neu.length }) });
          onSchliessen();
        },
      },
    );
  };

  return (
    <form className={s.dialog} onSubmit={absenden} noValidate>
      <Select
        size="md"
        label={t("serie.wettbewerb")}
        description={minuten ? t("serie.wettbewerb_hilfe", { minuten }) : undefined}
        allowDeselect={false}
        value={wettbewerbId}
        onChange={setWettbewerbId}
        data={wettbewerbe.map((w) => ({
          value: w.id,
          label: [w.catalog_code, w.name].filter(Boolean).join(" · "),
        }))}
        error={server.competition_id}
        data-autofocus
      />
      <div className={s.dialogZeile}>
        <TextInput
          size="md"
          type="date"
          label={t("serie.datum")}
          value={datum}
          onChange={(e) => setDatum(e.currentTarget.value)}
          error={zeitFehler}
          classNames={{ input: "num" }}
        />
        <TextInput
          size="md"
          type="time"
          label={t("serie.uhrzeit")}
          value={uhrzeit}
          onChange={(e) => setUhrzeit(e.currentTarget.value)}
          error={zeitFehler ? " " : undefined}
          classNames={{ input: "num" }}
        />
        <NumberInput
          size="md"
          label={t("serie.anzahl")}
          min={1}
          max={200}
          allowDecimal={false}
          value={anzahl}
          onChange={(wert) => setAnzahl(typeof wert === "number" ? wert : "")}
          error={geprueft && anzahl === "" ? t("serie.anzahl_fehlt") : server.count}
          classNames={{ input: "num" }}
        />
      </div>
      {vorschau && <p className="gedaempft num">{vorschau}</p>}
      <FehlerHinweis fehler={server[""] ? anlegen.error : null} text={server[""]} />
      <Knoepfe
        abbrechen={t("serie.abbrechen")}
        speichern={t("serie.anlegen")}
        laedt={anlegen.isPending}
        onAbbrechen={onSchliessen}
      />
    </form>
  );
}

// --- Durchgang ändern ----------------------------------------------------------------------------

interface DurchgangDialogProps {
  turnierId: string;
  standId: string;
  durchgang: Durchgang | null;
  onSchliessen: () => void;
}

export function DurchgangDialog(props: DurchgangDialogProps) {
  const { t } = useTranslation("stand");
  const { durchgang } = props;
  return (
    <Dialog
      opened={durchgang !== null}
      onClose={props.onSchliessen}
      title={durchgang ? t("durchgang_form.titel", { nummer: durchgang.number }) : ""}
      centered
      size="md"
      closeButtonProps={{ "aria-label": t("dialog_schliessen") }}
    >
      {durchgang && <DurchgangFormular key={durchgang.id} {...props} durchgang={durchgang} />}
    </Dialog>
  );
}

function DurchgangFormular({
  turnierId,
  standId,
  durchgang,
  onSchliessen,
}: DurchgangDialogProps & { durchgang: Durchgang }) {
  const { t } = useTranslation("stand");
  const aendern = useDurchgangAendern(turnierId, standId);
  const [nummer, setNummer] = useState<number | "">(durchgang.number);
  const [datum, setDatum] = useState(lokalesDatum(durchgang.starts_at));
  const [von, setVon] = useState(lokaleUhrzeit(durchgang.starts_at));
  const [bis, setBis] = useState(lokaleUhrzeit(durchgang.ends_at));
  const [geprueft, setGeprueft] = useState(false);

  const beginn = zeitpunktAusEingabe(datum, von);
  const ende = zeitpunktAusEingabe(datum, bis);
  const server = aendern.isError
    ? feldFehlerFuer(aendern.error, ["number", "starts_at", "ends_at"])
    : {};

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    setGeprueft(true);
    if (!beginn || !ende || nummer === "") return;
    const daten: { number?: number; starts_at?: string; ends_at?: string } = {};
    if (nummer !== durchgang.number) daten.number = nummer;
    if (beginn !== new Date(durchgang.starts_at).toISOString()) daten.starts_at = beginn;
    if (ende !== new Date(durchgang.ends_at).toISOString()) daten.ends_at = ende;
    if (Object.keys(daten).length === 0) {
      onSchliessen();
      return;
    }
    aendern.mutate(
      { durchgangId: durchgang.id, daten },
      {
        onSuccess: (neu) => {
          zeigeMeldung({
            ton: "erfolg",
            titel: t("durchgang_form.gespeichert", { nummer: neu.number }),
          });
          onSchliessen();
        },
      },
    );
  };

  return (
    <form className={s.dialog} onSubmit={absenden} noValidate>
      <div className={s.dialogZeile}>
        <NumberInput
          size="md"
          label={t("durchgang_form.nummer")}
          min={1}
          allowDecimal={false}
          value={nummer}
          onChange={(wert) => setNummer(typeof wert === "number" ? wert : "")}
          error={geprueft && nummer === "" ? t("durchgang_form.nummer_fehlt") : server.number}
          classNames={{ input: "num" }}
          data-autofocus
        />
        <TextInput
          size="md"
          type="date"
          label={t("durchgang_form.datum")}
          value={datum}
          onChange={(e) => setDatum(e.currentTarget.value)}
          classNames={{ input: "num" }}
        />
      </div>
      <div className={s.dialogZeile}>
        <TextInput
          size="md"
          type="time"
          label={t("durchgang_form.von")}
          value={von}
          onChange={(e) => setVon(e.currentTarget.value)}
          error={geprueft && !beginn ? t("durchgang_form.zeit_fehlt") : server.starts_at}
          classNames={{ input: "num" }}
        />
        <TextInput
          size="md"
          type="time"
          label={t("durchgang_form.bis")}
          value={bis}
          onChange={(e) => setBis(e.currentTarget.value)}
          error={geprueft && !ende ? t("durchgang_form.zeit_fehlt") : server.ends_at}
          classNames={{ input: "num" }}
        />
      </div>
      <FehlerHinweis fehler={server[""] ? aendern.error : null} text={server[""]} />
      <Knoepfe
        abbrechen={t("durchgang_form.abbrechen")}
        speichern={t("durchgang_form.speichern")}
        laedt={aendern.isPending}
        onAbbrechen={onSchliessen}
      />
    </form>
  );
}

// --- Platz wählen (umsetzen, einplanen) ----------------------------------------------------------

interface PlatzDialogProps {
  turnierId: string;
  start: StationStart | null;
  durchgaenge: readonly Durchgang[];
  /** Alle Starts des Stands (für die Belegung) */
  starts: readonly StationStart[];
  onSchliessen: () => void;
}

export function PlatzDialog(props: PlatzDialogProps) {
  const { t } = useTranslation("stand");
  const { start } = props;
  const titel = start
    ? t(start.heat_id ? "platz.titel_umsetzen" : "platz.titel_einplanen", {
        nr: start.start_number,
      })
    : "";
  return (
    <Dialog
      opened={start !== null}
      onClose={props.onSchliessen}
      title={titel}
      centered
      size="md"
      closeButtonProps={{ "aria-label": t("dialog_schliessen") }}
    >
      {start && <PlatzFormular key={start.start_id} {...props} start={start} />}
    </Dialog>
  );
}

function PlatzFormular({
  turnierId,
  start,
  durchgaenge,
  starts,
  onSchliessen,
}: PlatzDialogProps & { start: StationStart }) {
  const { t, i18n } = useTranslation("stand");
  const zuweisen = usePlatzZuweisen(turnierId);
  const auswahl = sortiereDurchgaenge(durchgaenge)
    .map((durchgang) => ({
      durchgang,
      frei: freieBahnenDurchgang(durchgang, starts, start.start_id),
    }))
    .filter(({ frei, durchgang }) => frei.length > 0 || durchgang.id === start.heat_id);
  const [durchgangId, setDurchgangId] = useState<string | null>(
    start.heat_id ?? auswahl[0]?.durchgang.id ?? null,
  );
  const gewaehlt = auswahl.find(({ durchgang }) => durchgang.id === durchgangId);
  const [bahn, setBahn] = useState<string>(start.heat_id && start.lane ? String(start.lane) : "");
  const server = zuweisen.isError ? feldFehlerFuer(zuweisen.error, ["heat_id", "lane"]) : {};

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    if (!durchgangId) return;
    zuweisen.mutate(
      { startId: start.start_id, durchgangId, bahn: bahn ? Number(bahn) : undefined },
      {
        onSuccess: (neu) => {
          const nummer = durchgaenge.find((d) => d.id === neu.heat_id)?.number ?? "";
          zeigeMeldung({
            ton: "erfolg",
            titel: t("platz.gespeichert", { nr: start.start_number, nummer, bahn: neu.lane ?? "" }),
          });
          onSchliessen();
        },
      },
    );
  };

  if (auswahl.length === 0) {
    return <p className="gedaempft">{t("platz.kein_durchgang")}</p>;
  }

  return (
    <form className={s.dialog} onSubmit={absenden} noValidate>
      <Select
        size="md"
        label={t("platz.durchgang")}
        allowDeselect={false}
        value={durchgangId}
        onChange={(wert) => {
          setDurchgangId(wert);
          setBahn("");
        }}
        data={auswahl.map(({ durchgang, frei }) => ({
          value: durchgang.id,
          label: t("platz.durchgang_option", {
            nummer: durchgang.number,
            zeit: formatUhrzeit(new Date(durchgang.starts_at), i18n.language),
            frei: frei.length,
          }),
        }))}
        error={server.heat_id}
        data-autofocus
      />
      <Select
        size="md"
        label={t("platz.bahn")}
        allowDeselect={false}
        value={bahn}
        onChange={(wert) => setBahn(wert ?? "")}
        data={[
          { value: "", label: t("platz.bahn_erste") },
          ...(gewaehlt?.frei ?? []).map((nr) => ({
            value: String(nr),
            label: t("platz.bahn_option", { bahn: nr }),
          })),
        ]}
        error={server.lane}
      />
      <FehlerHinweis fehler={server[""] ? zuweisen.error : null} text={server[""]} />
      <Knoepfe
        abbrechen={t("platz.abbrechen")}
        speichern={t("platz.speichern")}
        laedt={zuweisen.isPending}
        onAbbrechen={onSchliessen}
      />
    </form>
  );
}
