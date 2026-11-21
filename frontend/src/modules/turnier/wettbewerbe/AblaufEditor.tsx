import { NumberInput, Switch, TextInput } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Abschnitt, Variante } from "../../../api/typen";
import { formatZahl } from "../../../lib/format";
import s from "../turnier.module.css";
import {
  type AbschnittFeld,
  abschnittPfad,
  type FeldBeschreibung,
  schalteTrefferaufnahme,
  setzeSerien,
  sichtbareFelder,
} from "../wettbewerbFormular";

interface AblaufEditorProps {
  abschnitte: Abschnitt[];
  /** Stand auf dem Server; bestimmt mit dem Katalog, welche Felder erscheinen */
  original: readonly Abschnitt[];
  /** Katalogvariante zum Vergleich; fehlt bei eigenen Wettbewerben */
  katalog: Variante | undefined;
  fehler: Record<string, string>;
  gesperrt: boolean;
  onAendern: (abschnitte: Abschnitt[]) => void;
}

function gleich(a: unknown, b: unknown): boolean {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

const GRUPPEN = ["schuss", "zeit", "zuschlag"] as const;

/** Der Ablauf als Formular: je Abschnitt nur die Felder, die er hat. */
export function AblaufEditor({
  abschnitte,
  original,
  katalog,
  fehler,
  gesperrt,
  onAendern,
}: AblaufEditorProps) {
  const setzeAbschnitt = (index: number, neu: Abschnitt) =>
    onAendern(abschnitte.map((eintrag, i) => (i === index ? neu : eintrag)));

  return (
    <div className={s.abschnitte}>
      {abschnitte.map((abschnitt, index) => (
        <AbschnittFormular
          key={abschnitt.id}
          abschnitt={abschnitt}
          index={index}
          mitName={abschnitte.length > 1}
          original={original.find((eintrag) => eintrag.id === abschnitt.id)}
          katalog={katalog?.abschnitte.find((eintrag) => eintrag.id === abschnitt.id)}
          fehler={fehler}
          gesperrt={gesperrt}
          onAendern={(neu) => setzeAbschnitt(index, neu)}
        />
      ))}
    </div>
  );
}

interface AbschnittFormularProps {
  abschnitt: Abschnitt;
  index: number;
  mitName: boolean;
  original: Abschnitt | undefined;
  katalog: Abschnitt | undefined;
  fehler: Record<string, string>;
  gesperrt: boolean;
  onAendern: (abschnitt: Abschnitt) => void;
}

function AbschnittFormular({
  abschnitt,
  index,
  mitName,
  original,
  katalog,
  fehler,
  gesperrt,
  onAendern,
}: AbschnittFormularProps) {
  const { t, i18n } = useTranslation("turnier");
  const felder = sichtbareFelder(abschnitt, original, katalog);
  const pfad = (feld: string) => abschnittPfad(index, feld);
  const katalogText = (feld: AbschnittFeld) => {
    if (!katalog) return undefined;
    const wert = katalog[feld];
    if (gleich(wert, abschnitt[feld])) return undefined;
    return t("ablauf.katalog_wert", {
      wert: wertText(wert, feld, (k, o) => t(k, o ?? {}), i18n.language),
    });
  };
  const allgemein = fehler[pfad("")] ?? fehler[abschnittPfad(index)];

  return (
    <fieldset className={`inset ${s.abschnitt}`} disabled={gesperrt}>
      <legend className={mitName ? s.abschnittName : "nur-screenreader"}>
        {mitName ? abschnitt.name : t("ablauf.titel")}
      </legend>
      {allgemein && (
        <p className={s.fehlerText} role="alert">
          {allgemein}
        </p>
      )}

      <div className={s.feldRaster}>
        <ZahlFeld
          label={t("ablauf.feld.serien")}
          wert={abschnitt.serien}
          ganz
          min={1}
          geaendertText={katalogText("serien")}
          fehler={fehler[pfad("serien")]}
          onWert={(wert) => wert !== null && onAendern(setzeSerien(abschnitt, wert))}
        />
        <ZahlFeld
          label={t("ablauf.feld.serien_gewertet")}
          beschreibung={t("ablauf.feld.serien_gewertet_hilfe")}
          platzhalter={t("ablauf.alle")}
          wert={abschnitt.serien_gewertet ?? null}
          ganz
          min={1}
          max={abschnitt.serien}
          geaendertText={katalogText("serien_gewertet")}
          fehler={fehler[pfad("serien_gewertet")]}
          onWert={(wert) => onAendern({ ...abschnitt, serien_gewertet: wert })}
        />
      </div>

      <Trefferaufnahme
        abschnitt={abschnitt}
        geaendertText={katalogText("trefferaufnahme_nach")}
        fehler={fehler[pfad("trefferaufnahme_nach")]}
        onAendern={onAendern}
      />

      {GRUPPEN.map((gruppe) => {
        const inGruppe = felder.filter((feld) => feld.gruppe === gruppe);
        if (inGruppe.length === 0) return null;
        return (
          <div key={gruppe} className={s.feldGruppe}>
            <span className="h-label">{t(`ablauf.gruppe.${gruppe}`)}</span>
            <div className={s.feldRaster}>
              {inGruppe.map((beschreibung) => (
                <Feld
                  key={beschreibung.feld}
                  beschreibung={beschreibung}
                  abschnitt={abschnitt}
                  geaendertText={katalogText(beschreibung.feld)}
                  fehler={fehler[pfad(beschreibung.feld)]}
                  onAendern={onAendern}
                />
              ))}
            </div>
          </div>
        );
      })}

      {abschnitt.positionen && abschnitt.positionen.length > 0 && (
        <p className={s.hilfe}>{t("ablauf.positionen", { count: abschnitt.positionen.length })}</p>
      )}
    </fieldset>
  );
}

/** Wert für „Katalog: …“: Zahl mit Einheit, Liste, Ja/Nein oder „nicht gesetzt“. */
function wertText(
  wert: unknown,
  feld: AbschnittFeld,
  t: (schluessel: string, werte?: Record<string, unknown>) => string,
  sprache: string,
): string {
  if (wert === null || wert === undefined) return t("ablauf.nicht_gesetzt");
  if (typeof wert === "boolean") return wert ? t("ablauf.ja") : t("ablauf.nein");
  const einheit = feld.endsWith("_s") ? " s" : feld.endsWith("_m") ? " m" : "";
  if (Array.isArray(wert)) {
    return `${wert.map((zahl) => formatZahl(Number(zahl), {}, sprache)).join(" / ")}${einheit}`;
  }
  if (typeof wert === "number") return `${formatZahl(wert, {}, sprache)}${einheit}`;
  return String(wert);
}

interface ZahlFeldProps {
  label: string;
  beschreibung?: string;
  platzhalter?: string;
  wert: number | null;
  ganz?: boolean;
  min?: number;
  max?: number;
  einheit?: string;
  geaendertText?: string;
  fehler?: string;
  onWert: (wert: number | null) => void;
}

function ZahlFeld({
  label,
  beschreibung,
  platzhalter,
  wert,
  ganz,
  min = 0,
  max,
  einheit,
  geaendertText,
  fehler,
  onWert,
}: ZahlFeldProps) {
  return (
    <NumberInput
      label={label}
      description={geaendertText ?? beschreibung}
      placeholder={platzhalter}
      size="md"
      min={min}
      max={max}
      allowDecimal={!ganz}
      allowNegative={false}
      decimalSeparator=","
      suffix={einheit ? ` ${einheit}` : undefined}
      value={wert ?? ""}
      error={fehler}
      data-geaendert={geaendertText ? "" : undefined}
      classNames={{ input: "num" }}
      className={geaendertText ? s.geaendert : undefined}
      onChange={(eingabe) => onWert(typeof eingabe === "number" ? eingabe : null)}
    />
  );
}

function Feld({
  beschreibung,
  abschnitt,
  geaendertText,
  fehler,
  onAendern,
}: {
  beschreibung: FeldBeschreibung;
  abschnitt: Abschnitt;
  geaendertText?: string;
  fehler?: string;
  onAendern: (abschnitt: Abschnitt) => void;
}) {
  const { t } = useTranslation("turnier");
  const { feld, art } = beschreibung;
  const label = t(`ablauf.feld.${feld}`);
  const setze = (wert: unknown) => onAendern({ ...abschnitt, [feld]: wert } as Abschnitt);

  if (art === "schalter") {
    return (
      <div className={geaendertText ? `${s.schalterFeld} ${s.geaendert}` : s.schalterFeld}>
        <Switch
          size="md"
          label={label}
          description={geaendertText}
          checked={abschnitt[feld] === true}
          onChange={(e) => setze(e.currentTarget.checked)}
        />
      </div>
    );
  }

  if (art === "liste_ganz") {
    return (
      <RingwerteFeld
        label={label}
        werte={(abschnitt[feld] as number[] | null | undefined) ?? []}
        geaendertText={geaendertText}
        fehler={fehler}
        onWerte={(werte) => setze(werte.length > 0 ? werte : null)}
      />
    );
  }

  if (art === "liste_sekunden" || art === "liste_meter") {
    const werte = (abschnitt[feld] as number[] | null | undefined) ?? [];
    const einheit = art === "liste_meter" ? "m" : "s";
    return (
      <fieldset
        className={`${s.listenFeld} ${geaendertText ? s.geaendert : ""}`}
        aria-describedby={fehler ? `${abschnitt.id}-${feld}-fehler` : undefined}
      >
        <legend className={s.feldLabel}>{label}</legend>
        {geaendertText && <p className={s.hilfe}>{geaendertText}</p>}
        <div className={s.serienListe}>
          {werte.map((wert, nr) => (
            <NumberInput
              // Position ist hier die Identität: ein Wert je Serie.
              // biome-ignore lint/suspicious/noArrayIndexKey: ein Feld je Serie
              key={nr}
              label={t("ablauf.serie_nr", { nr: nr + 1 })}
              size="sm"
              min={0}
              allowNegative={false}
              decimalSeparator=","
              suffix={` ${einheit}`}
              classNames={{ input: "num" }}
              value={wert}
              onChange={(eingabe) =>
                setze(
                  werte.map((alt, i) =>
                    i === nr ? (typeof eingabe === "number" ? eingabe : 0) : alt,
                  ),
                )
              }
            />
          ))}
        </div>
        {fehler && (
          <p className={s.fehlerText} id={`${abschnitt.id}-${feld}-fehler`} role="alert">
            {fehler}
          </p>
        )}
      </fieldset>
    );
  }

  return (
    <ZahlFeld
      label={label}
      wert={(abschnitt[feld] as number | null | undefined) ?? null}
      ganz={art === "ganz"}
      min={art === "ganz" ? 1 : 0}
      einheit={art === "sekunden" ? "s" : art === "meter" ? "m" : undefined}
      geaendertText={geaendertText}
      fehler={fehler}
      onWert={setze}
    />
  );
}

/** Ringwerte als Text „10, 7, 0“; gespeichert wird die Zahlenliste. */
function RingwerteFeld({
  label,
  werte,
  geaendertText,
  fehler,
  onWerte,
}: {
  label: string;
  werte: number[];
  geaendertText?: string;
  fehler?: string;
  onWerte: (werte: number[]) => void;
}) {
  const { t } = useTranslation("turnier");
  const [text, setText] = useState(werte.join(", "));
  const [bekannt, setBekannt] = useState(werte);
  if (!gleich(bekannt, werte)) {
    setBekannt(werte);
    setText(werte.join(", "));
  }
  return (
    <TextInput
      label={label}
      description={geaendertText ?? t("ablauf.feld.ringwerte_hilfe")}
      size="md"
      value={text}
      error={fehler}
      classNames={{ input: "num" }}
      className={geaendertText ? s.geaendert : undefined}
      onChange={(e) => {
        const neu = e.currentTarget.value;
        setText(neu);
        const zahlen = neu
          .split(/[;,\s]+/)
          .filter(Boolean)
          .map((teil) => Number(teil));
        if (zahlen.every((zahl) => Number.isFinite(zahl))) {
          setBekannt(zahlen);
          onWerte(zahlen);
        }
      }}
    />
  );
}

function Trefferaufnahme({
  abschnitt,
  geaendertText,
  fehler,
  onAendern,
}: {
  abschnitt: Abschnitt;
  geaendertText?: string;
  fehler?: string;
  onAendern: (abschnitt: Abschnitt) => void;
}) {
  const { t, i18n } = useTranslation("turnier");
  const gewaehlt = new Set(abschnitt.trefferaufnahme_nach ?? []);
  const id = `trefferaufnahme-${abschnitt.id}`;
  return (
    <div className={`${s.feldGruppe} ${geaendertText ? s.geaendert : ""}`}>
      <span className={s.feldLabel} id={id}>
        {t("ablauf.feld.trefferaufnahme_nach")}
      </span>
      <fieldset className={s.wahlReihe} aria-labelledby={id}>
        {Array.from({ length: abschnitt.serien }, (_, i) => i + 1).map((nr) => (
          <button
            key={nr}
            type="button"
            className={s.wahlchip}
            aria-pressed={gewaehlt.has(nr)}
            onClick={() => onAendern(schalteTrefferaufnahme(abschnitt, nr))}
          >
            {t("ablauf.nach_serie", { nr: formatZahl(nr, {}, i18n.language) })}
          </button>
        ))}
      </fieldset>
      <p className={s.hilfe}>{geaendertText ?? t("ablauf.feld.trefferaufnahme_hilfe")}</p>
      {fehler && (
        <p className={s.fehlerText} role="alert">
          {fehler}
        </p>
      )}
    </div>
  );
}
