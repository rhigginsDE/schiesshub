import {
  ActionIcon,
  Button,
  SegmentedControl,
  Skeleton,
  Switch,
  Textarea,
  TextInput,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Eye, EyeOff, FileText, Plus, Printer, Save, Trash2, Undo2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ReihenfolgeKnoepfe, verschiebe } from "../../../components/Reihenfolge";
import { Fehlerzustand, Leerzustand } from "../../../components/Zustand";
import { useBegriffe } from "../../../lib/begriffe";
import { fehlerText } from "../fehlertext";
import { feldFehlerFuer } from "../senden";
import t_s from "../turnier.module.css";
import type { TurnierUebersicht } from "../typen";
import { useEntwurf } from "../useEntwurf";
import {
  ausschreibungAbfrage,
  ausschreibungDokumentAbfrage,
  useAusschreibungSpeichern,
} from "./abfragen";
import s from "./ausschreibung.module.css";
import { BausteinBlatt, Blatt } from "./Blatt";
import { dokumentAusEntwurf, druckModell, istLeer } from "./dokument";
import {
  type Ausschreibung as AusschreibungDaten,
  type Baustein,
  ECKDATEN_FELDER,
  type Eckdaten,
} from "./typen";

export const DRUCK_PFAD = "/turnier/$turnierId/ausschreibung/druck";

/** Freie ID für einen neuen Text-Baustein: `abschnitt-1`, `abschnitt-2`, … */
export function neueBausteinId(bausteine: readonly Baustein[]): string {
  const vergeben = new Set(bausteine.map((b) => b.id));
  let nr = 1;
  while (vergeben.has(`abschnitt-${nr}`)) nr += 1;
  return `abschnitt-${nr}`;
}

/** Für den Server: leere Eckdaten werden `null`, Texte ohne Rand-Leerzeichen. */
export function zumSpeichern(entwurf: AusschreibungDaten): AusschreibungDaten {
  const facts: Eckdaten = {};
  for (const feld of ECKDATEN_FELDER) {
    const wert = entwurf.facts[feld]?.trim();
    facts[feld] = wert ? wert : null;
  }
  return {
    title: entwurf.title?.trim() || null,
    facts,
    blocks: entwurf.blocks.map((b) => ({
      ...b,
      heading: b.heading.trim(),
      body: b.body.trimEnd(),
    })),
  };
}

const LEER: AusschreibungDaten = { title: null, facts: {}, blocks: [] };

/**
 * Reihenfolge der Standardgliederung (wie `announcement_outline.py`), nur um einen fehlenden
 * Abschnitt an sinnvoller Stelle einzufügen. Automatische Abschnitte zählen nach Art.
 */
const STANDARD_REIHENFOLGE: readonly string[] = [
  "begruessung",
  "veranstalter-und-ort",
  "dates",
  "teilnahmeberechtigung",
  "competitions",
  "ranges",
  "classes",
  "fees",
  "anmeldung",
  "ablauf",
  "sicherheit",
  "wertung",
  "einsprueche",
  "datenschutz",
  "kontakt",
];

/** Platz eines Abschnitts in der Standardgliederung: automatische nach Art, Texte nach ID. */
function standardPlatz(baustein: Pick<Baustein, "id" | "kind">): number {
  return STANDARD_REIHENFOLGE.indexOf(baustein.kind === "text" ? baustein.id : baustein.kind);
}

/** Ist dieser Abschnitt der Standardgliederung schon im Dokument? Wie der Server: Art bzw. ID. */
function schonDa(bausteine: readonly Baustein[], vorschlag: Baustein): boolean {
  return bausteine.some((b) =>
    vorschlag.kind === "text" ? b.id === vorschlag.id : b.kind === vorschlag.kind,
  );
}

/** Vom Server gemeldete fehlende Abschnitte, ohne die inzwischen im Entwurf eingefügten. */
export function fehlendeAbschnitte(
  vorschlaege: readonly Baustein[] | undefined,
  bausteine: readonly Baustein[],
): Baustein[] {
  return (vorschlaege ?? []).filter((vorschlag) => !schonDa(bausteine, vorschlag));
}

/**
 * Fügt einen fehlenden Abschnitt an sinnvoller Stelle ein: hinter den nächsten Vorgänger aus der
 * Standardgliederung, sonst vor den nächsten Nachfolger, sonst ans Ende.
 */
export function abschnittEinfuegen(bausteine: readonly Baustein[], neu: Baustein): Baustein[] {
  const platz = standardPlatz(neu);
  const liste = [...bausteine];
  if (platz >= 0) {
    let vorgaenger = -1;
    let nachfolger = -1;
    liste.forEach((b, i) => {
      const p = standardPlatz(b);
      if (p < 0) return;
      if (p < platz) vorgaenger = i;
      else if (p > platz && nachfolger < 0) nachfolger = i;
    });
    const ziel = vorgaenger >= 0 ? vorgaenger + 1 : nachfolger >= 0 ? nachfolger : liste.length;
    liste.splice(ziel, 0, neu);
    return liste;
  }
  return [...liste, neu];
}

export function Ausschreibung({
  turnier,
  gesperrt,
}: {
  turnier: TurnierUebersicht;
  gesperrt: boolean;
}) {
  const { t } = useTranslation("turnier");
  const abfrage = useQuery(ausschreibungAbfrage(turnier.id));

  if (abfrage.isPending) return <Skeleton height={480} radius="lg" />;
  if (abfrage.isError) {
    return (
      <div className="panel">
        <Fehlerzustand fehler={abfrage.error} onErneut={() => void abfrage.refetch()} />
      </div>
    );
  }
  if (abfrage.data === null) {
    return (
      <div className="panel">
        <Leerzustand
          icon={FileText}
          titel={t("ausschreibung.nicht_verfuegbar_titel")}
          text={t("ausschreibung.nicht_verfuegbar_text")}
        />
      </div>
    );
  }
  return <Editor turnier={turnier} quelle={abfrage.data} gesperrt={gesperrt} />;
}

function Editor({
  turnier,
  quelle,
  gesperrt,
}: {
  turnier: TurnierUebersicht;
  quelle: AusschreibungDaten;
  gesperrt: boolean;
}) {
  const { t, i18n } = useTranslation("turnier");
  const navigate = useNavigate();
  const speichern = useAusschreibungSpeichern(turnier.id);
  const server = useQuery(ausschreibungDokumentAbfrage(turnier.id));
  const saetze = useBegriffe();
  // Nur Ausgabe des Servers, gehört nicht in den Entwurf.
  const { missing_default_blocks: vorschlaege, ...gespeichert } = quelle;
  const entwurf = useEntwurf<AusschreibungDaten>(
    { ...LEER, ...gespeichert, facts: gespeichert.facts ?? {} },
    {
      speichern: async () => {
        try {
          await speichern.mutateAsync(zumSpeichern(entwurf.werte));
          return true;
        } catch {
          return false;
        }
      },
    },
  );
  const { werte } = entwurf;
  const [gewaehlt, setGewaehlt] = useState<string | null>(werte.blocks[0]?.id ?? null);
  const fehlend = fehlendeAbschnitte(vorschlaege, werte.blocks);
  const [ansicht, setAnsicht] = useState<"bearbeiten" | "vorschau">("bearbeiten");
  const [erstellt] = useState(() => new Date());

  const index = werte.blocks.findIndex((b) => b.id === gewaehlt);
  const baustein = index >= 0 ? werte.blocks[index] : undefined;
  const dokument = useMemo(
    () => dokumentAusEntwurf(werte, turnier, server.data, i18n.language, saetze),
    [werte, turnier, server.data, i18n.language, saetze],
  );
  const modell = useMemo(
    () =>
      druckModell(
        dokument,
        i18n.language,
        new Map(turnier.competitions.map((w) => [w.id, w.catalog_code ?? null] as const)),
      ),
    [dokument, i18n.language, turnier.competitions],
  );
  // Hilfetexte nennen die formellen Wörter, die auch im Blatt stehen (z. B. „Protestgebühr“).
  const begriffe = modell.begriffe;

  const felder = [
    "title",
    ...ECKDATEN_FELDER.map((f) => `facts.${f}`),
    ...werte.blocks.flatMap((_, i) => [`blocks.${i}`, `blocks.${i}.heading`, `blocks.${i}.body`]),
  ];
  const fehler = speichern.isError ? feldFehlerFuer(speichern.error, felder) : {};

  const setze = (neu: Partial<AusschreibungDaten>) => {
    entwurf.setWerte({ ...werte, ...neu });
    if (speichern.isError) speichern.reset();
  };
  const setzeBaustein = (id: string, neu: Partial<Baustein>) =>
    setze({ blocks: werte.blocks.map((b) => (b.id === id ? { ...b, ...neu } : b)) });
  const setzeEckdatum = (feld: keyof Eckdaten, wert: string) =>
    setze({ facts: { ...werte.facts, [feld]: wert } });

  return (
    <form
      className={s.editorRaster}
      data-ansicht={ansicht}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        speichern.mutate(zumSpeichern(werte));
      }}
    >
      {/* Kopf über alle Spalten */}
      <div className={s.editorKopf}>
        <div>
          <h2 className="h-section">{t("bereich.ausschreibung.titel")}</h2>
          <p className="gedaempft">{t("bereich.ausschreibung.text")}</p>
        </div>
        <SegmentedControl
          className={s.umschalter}
          value={ansicht}
          onChange={(wert) => setAnsicht(wert as typeof ansicht)}
          data={[
            { value: "bearbeiten", label: t("ausschreibung.ansicht_bearbeiten") },
            { value: "vorschau", label: t("ausschreibung.ansicht_vorschau") },
          ]}
        />
        <div className={s.editorAktionen}>
          <span className={s.zustand} aria-live="polite">
            {fehler[""] ? (
              <span className={t_s.fehlerText} role="alert">
                {fehler[""]}
              </span>
            ) : entwurf.geaendert ? (
              t("speichern.ungespeichert")
            ) : speichern.isSuccess ? (
              t("speichern.gespeichert")
            ) : null}
          </span>
          {entwurf.geaendert && (
            <Button
              variant="default"
              leftSection={<Undo2 aria-hidden />}
              onClick={() => {
                entwurf.verwerfen();
                speichern.reset();
              }}
            >
              {t("speichern.verwerfen")}
            </Button>
          )}
          <Button
            variant="default"
            leftSection={<Printer aria-hidden />}
            disabled={entwurf.geaendert}
            title={entwurf.geaendert ? t("ausschreibung.erst_speichern") : undefined}
            onClick={() => void navigate({ to: DRUCK_PFAD, params: { turnierId: turnier.id } })}
          >
            {t("ausschreibung.druckansicht")}
          </Button>
          <Button
            type="submit"
            leftSection={<Save aria-hidden />}
            loading={speichern.isPending}
            disabled={!entwurf.geaendert || gesperrt}
          >
            {t("speichern.knopf")}
          </Button>
        </div>
      </div>

      {/* Bausteine */}
      <section className={`panel ${s.spalte} ${s.listenSpalte}`} aria-labelledby="as-bausteine">
        <h3 className="h-label" id="as-bausteine">
          {t("ausschreibung.bausteine")}
        </h3>
        {/* Älteren Dokumenten fehlt womöglich ein Abschnitt der Standardgliederung: anbieten. */}
        {fehlend.length > 0 && !gesperrt && (
          <div className={s.fehltHinweis} role="status">
            {fehlend.map((vorschlag) => {
              const name =
                vorschlag.heading.trim() || t(`ausschreibung.art.${vorschlag.kind}`, begriffe);
              return (
                <div key={`${vorschlag.kind}-${vorschlag.id}`} className={s.fehltZeile}>
                  <span>{t("ausschreibung.fehlt_abschnitt", { name })}</span>
                  <Button
                    variant="default"
                    size="sm"
                    leftSection={<Plus aria-hidden />}
                    aria-label={t("ausschreibung.fehlt_einfuegen_lang", { name })}
                    onClick={() => {
                      // Gleiche ID schon vergeben (z. B. eigener Text „schiessstaende“): neue ID.
                      const neu = werte.blocks.some((b) => b.id === vorschlag.id)
                        ? { ...vorschlag, id: neueBausteinId(werte.blocks) }
                        : { ...vorschlag };
                      setze({ blocks: abschnittEinfuegen(werte.blocks, neu) });
                      setGewaehlt(neu.id);
                    }}
                  >
                    {t("ausschreibung.fehlt_einfuegen")}
                  </Button>
                </div>
              );
            })}
          </div>
        )}
        <ul className={s.liste}>
          {werte.blocks.map((b, i) => (
            <li
              key={b.id}
              className={s.eintrag}
              data-aktiv={b.id === gewaehlt || undefined}
              data-versteckt={!b.visible || undefined}
            >
              <button
                type="button"
                className={s.eintragKnopf}
                aria-current={b.id === gewaehlt ? "true" : undefined}
                onClick={() => setGewaehlt(b.id)}
              >
                <strong>{b.heading.trim() || t("ausschreibung.ohne_ueberschrift")}</strong>
                <span>
                  {t(`ausschreibung.art.${b.kind}`, begriffe)}
                  {!b.visible && ` · ${t("ausschreibung.ausgeblendet")}`}
                  {b.visible && istLeer(b) && (
                    <span className={s.leerMarke}> · {t("ausschreibung.noch_leer")}</span>
                  )}
                </span>
              </button>
              <span className={s.eintragAktionen}>
                <ReihenfolgeKnoepfe
                  index={i}
                  anzahl={werte.blocks.length}
                  hoch={t("aktion.nach_oben", { name: b.heading || b.id })}
                  runter={t("aktion.nach_unten", { name: b.heading || b.id })}
                  gesperrt={gesperrt}
                  onVerschieben={(richtung) =>
                    setze({ blocks: verschiebe(werte.blocks, i, richtung) })
                  }
                />
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  size={40}
                  disabled={gesperrt}
                  aria-label={
                    b.visible
                      ? t("ausschreibung.ausblenden", { name: b.heading || b.id })
                      : t("ausschreibung.einblenden", { name: b.heading || b.id })
                  }
                  aria-pressed={b.visible}
                  onClick={() => setzeBaustein(b.id, { visible: !b.visible })}
                >
                  {b.visible ? <Eye aria-hidden /> : <EyeOff aria-hidden />}
                </ActionIcon>
              </span>
            </li>
          ))}
        </ul>
        <Button
          variant="default"
          leftSection={<Plus aria-hidden />}
          disabled={gesperrt}
          onClick={() => {
            const neu: Baustein = {
              id: neueBausteinId(werte.blocks),
              kind: "text",
              heading: "",
              body: "",
              visible: true,
            };
            const ziel = index >= 0 ? index + 1 : werte.blocks.length;
            setze({ blocks: [...werte.blocks.slice(0, ziel), neu, ...werte.blocks.slice(ziel)] });
            setGewaehlt(neu.id);
          }}
        >
          {t("ausschreibung.text_hinzufuegen")}
        </Button>
      </section>

      {/* Formular */}
      <div className={`${s.spalte} ${s.formSpalte}`}>
        <fieldset className={`panel ${s.ohneRahmen}`} disabled={gesperrt}>
          <legend className="h-label">{t("ausschreibung.eckdaten_titel")}</legend>
          <TextInput
            label={t("ausschreibung.titel_feld")}
            description={t("ausschreibung.titel_hilfe", {
              titel: `${t("ausschreibung.titel_standard")} ${turnier.name}`,
            })}
            inputWrapperOrder={["label", "input", "description", "error"]}
            value={werte.title ?? ""}
            error={fehler.title}
            onChange={(e) => setze({ title: e.currentTarget.value })}
          />
          <div className={t_s.zweiSpalten}>
            <TextInput
              label={t("ausschreibung.eckdaten.venue")}
              placeholder={t("ausschreibung.platzhalter.venue")}
              value={werte.facts.venue ?? ""}
              error={fehler["facts.venue"]}
              onChange={(e) => setzeEckdatum("venue", e.currentTarget.value)}
            />
            <TextInput
              type="date"
              label={t("ausschreibung.eckdaten.registration_deadline")}
              value={werte.facts.registration_deadline ?? ""}
              error={fehler["facts.registration_deadline"]}
              onChange={(e) => setzeEckdatum("registration_deadline", e.currentTarget.value)}
            />
          </div>
          <Textarea
            label={t("ausschreibung.eckdaten.address")}
            placeholder={t("ausschreibung.platzhalter.address")}
            autosize
            minRows={2}
            value={werte.facts.address ?? ""}
            error={fehler["facts.address"]}
            onChange={(e) => setzeEckdatum("address", e.currentTarget.value)}
          />
          <Textarea
            label={t("ausschreibung.eckdaten.registration_info")}
            placeholder={t("ausschreibung.platzhalter.registration_info", begriffe)}
            autosize
            minRows={2}
            value={werte.facts.registration_info ?? ""}
            error={fehler["facts.registration_info"]}
            onChange={(e) => setzeEckdatum("registration_info", e.currentTarget.value)}
          />
          <div className={t_s.zweiSpalten}>
            <TextInput
              label={t("ausschreibung.eckdaten.contact_name")}
              value={werte.facts.contact_name ?? ""}
              error={fehler["facts.contact_name"]}
              onChange={(e) => setzeEckdatum("contact_name", e.currentTarget.value)}
            />
            <TextInput
              label={t("ausschreibung.eckdaten.contact_info")}
              placeholder={t("ausschreibung.platzhalter.contact_info")}
              value={werte.facts.contact_info ?? ""}
              error={fehler["facts.contact_info"]}
              onChange={(e) => setzeEckdatum("contact_info", e.currentTarget.value)}
            />
          </div>
        </fieldset>

        {baustein ? (
          <fieldset className={`panel ${s.ohneRahmen}`} disabled={gesperrt}>
            <legend className="h-label">
              {t("ausschreibung.baustein")}: {t(`ausschreibung.art.${baustein.kind}`, begriffe)}
            </legend>
            {fehler[`blocks.${index}`] && (
              <p className={t_s.fehlerText} role="alert">
                {fehler[`blocks.${index}`]}
              </p>
            )}
            <TextInput
              label={t("ausschreibung.ueberschrift")}
              value={baustein.heading}
              error={fehler[`blocks.${index}.heading`]}
              onChange={(e) => setzeBaustein(baustein.id, { heading: e.currentTarget.value })}
            />
            <Switch
              label={t("ausschreibung.sichtbar")}
              checked={baustein.visible}
              onChange={(e) => setzeBaustein(baustein.id, { visible: e.currentTarget.checked })}
            />
            {baustein.kind !== "text" && (
              <div className={`inset ${s.datenVorschau}`}>
                <p className={t_s.hilfe}>{t("ausschreibung.automatisch_hinweis")}</p>
                <AutoVorschau modellBausteine={modell.bausteine} id={baustein.id} />
              </div>
            )}
            <Textarea
              label={
                baustein.kind === "text" ? t("ausschreibung.text") : t("ausschreibung.zusatztext")
              }
              description={t("ausschreibung.text_hilfe")}
              placeholder={t(`ausschreibung.hinweis.${baustein.id}`, {
                ...begriffe,
                defaultValue:
                  baustein.kind === "text"
                    ? t("ausschreibung.hinweis_text")
                    : t("ausschreibung.hinweis_zusatz"),
              })}
              autosize
              minRows={baustein.kind === "text" ? 10 : 3}
              value={baustein.body}
              error={fehler[`blocks.${index}.body`]}
              onChange={(e) => setzeBaustein(baustein.id, { body: e.currentTarget.value })}
            />
            {baustein.kind === "text" && (
              <div className={t_s.knopfReihe}>
                <Button
                  variant="subtle"
                  color="gray"
                  leftSection={<Trash2 aria-hidden />}
                  onClick={() => {
                    setze({ blocks: werte.blocks.filter((b) => b.id !== baustein.id) });
                    setGewaehlt(werte.blocks[index + 1]?.id ?? werte.blocks[index - 1]?.id ?? null);
                  }}
                >
                  {t("ausschreibung.baustein_loeschen")}
                </Button>
              </div>
            )}
          </fieldset>
        ) : (
          <p className="gedaempft">{t("ausschreibung.keine_auswahl")}</p>
        )}
        {speichern.isError && !fehler[""] && Object.keys(fehler).length === 0 && (
          <p className={t_s.fehlerText} role="alert">
            {fehlerText(speichern.error)}
          </p>
        )}
      </div>

      {/* Vorschau */}
      <section
        className={`${s.spalte} ${s.vorschauSpalte}`}
        aria-label={t("ausschreibung.ansicht_vorschau")}
      >
        <Blatt modell={modell} erstellt={erstellt} />
      </section>
    </form>
  );
}

function AutoVorschau({
  modellBausteine,
  id,
}: {
  modellBausteine: ReturnType<typeof druckModell>["bausteine"];
  id: string;
}) {
  const { t } = useTranslation("turnier");
  const eintrag = modellBausteine.find((b) => b.id === id);
  if (!eintrag) return <p className={t_s.hilfe}>{t("ausschreibung.keine_daten")}</p>;
  return <BausteinBlatt baustein={{ ...eintrag, ueberschrift: "", absaetze: [] }} />;
}
