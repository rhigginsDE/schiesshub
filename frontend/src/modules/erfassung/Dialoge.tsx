import { Button, Checkbox, Loader, Radio, Stack, Textarea } from "@mantine/core";
import { CheckCheck, CircleAlert, TriangleAlert } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Dialog } from "../../components/Dialog";
import { useFehlerText } from "../../components/FehlerHinweis";
import { formatWert, serienAnzeige } from "./anzeige";
import {
  ABBRUCHGRUENDE,
  type Abbruchgrund,
  type ErgebnisStand,
  type FeldBeschreibung,
  type Formular,
  type Rohwerte,
} from "./api";
import { wertText } from "./eingabe";
import s from "./erfassung.module.css";
import {
  type Aenderung,
  entwurfAus,
  feldAktiv,
  gleicheRohwerte,
  NORMAL,
  schuesseAus,
  serieAus,
  statusAus,
  wertAus,
} from "./rohwerte";

interface VorgangProps {
  offen: boolean;
  laedt: boolean;
  fehler: unknown;
  onSchliessen: () => void;
}

/** Wer und was: Startnummer, Name, Wettbewerb und Klasse für den Abgleich mit dem Startzettel. */
export interface PruefKopf {
  startnummer: number;
  name: string;
  wettbewerb: string;
  kennziffer: string | null;
  klasse: string | null;
}

interface PruefDialogProps extends VorgangProps {
  form: Formular;
  kopf: PruefKopf;
  /** Frisch vom Server geladen; `null`, solange er lädt */
  stand: ErgebnisStand | null;
  standLaedt: boolean;
  standFehler: unknown;
  /** Der Server hatte beim Abschließen andere Werte (409); `stand` ist der neu geladene. */
  geaendert?: boolean;
  onNeuLaden: () => void;
  /** Rohwerte der Eingabe auf diesem Gerät (zum Vergleich mit dem Server) */
  lokal: Rohwerte;
  onBestaetigen: (stand: ErgebnisStand) => void;
}

/**
 * Prüfansicht vor dem Abschluss: zeigt das Ergebnis so, wie der Server es hat (frisch geladen),
 * gesperrt. Abgeschlossen wird genau dieser Stand (Sequenznummer); weicht er von der Eingabe ab,
 * geht es nur zurück zur Eingabe. Warnungen des Servers verlangen eine ausdrückliche Bestätigung.
 */
export function PruefDialog({
  offen,
  laedt,
  fehler,
  onSchliessen,
  form,
  kopf,
  stand,
  standLaedt,
  standFehler,
  geaendert = false,
  onNeuLaden,
  lokal,
  onBestaetigen,
}: PruefDialogProps) {
  const { t } = useTranslation("erfassung");
  const fehlerText = useFehlerText();
  // Der Haken gilt nur für den Stand, an dem er gesetzt wurde (nach dem Neuladen neu prüfen).
  const [geprueftBei, setGeprueftBei] = useState<number | null>(null);
  const geprueft = stand !== null && geprueftBei === stand.seq;
  const wertung = stand?.computed ?? null;
  const warnungen = wertung?.warnings ?? [];
  const abweichung = stand !== null && !gleicheRohwerte(lokal, stand.raw);
  const erledigt = stand !== null && (stand.status === "final" || stand.status === "aborted");
  const unvollstaendig = stand !== null && !(wertung?.complete ?? false);
  const sperre = abweichung || erledigt || unvollstaendig;
  const bereit = stand !== null && !standLaedt && !sperre && (warnungen.length === 0 || geprueft);

  return (
    <Dialog
      opened={offen}
      onClose={onSchliessen}
      title={t("abschluss.titel")}
      centered
      size="lg"
      closeButtonProps={{ "aria-label": t("shell:dialog.schliessen") }}
    >
      <div className={s.pruefung}>
        <header className={s.pruefKopf}>
          <span className={`${s.startnummer} num`}>
            <span className="nur-screenreader">{t("kopf.startnummer_kurz")} </span>
            {kopf.startnummer}
          </span>
          <div>
            <strong className={s.pruefName}>{kopf.name}</strong>
            <p className={s.pruefWettbewerb}>
              {kopf.kennziffer && <span className="num">{kopf.kennziffer}</span>}
              {kopf.kennziffer && " · "}
              {kopf.wettbewerb}
              {kopf.klasse && ` · ${t("auswahl.klasse", { klasse: kopf.klasse })}`}
            </p>
          </div>
        </header>

        {geaendert && (
          <div className={s.banner} data-ton="warn" role="alert">
            <TriangleAlert aria-hidden />
            <div>
              <strong>{t("abschluss.geaendert")}</strong>
              <p>{t("abschluss.geaendert_text")}</p>
            </div>
          </div>
        )}

        {stand === null ? (
          standFehler ? (
            <div className={s.banner} data-ton="krit" role="alert">
              <CircleAlert aria-hidden />
              <div>
                <p>{fehlerText(standFehler)}</p>
              </div>
              <div className={s.bannerAktionen}>
                <Button variant="default" onClick={onNeuLaden}>
                  {t("abschluss.erneut")}
                </Button>
              </div>
            </div>
          ) : (
            <p className={s.pruefLaedt} aria-busy="true">
              <Loader size={16} aria-hidden />
              {t("abschluss.laedt")}
            </p>
          )
        ) : (
          <>
            <p className="gedaempft">{t("abschluss.text")}</p>
            <ServerSerien form={form} stand={stand} />
            <div className={s.pruefErgebnis}>
              <span className="h-label">{t("abschluss.ergebnis")}</span>
              <strong className="num">
                {wertung ? formatWert(wertung.score) : formatWert(stand.score)}
              </strong>
              {wertung && <span className={s.gesamtEinheit}>{wertung.unit}</span>}
            </div>

            {abweichung && <Sperre text={t("abschluss.abweichung")} />}
            {!abweichung && erledigt && <Sperre text={t("abschluss.schon_erledigt")} />}
            {!abweichung && !erledigt && unvollstaendig && (
              <Sperre text={t("abschluss.unvollstaendig")} />
            )}

            {!sperre && warnungen.length > 0 && (
              <div className={s.banner} data-ton="warn" role="alert">
                <TriangleAlert aria-hidden />
                <div>
                  <strong>{t("abschluss.warnungen")}</strong>
                  <ul className={s.pruefWarnungen}>
                    {warnungen.map((w) => (
                      <li key={`${w.path}-${w.message}`}>{w.message}</li>
                    ))}
                  </ul>
                  <Checkbox
                    className={s.pruefHaken}
                    size="md"
                    checked={geprueft}
                    onChange={(e) =>
                      setGeprueftBei(e.currentTarget.checked && stand ? stand.seq : null)
                    }
                    label={t("abschluss.plausibel")}
                  />
                </div>
              </div>
            )}
            {!sperre && <p className={s.klein}>{t("abschluss.danach")}</p>}
          </>
        )}

        {fehler ? (
          <p className={s.meldungFehler} role="alert">
            {fehlerText(fehler)}
          </p>
        ) : null}

        <div className={s.pruefAktionen}>
          <Button
            variant="default"
            size="lg"
            onClick={onSchliessen}
            disabled={laedt}
            data-autofocus
          >
            {t("abschluss.zurueck")}
          </Button>
          <Button
            size="lg"
            leftSection={<CheckCheck aria-hidden />}
            loading={laedt}
            disabled={!bereit}
            onClick={() => stand && onBestaetigen(stand)}
          >
            {t("abschluss.bestaetigen")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function Sperre({ text }: { text: string }) {
  return (
    <div className={s.banner} data-ton="krit" role="alert">
      <CircleAlert aria-hidden />
      <div>
        <p>{text}</p>
      </div>
    </div>
  );
}

/** Serien mit den Werten aus den Rohwerten des Servers und dem Serienergebnis des Servers. */
function ServerSerien({ form, stand }: { form: Formular; stand: ErgebnisStand }) {
  const { t } = useTranslation("erfassung");
  const entwurf = entwurfAus(stand.raw);
  return (
    <div className={s.pruefSerien}>
      {form.sections.map((abschnitt) => {
        const wertungAbschnitt = stand.computed?.sections.find((w) => w.id === abschnitt.id);
        return (
          <section key={abschnitt.id} aria-label={abschnitt.name}>
            {form.sections.length > 1 && <h3 className="h-label">{abschnitt.name}</h3>}
            <ol className={s.pruefListe}>
              {abschnitt.series.map((serie) => {
                const option = statusAus(entwurf, abschnitt.id, serie);
                const roh = serieAus(entwurf, abschnitt.id, serie.index);
                if (serie.struck && Object.keys(roh).length === 0) return null;
                const anzeige = serienAnzeige(wertungAbschnitt?.series[serie.index], t);
                const werte = serie.fields
                  .filter((feld) => feld.kind !== "choice")
                  .map((feld) => ({
                    feld,
                    text: !feldAktiv(option, feld.key)
                      ? t("feld.entfaellt")
                      : feldText(feld, feld.kind === "shots" ? schuesseAus(roh) : roh[feld.key], t),
                  }));
                return (
                  <li key={serie.index} className={s.pruefZeile}>
                    <span className={s.pruefSerie}>
                      {serie.label}
                      {serie.struck && ` · ${t("serie.gestrichen")}`}
                    </span>
                    <span className={s.pruefWerte}>
                      {option && option.key !== NORMAL && (
                        <span className={s.statusMarke}>{option.label}</span>
                      )}
                      {werte.map(({ feld, text }) => (
                        <span key={feld.key}>
                          <span className="gedaempft">{feld.label} </span>
                          <strong className="num">{text}</strong>
                        </span>
                      ))}
                    </span>
                    <span className={`${s.pruefSerienWert} num`}>
                      {anzeige.wert}
                      {anzeige.einheit && ` ${t(`einheit.${anzeige.einheit}`)}`}
                    </span>
                  </li>
                );
              })}
            </ol>
            {abschnitt.fields
              .filter((feld) => feld.kind !== "choice")
              .map((feld) => (
                <p key={feld.key} className={s.pruefZeile}>
                  <span className={s.pruefSerie}>{feld.label}</span>
                  <strong className="num">
                    {feldText(
                      feld,
                      wertAus(entwurf, { abschnitt: abschnitt.id, serie: null, key: feld.key }),
                      t,
                    )}
                  </strong>
                </p>
              ))}
          </section>
        );
      })}
    </div>
  );
}

/** Anzeigetext eines Werts (Zeit mit Komma, Schüsse als Reihe, Auswahl als Bezeichnung). */
export function feldText(
  feld: FeldBeschreibung,
  wert: unknown,
  t: ReturnType<typeof useTranslation<"erfassung">>["t"],
): string {
  if (wert === undefined || wert === null || (Array.isArray(wert) && wert.length === 0)) {
    return feld.kind === "choice"
      ? (feld.options?.find((o) => o.key === NORMAL)?.label ?? t("feld.leer_wert"))
      : t("feld.leer_wert");
  }
  // Schüsse als Reihe; Zehntel mit Komma („10,4 9,8“).
  if (Array.isArray(wert)) return wert.map((einzeln) => wertText(feld, einzeln)).join(" ");
  if (feld.kind === "choice")
    return feld.options?.find((o) => o.key === wert)?.label ?? String(wert);
  const text = wertText(feld, wert);
  return feld.kind === "time" ? `${text} ${t("einheit.sekunden")}` : text;
}

/** Korrektur: geänderte Felder alt → neu. Das neue Ergebnis rechnet der Server erst beim Speichern. */
export function AenderungsListe({ liste }: { liste: readonly Aenderung[] }) {
  const { t } = useTranslation("erfassung");
  if (liste.length === 0) return null;
  return (
    <div className={s.aenderungsBox}>
      <span className="h-label">{t("korrektur.aenderungen")}</span>
      <ul className={s.aenderungsListe}>
        {liste.map((a) => (
          <li key={a.ort}>
            <span>{a.ort}</span>
            <strong className="num">
              {t("korrektur.alt_neu", {
                vorher: feldText(a.feld, a.vorher, t),
                nachher: feldText(a.feld, a.nachher, t),
              })}
            </strong>
          </li>
        ))}
      </ul>
      <p className={s.klein}>{t("korrektur.server_rechnet")}</p>
    </div>
  );
}

export function AbbruchDialog({
  offen,
  laedt,
  fehler,
  onSchliessen,
  onBestaetigen,
  wer,
}: VorgangProps & {
  onBestaetigen: (grund: Abbruchgrund, text: string | null) => void;
  wer: string;
}) {
  const { t } = useTranslation("erfassung");
  const fehlerText = useFehlerText();
  const [grund, setGrund] = useState<Abbruchgrund | null>(null);
  const [text, setText] = useState("");
  return (
    <Bestaetigung
      offen={offen}
      titel={t("abbruch.titel")}
      text={t("abbruch.text", { wer })}
      bestaetigen={t("abbruch.bestaetigen")}
      abbrechen={t("dialog.abbrechen")}
      ton="gefahr"
      laedt={laedt}
      gesperrt={grund === null}
      fehler={fehler ? fehlerText(fehler) : undefined}
      onSchliessen={onSchliessen}
      onBestaetigen={() => grund && onBestaetigen(grund, text.trim() || null)}
    >
      <Radio.Group
        value={grund}
        onChange={(wert) => setGrund(wert as Abbruchgrund)}
        label={t("abbruch.art")}
      >
        <Stack gap="xs" mt="xs">
          {ABBRUCHGRUENDE.map((g) => (
            <Radio
              key={g}
              value={g}
              label={t(`abbruch.lang.${g}`)}
              size="md"
              classNames={{ root: s.radioZeile }}
            />
          ))}
        </Stack>
      </Radio.Group>
      <Textarea
        label={t("abbruch.grund")}
        value={text}
        onChange={(e) => setText(e.currentTarget.value)}
        maxLength={500}
        autosize
        minRows={2}
      />
    </Bestaetigung>
  );
}

/** Rückfrage mit Pflichtgrund (Korrektur speichern, wieder öffnen). */
export function GrundDialog({
  offen,
  laedt,
  fehler,
  onSchliessen,
  onBestaetigen,
  titel,
  text,
  bestaetigen,
  children,
}: VorgangProps & {
  onBestaetigen: (grund: string) => void;
  titel: string;
  text: string;
  bestaetigen: string;
  children?: ReactNode;
}) {
  const { t } = useTranslation("erfassung");
  const fehlerText = useFehlerText();
  const [grund, setGrund] = useState("");
  return (
    <Bestaetigung
      offen={offen}
      titel={titel}
      text={text}
      bestaetigen={bestaetigen}
      abbrechen={t("dialog.abbrechen")}
      laedt={laedt}
      gesperrt={grund.trim() === ""}
      fehler={fehler ? fehlerText(fehler) : undefined}
      onSchliessen={onSchliessen}
      onBestaetigen={() => onBestaetigen(grund.trim())}
    >
      {children}
      <Textarea
        label={t("dialog.grund")}
        description={t("dialog.grund_hilfe")}
        value={grund}
        onChange={(e) => setGrund(e.currentTarget.value)}
        maxLength={500}
        autosize
        minRows={2}
        required
        data-autofocus
      />
    </Bestaetigung>
  );
}
