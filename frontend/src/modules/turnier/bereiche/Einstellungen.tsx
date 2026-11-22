import { NumberInput, SegmentedControl, Select, Switch, TextInput } from "@mantine/core";
import { Info } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { GeldEingabe } from "../../../components/GeldEingabe";
import { useTurnierAendern } from "../abfragen";
import a from "../aufgaben.module.css";
import { feldFehlerFuer } from "../senden";
import s from "../turnier.module.css";
import type {
  TurnierEinstellungen,
  TurnierEinstellungenAenderung,
  TurnierUebersicht,
  ZusatzEinstellungen,
} from "../typen";
import { useEntwurf } from "../useEntwurf";
import { BereichKopf, Erweitert, HILFE_UNTEN, Speicherleiste } from "./Bausteine";

/** Felder, die unter „Erweitert“ stehen; ein Fehler dort klappt den Abschnitt auf. */
const ERWEITERT = [
  "currency",
  "default_capture_mode",
  "default_changeover_minutes",
  "first_start_number",
  "protest_minutes",
  "protest_restart_on_correction",
  "timezone",
] as const;

export type EinstellungsWerte = Omit<TurnierEinstellungen, "display" | "first_start_number"> &
  ZusatzEinstellungen;

const FELDER = [
  "protest_minutes",
  "currency",
  "default_fee_first_cents",
  "default_fee_repeat_cents",
  "default_multi_start",
  "default_max_starts",
  "default_multi_start_rule",
  "default_changeover_minutes",
  "default_capture_mode",
  "first_start_number",
  "protest_restart_on_correction",
  "timezone",
] as const;

/**
 * Zeitzonen zur Auswahl: Deutschland zuerst, dann die Nachbarländer und übliche Zonen in Europa.
 * Ein gespeicherter Wert, der hier fehlt, kommt beim Anzeigen dazu (`zeitzonenAuswahl`).
 */
export const ZEITZONEN = [
  "Europe/Berlin",
  "Europe/Vienna",
  "Europe/Zurich",
  "Europe/Luxembourg",
  "Europe/Brussels",
  "Europe/Amsterdam",
  "Europe/Paris",
  "Europe/Copenhagen",
  "Europe/Prague",
  "Europe/Warsaw",
  "Europe/Rome",
  "Europe/Madrid",
  "Europe/Stockholm",
  "Europe/London",
  "Europe/Lisbon",
  "Europe/Helsinki",
  "Europe/Athens",
  "UTC",
] as const;

/** Auswahl der Zeitzonen; ein gespeicherter Wert außerhalb der Liste steht mit seinem Namen dabei. */
export function zeitzonenAuswahl(
  gespeichert: string | undefined,
  t: (schluessel: string) => string,
): { value: string; label: string }[] {
  const liste: { value: string; label: string }[] = ZEITZONEN.map((zone) => ({
    value: zone,
    label: t(`zeitzone.${zone.replace("/", "_")}`),
  }));
  if (gespeichert && !liste.some((eintrag) => eintrag.value === gespeichert)) {
    liste.push({ value: gespeichert, label: gespeichert.replace(/_/g, " ") });
  }
  return liste;
}

export const REGELN = ["best", "first", "all"] as const;

/** Nur geänderte Einstellungen; ohne Mehrfachstart gilt genau ein Start. */
export function einstellungsAenderung(
  werte: EinstellungsWerte,
  basis: EinstellungsWerte,
): TurnierEinstellungenAenderung & ZusatzEinstellungen {
  const bereinigt: EinstellungsWerte = {
    ...werte,
    default_max_starts: werte.default_multi_start ? werte.default_max_starts : 1,
  };
  const aenderung: Record<string, unknown> = {};
  for (const feld of FELDER) {
    if (!(feld in bereinigt) && !(feld in basis)) continue;
    if (bereinigt[feld] !== basis[feld]) aenderung[feld] = bereinigt[feld];
  }
  return aenderung as TurnierEinstellungenAenderung & ZusatzEinstellungen;
}

export function pruefeEinstellungen(werte: EinstellungsWerte, t: (s: string) => string) {
  const fehler: Record<string, string> = {};
  if (!/^[A-Z]{3}$/.test(werte.currency)) fehler.currency = t("pruefung.waehrung");
  if (werte.default_multi_start && !(werte.default_max_starts >= 2)) {
    fehler.default_max_starts = t("pruefung.max_starts");
  }
  if (werte.protest_minutes !== null && werte.protest_minutes !== undefined) {
    if (!(werte.protest_minutes >= 1)) fehler.protest_minutes = t("pruefung.ganz_positiv");
  }
  if (!(werte.default_changeover_minutes >= 0)) {
    fehler.default_changeover_minutes = t("pruefung.nicht_negativ");
  }
  if (
    "first_start_number" in werte &&
    werte.first_start_number !== null &&
    werte.first_start_number !== undefined &&
    !(werte.first_start_number >= 1)
  ) {
    fehler.first_start_number = t("pruefung.ganz_positiv");
  }
  return fehler;
}

function alsZahl(wert: string | number): number {
  return typeof wert === "number" ? wert : Number.NaN;
}

/**
 * Startgeld und Vorgaben: Startgeld und Mehrfachstart oben, Seltenes unter „Erweitert“. Die Werte
 * gelten für Wettbewerbe, die danach hinzukommen; darum steht der Schritt vor den Wettbewerben.
 */
export function Einstellungen({
  turnier,
  gesperrt,
}: {
  turnier: TurnierUebersicht;
  gesperrt: boolean;
}) {
  const { t } = useTranslation("turnier");
  const aendern = useTurnierAendern(turnier.id);
  const quelle = useMemo<EinstellungsWerte>(() => {
    const { display: _anzeige, ...rest } = turnier.settings as TurnierEinstellungen &
      ZusatzEinstellungen;
    return rest;
  }, [turnier.settings]);
  const [geprueft, setGeprueft] = useState(false);
  const entwurf = useEntwurf(quelle, {
    speichern: async () => {
      setGeprueft(true);
      if (Object.keys(pruefeEinstellungen(entwurf.werte, t)).length > 0) return false;
      try {
        await aendern.mutateAsync({
          settings: einstellungsAenderung(entwurf.werte, entwurf.basis),
        });
        return true;
      } catch {
        return false;
      }
    },
  });
  const { werte } = entwurf;
  // Gesetzte Werte bleiben im Entwurf; „aus“ blendet nur das Feld aus.
  const [fristMinuten, setFristMinuten] = useState(werte.protest_minutes ?? 30);
  const mitStartnummer = "first_start_number" in quelle;
  const fristAn = werte.protest_minutes !== null && werte.protest_minutes !== undefined;
  // Fehlt der Wert (älterer Server), gilt wie beim Server: Frist beginnt neu.
  const neuNachKorrektur = werte.protest_restart_on_correction ?? true;

  const eigene = geprueft ? pruefeEinstellungen(werte, t) : {};
  const server = aendern.isError ? feldFehlerFuer(aendern.error, FELDER, "settings") : {};
  const fehler: Record<string, string> = { ...server, ...eigene };
  const setze = <K extends keyof EinstellungsWerte>(feld: K, wert: EinstellungsWerte[K]) => {
    entwurf.setWerte({ ...werte, [feld]: wert });
    if (aendern.isError) aendern.reset();
  };
  const waehrung = /^[A-Z]{3}$/.test(werte.currency) ? werte.currency : "EUR";
  const meldungBetrag = t("pruefung.betrag_format");
  const vorhanden = turnier.competitions.length;

  return (
    <form
      className={s.bereich}
      noValidate
      onSubmit={(ereignis) => {
        ereignis.preventDefault();
        setGeprueft(true);
        if (Object.keys(pruefeEinstellungen(werte, t)).length > 0) return;
        aendern.mutate({ settings: einstellungsAenderung(werte, entwurf.basis) });
      }}
    >
      <BereichKopf
        titel={t("bereich.einstellungen.titel")}
        text={t("bereich.einstellungen.text")}
      />
      {vorhanden > 0 && (
        <p className={`inset ${a.infoKasten}`}>
          <Info aria-hidden />
          {t("einstellungen.vorhanden", { count: vorhanden })}
        </p>
      )}

      <section className={`panel ${s.formular}`} aria-labelledby="einst-startgeld">
        <h3 className="h-label" id="einst-startgeld">
          {t("einstellungen.startgeld")}
        </h3>
        <GeldEingabe
          label={t("einstellungen.startgeld_feld")}
          description={t("einstellungen.startgeld_hilfe")}
          inputWrapperOrder={HILFE_UNTEN}
          size="md"
          className={s.schmal}
          waehrung={waehrung}
          meldungUnlesbar={meldungBetrag}
          disabled={gesperrt}
          wert={werte.default_fee_first_cents}
          error={fehler.default_fee_first_cents}
          onWert={(cent) => setze("default_fee_first_cents", cent ?? 0)}
        />
        <Switch
          size="md"
          label={t("einstellungen.mehrfach_standard")}
          description={t("einstellungen.mehrfach_hilfe")}
          disabled={gesperrt}
          checked={werte.default_multi_start}
          onChange={(e) => {
            const an = e.currentTarget.checked;
            entwurf.setWerte({
              ...werte,
              default_multi_start: an,
              default_max_starts: an ? Math.max(2, werte.default_max_starts) : 1,
            });
          }}
        />
        {werte.default_multi_start && (
          <div className={s.dreiSpalten}>
            <GeldEingabe
              label={t("feld.nachkauf")}
              size="md"
              waehrung={waehrung}
              meldungUnlesbar={meldungBetrag}
              disabled={gesperrt}
              wert={werte.default_fee_repeat_cents}
              error={fehler.default_fee_repeat_cents}
              onWert={(cent) => setze("default_fee_repeat_cents", cent ?? 0)}
            />
            <NumberInput
              label={t("feld.max_starts")}
              size="md"
              min={2}
              max={99}
              allowDecimal={false}
              disabled={gesperrt}
              value={werte.default_max_starts}
              error={fehler.default_max_starts}
              onChange={(wert) => setze("default_max_starts", alsZahl(wert))}
            />
            <Select
              label={t("feld.regel")}
              size="md"
              allowDeselect={false}
              disabled={gesperrt}
              value={werte.default_multi_start_rule}
              data={REGELN.map((regel) => ({ value: regel, label: t(`regel.${regel}`) }))}
              onChange={(wert) =>
                wert && setze("default_multi_start_rule", wert as (typeof REGELN)[number])
              }
            />
          </div>
        )}
      </section>

      <Erweitert
        titel={t("erweitert.titel")}
        text={t("einstellungen.erweitert_inhalt")}
        fehler={ERWEITERT.some((feld) => fehler[feld])}
      >
        <div className={s.feldGruppe}>
          <span className={s.feldLabel} id="einst-erfassung">
            {t("feld.erfassung")}
          </span>
          <SegmentedControl
            aria-labelledby="einst-erfassung"
            size="md"
            className={s.segmente}
            disabled={gesperrt}
            value={werte.default_capture_mode}
            onChange={(wert) =>
              setze("default_capture_mode", wert as EinstellungsWerte["default_capture_mode"])
            }
            data={[
              { value: "series", label: t("erfassung.series") },
              { value: "shot", label: t("erfassung.shot") },
            ]}
          />
          <p className={s.hilfe}>{t(`erfassung.${werte.default_capture_mode}_hilfe`)}</p>
        </div>
        <NumberInput
          label={t("feld.wechselzeit")}
          description={t("feld.wechselzeit_hilfe")}
          inputWrapperOrder={HILFE_UNTEN}
          size="md"
          min={0}
          max={240}
          allowDecimal={false}
          suffix={` ${t("einheit.min")}`}
          className={s.schmal}
          disabled={gesperrt}
          value={werte.default_changeover_minutes}
          error={fehler.default_changeover_minutes}
          onChange={(wert) => setze("default_changeover_minutes", alsZahl(wert))}
        />
        {mitStartnummer && (
          <NumberInput
            label={t("einstellungen.erste_startnummer")}
            description={t("einstellungen.erste_startnummer_hilfe")}
            inputWrapperOrder={HILFE_UNTEN}
            size="md"
            min={1}
            allowDecimal={false}
            className={s.schmal}
            disabled={gesperrt}
            value={werte.first_start_number ?? ""}
            error={fehler.first_start_number}
            onChange={(wert) => setze("first_start_number", typeof wert === "number" ? wert : null)}
          />
        )}
        <div className={s.zeileMitFeld}>
          <Switch
            size="md"
            label={t("einstellungen.einspruch")}
            description={
              fristAn ? t("einstellungen.einspruch_an") : t("einstellungen.einspruch_aus")
            }
            disabled={gesperrt}
            checked={fristAn}
            onChange={(e) =>
              setze("protest_minutes", e.currentTarget.checked ? fristMinuten : null)
            }
          />
          {fristAn && (
            <NumberInput
              aria-label={t("einstellungen.einspruch_minuten")}
              size="md"
              min={1}
              allowDecimal={false}
              suffix={` ${t("einheit.min")}`}
              className={s.schmal}
              disabled={gesperrt}
              value={werte.protest_minutes ?? ""}
              error={fehler.protest_minutes}
              onChange={(wert) => {
                const zahl = alsZahl(wert);
                if (Number.isFinite(zahl)) setFristMinuten(zahl);
                setze("protest_minutes", zahl);
              }}
            />
          )}
        </div>
        {fristAn && (
          <Switch
            size="md"
            label={t("einstellungen.einspruch_neu")}
            description={
              neuNachKorrektur
                ? t("einstellungen.einspruch_neu_an")
                : t("einstellungen.einspruch_neu_aus")
            }
            disabled={gesperrt}
            checked={neuNachKorrektur}
            error={fehler.protest_restart_on_correction}
            onChange={(e) => setze("protest_restart_on_correction", e.currentTarget.checked)}
          />
        )}
        <Select
          label={t("einstellungen.zeitzone")}
          description={t("einstellungen.zeitzone_hilfe")}
          inputWrapperOrder={HILFE_UNTEN}
          size="md"
          classNames={{ wrapper: s.schmal }}
          allowDeselect={false}
          checkIconPosition="right"
          disabled={gesperrt}
          value={werte.timezone ?? null}
          data={zeitzonenAuswahl(werte.timezone, t)}
          error={fehler.timezone}
          onChange={(wert) => wert && setze("timezone", wert)}
        />
        <TextInput
          label={t("einstellungen.waehrung")}
          description={t("einstellungen.waehrung_hilfe")}
          inputWrapperOrder={HILFE_UNTEN}
          size="md"
          maxLength={3}
          className={s.schmal}
          disabled={gesperrt}
          value={werte.currency}
          error={fehler.currency}
          onChange={(e) => setze("currency", e.currentTarget.value.toUpperCase())}
        />
      </Erweitert>

      <Speicherleiste
        geaendert={entwurf.geaendert}
        laedt={aendern.isPending}
        gespeichert={aendern.isSuccess && !entwurf.geaendert}
        fehler={fehler[""]}
        gesperrt={gesperrt}
        onVerwerfen={() => {
          entwurf.verwerfen();
          aendern.reset();
          setGeprueft(false);
        }}
      />
    </form>
  );
}
