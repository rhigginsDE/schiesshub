import { ActionIcon, Button, Select, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Download, Merge, Pencil, Plus, Trash2, Users } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { klassenAbfrage, verbaendeAbfrage } from "../../../api/abfragen";
import type { Klasse } from "../../../api/typen";
import { Bestaetigung } from "../../../components/Bestaetigung";
import { ReihenfolgeKnoepfe, verschiebe } from "../../../components/Reihenfolge";
import { Leerzustand } from "../../../components/Zustand";
import {
  useKlasseAendern,
  useKlasseAnlegen,
  useKlasseLoeschen,
  useKlassenSortieren,
  useKlassenUebernehmen,
} from "../abfragen";
import { fehlerText } from "../fehlertext";
import { feldFehlerFuer } from "../senden";
import s from "../turnier.module.css";
import type { KlasseAnlage, TurnierKlasse, TurnierUebersicht } from "../typen";
import { BereichKopf } from "./Bausteine";

const FELDER = ["code", "name", "short", "merge_into_id"] as const;

export interface KlassenWerte {
  code: string;
  name: string;
  short: string;
  merge_into_id: string | null;
}

/** Kennung aus dem Kurznamen, wenn keine angegeben ist: „Sen 2“ → „sen-2“. */
export function kennungAus(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/ß/g, "ss")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function klasseAusWerten(werte: KlassenWerte): KlasseAnlage {
  const anlage: KlasseAnlage = {
    code: werte.code.trim() || kennungAus(werte.short || werte.name),
    name: werte.name.trim(),
    short: werte.short.trim(),
  };
  if (werte.merge_into_id) anlage.merge_into_id = werte.merge_into_id;
  return anlage;
}

function pruefe(werte: KlassenWerte, t: (s: string) => string): Record<string, string> {
  const fehler: Record<string, string> = {};
  if (!werte.name.trim()) fehler.name = t("pruefung.pflicht");
  if (!werte.short.trim()) fehler.short = t("pruefung.pflicht");
  if (werte.code.trim() && /\s/.test(werte.code.trim())) fehler.code = t("pruefung.kennung");
  return fehler;
}

export function Klassen({ turnier, gesperrt }: { turnier: TurnierUebersicht; gesperrt: boolean }) {
  const { t } = useTranslation("turnier");
  const verbaende = useQuery(verbaendeAbfrage());
  const [verband, setVerband] = useState<string | null>(null);
  const gewaehlt = verband ?? verbaende.data?.[0]?.id ?? null;
  const katalogKlassen = useQuery({
    ...klassenAbfrage(gewaehlt ?? ""),
    enabled: Boolean(gewaehlt),
  });
  const sortieren = useKlassenSortieren(turnier.id);
  const klassen = turnier.classes;
  const hilfe = new Map((katalogKlassen.data ?? []).map((klasse) => [klasse.id, klasse]));

  return (
    <div className={s.bereich}>
      <BereichKopf titel={t("bereich.klassen.titel")} text={t("bereich.klassen.text")} />
      <p className={`inset ${s.hinweisKasten}`}>{t("klassen.kein_geburtsdatum")}</p>

      {!gesperrt && (
        <KlassenImport
          turnierId={turnier.id}
          verbaende={(verbaende.data ?? []).map((v) => ({ value: v.id, label: v.kuerzel }))}
          verband={gewaehlt}
          onVerband={setVerband}
          anzahlKatalog={katalogKlassen.data?.length}
          vorhanden={klassen.length}
        />
      )}

      <section className="panel" aria-labelledby="klassen-liste">
        <div className="panel-kopf">
          <h3 className="h-section" id="klassen-liste">
            {t("klassen.im_turnier", { count: klassen.length })}
          </h3>
        </div>
        {klassen.length === 0 ? (
          <Leerzustand icon={Users} titel={t("klassen.leer_titel")} text={t("klassen.leer_text")} />
        ) : (
          <ul className={s.zeilenListe}>
            {klassen.map((klasse, index) => (
              <KlassenZeile
                key={klasse.id}
                turnier={turnier}
                klasse={klasse}
                index={index}
                katalog={hilfe.get(klasse.code)}
                gesperrt={gesperrt || sortieren.isPending}
                onVerschieben={(richtung) =>
                  sortieren.mutate(verschiebe(klassen, index, richtung).map((k) => k.id))
                }
              />
            ))}
          </ul>
        )}
        {sortieren.isError && (
          <p className={s.fehlerText} role="alert">
            {fehlerText(sortieren.error)}
          </p>
        )}
      </section>

      {!gesperrt && <KlasseNeu turnier={turnier} />}
    </div>
  );
}

interface KlassenImportProps {
  turnierId: string;
  verbaende: { value: string; label: string }[];
  verband: string | null;
  onVerband: (verband: string) => void;
  anzahlKatalog: number | undefined;
  vorhanden: number;
}

function KlassenImport({
  turnierId,
  verbaende,
  verband,
  onVerband,
  anzahlKatalog,
  vorhanden,
}: KlassenImportProps) {
  const { t } = useTranslation("turnier");
  const uebernehmen = useKlassenUebernehmen(turnierId);

  return (
    <section className={`panel ${s.formular}`} aria-labelledby="klassen-import">
      <h3 className="h-label" id="klassen-import">
        {t("klassen.import_titel")}
      </h3>
      <div className={s.zeileFormular}>
        <Select
          label={t("klassen.verband")}
          size="md"
          allowDeselect={false}
          data={verbaende}
          value={verband}
          onChange={(wert) => {
            if (wert) onVerband(wert);
            uebernehmen.reset();
          }}
        />
        <Button
          size="md"
          leftSection={<Download aria-hidden />}
          disabled={!verband}
          loading={uebernehmen.isPending}
          onClick={() => verband && uebernehmen.mutate(verband)}
        >
          {t("klassen.import_knopf")}
        </Button>
      </div>
      <p className={s.hilfe} aria-live="polite">
        {uebernehmen.isSuccess
          ? t("klassen.import_ergebnis", { count: uebernehmen.data.length })
          : anzahlKatalog !== undefined
            ? t(vorhanden > 0 ? "klassen.import_hilfe_vorhanden" : "klassen.import_hilfe", {
                count: anzahlKatalog,
              })
            : null}
      </p>
      {uebernehmen.isError && (
        <p className={s.fehlerText} role="alert">
          {fehlerText(uebernehmen.error)}
        </p>
      )}
    </section>
  );
}

function KlassenFelder({
  werte,
  setWerte,
  fehler,
  ziele,
  neu,
}: {
  werte: KlassenWerte;
  setWerte: (werte: KlassenWerte) => void;
  fehler: Record<string, string>;
  ziele: { value: string; label: string }[];
  neu?: boolean;
}) {
  const { t } = useTranslation("turnier");
  return (
    <div className={s.klassenFelder}>
      <TextInput
        label={t("klassen.name")}
        placeholder={neu ? t("klassen.name_platzhalter") : undefined}
        size="md"
        value={werte.name}
        error={fehler.name}
        onChange={(e) => setWerte({ ...werte, name: e.currentTarget.value })}
      />
      <TextInput
        label={t("klassen.kurz")}
        placeholder={neu ? t("klassen.kurz_platzhalter") : undefined}
        size="md"
        value={werte.short}
        error={fehler.short}
        onChange={(e) => setWerte({ ...werte, short: e.currentTarget.value })}
      />
      <TextInput
        label={t("klassen.kennung")}
        description={neu ? t("klassen.kennung_hilfe") : undefined}
        placeholder={neu ? kennungAus(werte.short || werte.name) : undefined}
        size="md"
        value={werte.code}
        error={fehler.code}
        classNames={{ input: "num" }}
        onChange={(e) => setWerte({ ...werte, code: e.currentTarget.value })}
      />
      <Select
        label={t("klassen.zusammenlegen")}
        size="md"
        clearable
        placeholder={t("klassen.nicht_zusammenlegen")}
        data={ziele}
        value={werte.merge_into_id}
        error={fehler.merge_into_id}
        onChange={(wert) => setWerte({ ...werte, merge_into_id: wert })}
      />
    </div>
  );
}

function KlasseNeu({ turnier }: { turnier: TurnierUebersicht }) {
  const { t } = useTranslation("turnier");
  const anlegen = useKlasseAnlegen(turnier.id);
  const leer: KlassenWerte = { code: "", name: "", short: "", merge_into_id: null };
  const [werte, setWerte] = useState<KlassenWerte>(leer);
  const [geprueft, setGeprueft] = useState(false);
  const fehler = {
    ...(anlegen.isError ? feldFehlerFuer(anlegen.error, FELDER) : {}),
    ...(geprueft ? pruefe(werte, t) : {}),
  };

  return (
    <form
      className={`panel ${s.formular}`}
      aria-labelledby="klasse-neu"
      noValidate
      onSubmit={(ereignis) => {
        ereignis.preventDefault();
        setGeprueft(true);
        if (Object.keys(pruefe(werte, t)).length > 0) return;
        anlegen.mutate(klasseAusWerten(werte), {
          onSuccess: () => {
            setWerte(leer);
            setGeprueft(false);
          },
        });
      }}
    >
      <h3 className="h-label" id="klasse-neu">
        {t("klassen.neu")}
      </h3>
      <KlassenFelder
        neu
        werte={werte}
        setWerte={(neu) => {
          setWerte(neu);
          if (anlegen.isError) anlegen.reset();
        }}
        fehler={fehler}
        ziele={turnier.classes.map((k) => ({ value: k.id, label: `${k.name} (${k.short})` }))}
      />
      {fehler[""] && (
        <p className={s.fehlerText} role="alert">
          {fehler[""]}
        </p>
      )}
      <div className={s.knopfReihe}>
        <Button
          type="submit"
          variant="default"
          size="md"
          leftSection={<Plus aria-hidden />}
          loading={anlegen.isPending}
        >
          {t("klassen.anlegen")}
        </Button>
      </div>
    </form>
  );
}

interface KlassenZeileProps {
  turnier: TurnierUebersicht;
  klasse: TurnierKlasse;
  index: number;
  katalog: Klasse | undefined;
  gesperrt: boolean;
  onVerschieben: (richtung: -1 | 1) => void;
}

function KlassenZeile({
  turnier,
  klasse,
  index,
  katalog,
  gesperrt,
  onVerschieben,
}: KlassenZeileProps) {
  const { t } = useTranslation("turnier");
  const aendern = useKlasseAendern(turnier.id);
  const loeschen = useKlasseLoeschen(turnier.id);
  const [bearbeiten, setBearbeiten] = useState(false);
  const [frage, setFrage] = useState(false);
  const ausKlasse = (): KlassenWerte => ({
    code: klasse.code,
    name: klasse.name,
    short: klasse.short,
    merge_into_id: klasse.merge_into_id,
  });
  const [werte, setWerte] = useState<KlassenWerte>(ausKlasse);
  const ziel = turnier.classes.find((k) => k.id === klasse.merge_into_id);
  const fehler = {
    ...(aendern.isError ? feldFehlerFuer(aendern.error, FELDER) : {}),
    ...pruefe(werte, t),
  };
  const betroffen = turnier.competitions.filter((w) => w.class_ids.includes(klasse.id)).length;

  if (bearbeiten) {
    return (
      <li className={s.zeileOffen}>
        <form
          className={s.formular}
          noValidate
          onSubmit={(ereignis) => {
            ereignis.preventDefault();
            if (Object.keys(pruefe(werte, t)).length > 0) return;
            aendern.mutate(
              {
                klasseId: klasse.id,
                daten: {
                  code: werte.code.trim() || klasse.code,
                  name: werte.name.trim(),
                  short: werte.short.trim(),
                  merge_into_id: werte.merge_into_id,
                },
              },
              { onSuccess: () => setBearbeiten(false) },
            );
          }}
        >
          <KlassenFelder
            werte={werte}
            setWerte={setWerte}
            fehler={fehler}
            ziele={turnier.classes
              .filter((k) => k.id !== klasse.id)
              .map((k) => ({ value: k.id, label: `${k.name} (${k.short})` }))}
          />
          {fehler[""] && (
            <p className={s.fehlerText} role="alert">
              {fehler[""]}
            </p>
          )}
          <div className={s.knopfReihe}>
            <Button variant="default" size="md" onClick={() => setBearbeiten(false)}>
              {t("aktion.abbrechen")}
            </Button>
            <Button type="submit" variant="default" size="md" loading={aendern.isPending}>
              {t("aktion.uebernehmen")}
            </Button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className={s.zeile}>
      <span className={`num ${s.kuerzel}`}>{klasse.short}</span>
      <span className={s.zeileText}>
        <strong>{klasse.name}</strong>
        <span className="gedaempft">
          <span className="num">{klasse.code}</span>
          {katalog?.alter_hilfe && ` · ${katalog.alter_hilfe}`}
        </span>
        {ziel && (
          <span className={s.zusammen}>
            <Merge aria-hidden />
            {t("klassen.zusammen_in", { name: ziel.name })}
          </span>
        )}
      </span>
      <span className={s.zeilenAktionen}>
        <ReihenfolgeKnoepfe
          index={index}
          anzahl={turnier.classes.length}
          hoch={t("aktion.nach_oben", { name: klasse.name })}
          runter={t("aktion.nach_unten", { name: klasse.name })}
          gesperrt={gesperrt}
          onVerschieben={onVerschieben}
        />
        <ActionIcon
          variant="subtle"
          color="gray"
          size={40}
          aria-label={t("aktion.bearbeiten", { name: klasse.name })}
          title={t("aktion.bearbeiten", { name: klasse.name })}
          disabled={gesperrt}
          onClick={() => {
            setWerte(ausKlasse());
            aendern.reset();
            setBearbeiten(true);
          }}
        >
          <Pencil aria-hidden />
        </ActionIcon>
        <ActionIcon
          variant="subtle"
          color="gray"
          size={40}
          aria-label={t("aktion.loeschen", { name: klasse.name })}
          title={t("aktion.loeschen", { name: klasse.name })}
          disabled={gesperrt}
          onClick={() => {
            loeschen.reset();
            setFrage(true);
          }}
        >
          <Trash2 aria-hidden />
        </ActionIcon>
      </span>
      <Bestaetigung
        offen={frage}
        titel={t("klassen.loeschen_titel", { name: klasse.name })}
        text={
          <p>
            {betroffen > 0
              ? t("klassen.loeschen_text_wettbewerbe", { count: betroffen })
              : t("klassen.loeschen_text")}
          </p>
        }
        bestaetigen={t("aktion.loeschen_knopf")}
        abbrechen={t("aktion.abbrechen")}
        ton="gefahr"
        laedt={loeschen.isPending}
        fehler={loeschen.isError ? fehlerText(loeschen.error) : undefined}
        onSchliessen={() => setFrage(false)}
        onBestaetigen={() => loeschen.mutate(klasse.id, { onSuccess: () => setFrage(false) })}
      />
    </li>
  );
}
