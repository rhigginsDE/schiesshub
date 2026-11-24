import {
  Button,
  NumberInput,
  Radio,
  SegmentedControl,
  Select,
  Switch,
  Textarea,
  TextInput,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  ChevronRight,
  CopyPlus,
  History,
  Info,
  Lightbulb,
  RotateCcw,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { disziplinAbfrage } from "../../../api/abfragen";
import { Bestaetigung } from "../../../components/Bestaetigung";
import { Chip } from "../../../components/Chip";
import { GeldEingabe } from "../../../components/GeldEingabe";
import { formatDatum, formatUhrzeit, formatZahl } from "../../../lib/format";
import {
  revisionenAbfrage,
  useDefinitionZuruecksetzen,
  useWettbewerbAendern,
  useWettbewerbAnlegen,
} from "../abfragen";
import { Speicherleiste } from "../bereiche/Bausteine";
import { REGELN } from "../bereiche/Einstellungen";
import { fehlerText } from "../fehlertext";
import { planungBegruendung, planungVorschlag } from "../planung";
import { feldFehlerFuer } from "../senden";
import s from "../turnier.module.css";
import type { TurnierUebersicht, Wettbewerb, WettbewerbAnlage } from "../typen";
import { useEntwurf } from "../useEntwurf";
import {
  abweichungen,
  aenderungen,
  ausWettbewerb,
  bekannteFelder,
  erweiterteFelder,
  pruefeFormular,
  type WettbewerbFormular,
  wertungGeaendert,
} from "../wettbewerbFormular";
import { AblaufEditor } from "./AblaufEditor";
import { KatalogGeaendertHinweis } from "./KatalogStand";
import w from "./wettbewerbe.module.css";

interface WettbewerbBearbeitenProps {
  turnier: TurnierUebersicht;
  wettbewerb: Wettbewerb;
  gesperrt: boolean;
  /** Nach dem Kopieren: den neuen Wettbewerb aufklappen */
  onGeoeffnet: (id: string) => void;
}

/** Anlage eines eigenen Wettbewerbs als Kopie: gleiche Einstellungen, Definition ohne Herkunft. */
export function eigeneKopie(wettbewerb: Wettbewerb, name: string): WettbewerbAnlage {
  const { source: _herkunft, ...definition } = wettbewerb.definition;
  return {
    name,
    definition,
    range_id: wettbewerb.range_id,
    capture_mode: wettbewerb.capture_mode,
    multi_start: wettbewerb.multi_start,
    max_starts: wettbewerb.max_starts,
    multi_start_rule: wettbewerb.multi_start_rule,
    fee_first_cents: wettbewerb.fee_first_cents,
    fee_repeat_cents: wettbewerb.fee_repeat_cents,
    class_ids: wettbewerb.class_ids,
    combined_ranking: wettbewerb.combined_ranking,
    planning: wettbewerb.planning,
    heat_minutes: wettbewerb.heat_minutes,
    changeover_minutes: wettbewerb.changeover_minutes,
  };
}

type Rueckfrage =
  | { art: "speichern" }
  | { art: "zuruecksetzen"; variante?: string }
  | { art: "kopieren" }
  | null;

/** Hilfetexte unter dem Feld, damit Felder nebeneinander auf einer Höhe beginnen. */
const HILFE_UNTEN = ["label", "input", "description", "error"] as (
  | "label"
  | "input"
  | "description"
  | "error"
)[];

/**
 * Einstellungen eines Wettbewerbs. Oben, was fast jeder braucht (Stand, Startgeld, Mehrfachstart,
 * Klassen); Ablauf, Wertung, Erfassung und Planung liegen zugeklappt unter „Erweitert“ und sind
 * aus Katalog und Turnier-Einstellungen voreingestellt.
 */
export function WettbewerbBearbeiten({
  turnier,
  wettbewerb,
  gesperrt,
  onGeoeffnet,
}: WettbewerbBearbeitenProps) {
  const { t, i18n } = useTranslation("turnier");
  const sprache = i18n.language;
  const aendern = useWettbewerbAendern(turnier.id);
  const zuruecksetzen = useDefinitionZuruecksetzen(turnier.id);
  const anlegen = useWettbewerbAnlegen(turnier.id);
  const quelle = useMemo(() => ausWettbewerb(wettbewerb), [wettbewerb]);
  // Mit Speicherfunktion: Die Rückfrage beim Verlassen bietet auch „Speichern und weiter“ an.
  const entwurf = useEntwurf<WettbewerbFormular>(quelle, { speichern: speichernVomSchutz });
  const { werte } = entwurf;
  const [geprueft, setGeprueft] = useState(false);
  const [rueckfrage, setRueckfrage] = useState<Rueckfrage>(null);
  const [grund, setGrund] = useState("");
  const [kopieName, setKopieName] = useState("");
  const [erweitertOffen, setErweitertOffen] = useState(false);

  const ausKatalog = Boolean(wettbewerb.catalog_federation && wettbewerb.catalog_code);
  const katalog = useQuery({
    ...disziplinAbfrage(wettbewerb.catalog_federation ?? "", wettbewerb.catalog_code ?? ""),
    enabled: ausKatalog,
  });
  const varianten = katalog.data?.ablauf.varianten ?? [];
  const katalogVariante = varianten.find((v) => v.id === wettbewerb.definition.variant.id);
  const abw = abweichungen(werte.abschnitte, katalogVariante);
  const entwurfsStatus = turnier.status === "draft";
  // Frühere Einstellungen gibt es erst, wenn das Turnier läuft; im Entwurf wären sie nur Rauschen.
  const revisionen = useQuery({
    ...revisionenAbfrage(turnier.id, wettbewerb.id),
    enabled: !entwurfsStatus,
  });

  const aktiv = turnier.status === "active";
  const waehrung = turnier.settings.currency;
  const vorschlag = planungVorschlag(
    { ...wettbewerb.definition.variant, abschnitte: werte.abschnitte },
    werte.changeover_minutes,
  );
  const vorschlagWeicht =
    vorschlag.planung !== werte.planning ||
    (vorschlag.planung === "schedule" && vorschlag.durchgangMinuten !== werte.heat_minutes);

  const eigene = geprueft ? pruefeFormular(werte) : {};
  const serverFehler = aendern.isError ? feldFehlerFuer(aendern.error, bekannteFelder(werte)) : {};
  const fehler: Record<string, string> = { ...serverFehler, ...eigene };
  const setze = (neu: Partial<WettbewerbFormular>) => {
    entwurf.setWerte({ ...werte, ...neu });
    if (aendern.isError) aendern.reset();
  };

  // Welche Felder liegen unter „Erweitert“? Fehler dort klappen den Abschnitt auf.
  const imErweitert = erweiterteFelder(ausKatalog);
  const fehlerErweitert = Object.keys(fehler).some(imErweitert);
  const geaendertErweitert = Object.keys(aenderungen(werte, wettbewerb)).some(imErweitert);
  const erweitertSichtbar = erweitertOffen || fehlerErweitert;
  const erweitertId = `erweitert-${wettbewerb.id}`;

  /**
   * Speichert und gibt `true` zurück, wenn der Server angenommen hat. Danach gilt der Entwurf als
   * gespeichert: Er übernimmt den Stand aus der Antwort (der Server leitet z. B. Planung und
   * Durchgangsdauer selbst ab), sonst bliebe er „geändert“ und das Verlassen fragte nach (QA G-4).
   */
  const speichern = async (mitGrund?: string): Promise<boolean> => {
    const daten = { ...aenderungen(werte, wettbewerb), ...(mitGrund ? { reason: mitGrund } : {}) };
    try {
      const neu = await aendern.mutateAsync({ wettbewerbId: wettbewerb.id, daten });
      entwurf.setWerte(ausWettbewerb(neu));
      return true;
    } catch {
      return false;
    } finally {
      setRueckfrage(null);
    }
  };

  /** „Speichern und weiter“ aus der Rückfrage beim Verlassen. */
  async function speichernVomSchutz(): Promise<boolean> {
    setGeprueft(true);
    if (Object.keys(pruefeFormular(werte)).length > 0) return false;
    if (aktiv && wertungGeaendert(werte, wettbewerb)) {
      // Ohne Grund kein Speichern: die Frage nach dem Grund öffnen, die Seite bleibt offen.
      setGrund("");
      setRueckfrage({ art: "speichern" });
      return false;
    }
    return speichern();
  }

  const zuruecksetzenFragen = () => {
    setGrund("");
    zuruecksetzen.reset();
    setRueckfrage({ art: "zuruecksetzen" });
  };

  const klassenIds = new Set(werte.class_ids);
  const nameFeld = (
    <TextInput
      label={t("wettbewerb.name")}
      description={ausKatalog ? t("wettbewerb.name_hilfe") : undefined}
      inputWrapperOrder={HILFE_UNTEN}
      size="md"
      value={werte.name}
      error={fehler.name}
      onChange={(e) => setze({ name: e.currentTarget.value })}
    />
  );

  return (
    <form
      className={s.wettbewerbFormular}
      noValidate
      onSubmit={(ereignis) => {
        ereignis.preventDefault();
        setGeprueft(true);
        if (Object.keys(pruefeFormular(werte)).length > 0) return;
        if (aktiv && wertungGeaendert(werte, wettbewerb)) {
          setGrund("");
          setRueckfrage({ art: "speichern" });
          return;
        }
        void speichern();
      }}
    >
      {/* Der Katalog hat sich seit der Übernahme geändert: Stand damals → heute, übernehmen */}
      <KatalogGeaendertHinweis
        turnierId={turnier.id}
        wettbewerb={wettbewerb}
        gesperrt={gesperrt}
        onUebernehmen={zuruecksetzenFragen}
      />

      {/* Das, was fast jeder Wettbewerb braucht */}
      <fieldset className={s.ohneRahmen} disabled={gesperrt}>
        <div className={s.feldGruppe}>
          <span className="h-label">{t("wettbewerb.gruppe.grundlagen")}</span>
          {!ausKatalog && nameFeld}
          <div className={s.zweiSpalten}>
            <Select
              label={t("wettbewerb.stand")}
              size="md"
              clearable
              placeholder={t("wettbewerb.kein_stand")}
              data={turnier.ranges.map((stand) => ({
                value: stand.id,
                label: t("wettbewerb.stand_option", {
                  name: stand.name,
                  count: stand.lane_count,
                }),
              }))}
              value={werte.range_id}
              description={werte.range_id ? undefined : t("wettbewerb.stand_fehlt")}
              inputWrapperOrder={HILFE_UNTEN}
              error={fehler.range_id}
              onChange={(wert) => setze({ range_id: wert })}
            />
            <GeldEingabe
              label={t("feld.startgeld")}
              size="md"
              waehrung={waehrung}
              meldungUnlesbar={t("pruefung.betrag_format")}
              wert={werte.fee_first_cents}
              error={fehler.fee_first_cents}
              onWert={(cent) => setze({ fee_first_cents: cent })}
            />
          </div>
          <Switch
            size="md"
            label={t("wettbewerb.mehrfach")}
            description={t("wettbewerb.mehrfach_hilfe")}
            checked={werte.multi_start}
            onChange={(e) => {
              const an = e.currentTarget.checked;
              setze({
                multi_start: an,
                max_starts: an ? Math.max(2, werte.max_starts) : 1,
                fee_repeat_cents: werte.fee_repeat_cents ?? werte.fee_first_cents,
              });
            }}
          />
          {werte.multi_start && (
            <div className={s.zweiSpalten}>
              <NumberInput
                label={t("feld.max_starts")}
                size="md"
                min={2}
                max={99}
                allowDecimal={false}
                value={werte.max_starts}
                error={fehler.max_starts}
                onChange={(wert) =>
                  setze({ max_starts: typeof wert === "number" ? wert : Number.NaN })
                }
              />
              <GeldEingabe
                label={t("feld.nachkauf")}
                size="md"
                waehrung={waehrung}
                meldungUnlesbar={t("pruefung.betrag_format")}
                wert={werte.fee_repeat_cents}
                error={fehler.fee_repeat_cents}
                onWert={(cent) => setze({ fee_repeat_cents: cent })}
              />
            </div>
          )}
        </div>

        <div className={s.feldGruppe}>
          <span className="h-label" id={`klassen-${wettbewerb.id}`}>
            {t("wettbewerb.gruppe.klassen")}
          </span>
          {turnier.classes.length === 0 ? (
            <p className={s.hilfe}>{t("wettbewerb.keine_klassen")}</p>
          ) : (
            <>
              <fieldset className={s.wahlReihe} aria-labelledby={`klassen-${wettbewerb.id}`}>
                {turnier.classes.map((klasse) => (
                  <button
                    key={klasse.id}
                    type="button"
                    className={`${s.wahlchip} ${w.chip}`}
                    aria-pressed={klassenIds.has(klasse.id)}
                    title={klasse.name}
                    onClick={() =>
                      setze({
                        class_ids: klassenIds.has(klasse.id)
                          ? werte.class_ids.filter((id) => id !== klasse.id)
                          : turnier.classes
                              .map((k) => k.id)
                              .filter((id) => id === klasse.id || klassenIds.has(id)),
                      })
                    }
                  >
                    {klasse.short}
                  </button>
                ))}
              </fieldset>
              <p className={s.hilfe}>
                {werte.class_ids.length === 0
                  ? t("wettbewerb.klassen_alle")
                  : t("wettbewerb.klassen_gewaehlt", { count: werte.class_ids.length })}
              </p>
            </>
          )}
          {fehler.class_ids && (
            <p className={s.fehlerText} role="alert">
              {fehler.class_ids}
            </p>
          )}
        </div>
      </fieldset>

      {/* Erweitert: zugeklappt, voreingestellt aus Katalog und Turnier */}
      <section className={w.erweitert} data-offen={erweitertSichtbar || undefined}>
        <button
          type="button"
          className={w.erweitertKopf}
          aria-expanded={erweitertSichtbar}
          aria-controls={erweitertId}
          onClick={() => setErweitertOffen(!erweitertSichtbar)}
        >
          {erweitertSichtbar ? <ChevronDown aria-hidden /> : <ChevronRight aria-hidden />}
          <span className={w.erweitertText}>
            <strong>{t("wettbewerb.erweitert.titel")}</strong>
            <span>{t("wettbewerb.erweitert.text")}</span>
          </span>
          <span className={w.erweitertMarken}>
            {abw && abw.length > 0 && (
              <Chip ton="info">{t("wettbewerb.abweichungen", { count: abw.length })}</Chip>
            )}
            {geaendertErweitert && (
              <Chip ton="warn">{t("wettbewerb.erweitert.ungespeichert")}</Chip>
            )}
          </span>
        </button>

        {erweitertSichtbar && (
          <div id={erweitertId} className={w.erweitertInhalt}>
            <fieldset className={s.ohneRahmen} disabled={gesperrt}>
              {/* Name und Wertung */}
              <div className={s.feldGruppe}>
                <span className="h-label">{t("wettbewerb.gruppe.wertung")}</span>
                {ausKatalog && nameFeld}
                {ausKatalog && varianten.length > 1 && (
                  <Select
                    label={t("wettbewerb.variante")}
                    description={t("wettbewerb.variante_hilfe")}
                    inputWrapperOrder={HILFE_UNTEN}
                    size="md"
                    allowDeselect={false}
                    data={varianten.map((v) => ({ value: v.id, label: v.name }))}
                    value={wettbewerb.definition.variant.id}
                    onChange={(wert) => {
                      if (!wert || wert === wettbewerb.definition.variant.id) return;
                      setGrund("");
                      zuruecksetzen.reset();
                      setRueckfrage({ art: "zuruecksetzen", variante: wert });
                    }}
                  />
                )}
                {werte.multi_start && (
                  <Select
                    label={t("feld.regel")}
                    size="md"
                    className={w.schmal}
                    allowDeselect={false}
                    data={REGELN.map((regel) => ({ value: regel, label: t(`regel.${regel}`) }))}
                    value={werte.multi_start_rule}
                    error={fehler.multi_start_rule}
                    onChange={(wert) =>
                      wert &&
                      setze({ multi_start_rule: wert as WettbewerbFormular["multi_start_rule"] })
                    }
                  />
                )}
                <Switch
                  size="md"
                  label={t("wettbewerb.gemeinsam")}
                  description={t("wettbewerb.gemeinsam_hilfe")}
                  checked={werte.combined_ranking}
                  onChange={(e) => setze({ combined_ranking: e.currentTarget.checked })}
                />
                <div className={s.feldGruppe}>
                  <span className={s.feldLabel} id={`erfassung-${wettbewerb.id}`}>
                    {t("feld.erfassung")}
                  </span>
                  <SegmentedControl
                    aria-labelledby={`erfassung-${wettbewerb.id}`}
                    size="md"
                    className={s.segmente}
                    value={werte.capture_mode}
                    onChange={(wert) =>
                      setze({ capture_mode: wert as WettbewerbFormular["capture_mode"] })
                    }
                    data={[
                      { value: "series", label: t("erfassung.series") },
                      { value: "shot", label: t("erfassung.shot") },
                    ]}
                  />
                  <p className={s.hilfe}>{t(`erfassung.${werte.capture_mode}_hilfe`)}</p>
                </div>
              </div>

              {/* Planung am Stand */}
              <div className={s.feldGruppe}>
                <span className="h-label" id={`planung-${wettbewerb.id}`}>
                  {t("wettbewerb.gruppe.planung")}
                </span>
                <Radio.Group
                  aria-labelledby={`planung-${wettbewerb.id}`}
                  value={werte.planning}
                  onChange={(wert) => {
                    const planning = wert as WettbewerbFormular["planning"];
                    setze({
                      planning,
                      heat_minutes:
                        planning === "schedule" && !werte.heat_minutes
                          ? (vorschlag.durchgangMinuten ?? null)
                          : werte.heat_minutes,
                    });
                  }}
                >
                  <div className={w.planungWahl}>
                    {(["queue", "schedule"] as const).map((art) => (
                      <Radio
                        key={art}
                        value={art}
                        size="md"
                        className={w.planungKarte}
                        label={t(`planung.${art}`)}
                        description={t(`planung.${art}_hilfe`)}
                      />
                    ))}
                  </div>
                </Radio.Group>
                {vorschlagWeicht && (
                  <div className={`inset ${s.vorschlag}`}>
                    <Lightbulb aria-hidden className={s.vorschlagSymbol} />
                    <div>
                      <strong>
                        {vorschlag.planung === "schedule"
                          ? t("planung.vorschlag_zeitplan", {
                              minuten: formatZahl(vorschlag.durchgangMinuten ?? 0, {}, sprache),
                            })
                          : t("planung.vorschlag_reihenfolge")}
                      </strong>
                      <p>{planungBegruendung(vorschlag, werte.changeover_minutes, sprache)}</p>
                    </div>
                    <Button
                      variant="default"
                      onClick={() =>
                        setze({
                          planning: vorschlag.planung,
                          heat_minutes:
                            vorschlag.planung === "schedule"
                              ? vorschlag.durchgangMinuten
                              : werte.heat_minutes,
                        })
                      }
                    >
                      {t("planung.uebernehmen")}
                    </Button>
                  </div>
                )}
                {werte.planning === "schedule" && (
                  <div className={s.zweiSpalten}>
                    <NumberInput
                      label={t("planung.durchgang")}
                      description={t("planung.durchgang_hilfe")}
                      inputWrapperOrder={HILFE_UNTEN}
                      size="md"
                      min={1}
                      allowDecimal={false}
                      suffix={` ${t("einheit.min")}`}
                      value={werte.heat_minutes ?? ""}
                      error={fehler.heat_minutes}
                      onChange={(wert) =>
                        setze({ heat_minutes: typeof wert === "number" ? wert : null })
                      }
                    />
                    <NumberInput
                      label={t("feld.wechselzeit")}
                      description={t("feld.wechselzeit_hilfe")}
                      inputWrapperOrder={HILFE_UNTEN}
                      size="md"
                      min={0}
                      allowDecimal={false}
                      suffix={` ${t("einheit.min")}`}
                      value={werte.changeover_minutes}
                      error={fehler.changeover_minutes}
                      onChange={(wert) =>
                        setze({ changeover_minutes: typeof wert === "number" ? wert : Number.NaN })
                      }
                    />
                  </div>
                )}
              </div>

              {/* Ablauf */}
              <div className={s.feldGruppe}>
                <span className="h-label">{t("wettbewerb.gruppe.ablauf")}</span>
                <p className={s.hilfe}>
                  {ausKatalog ? t("wettbewerb.ablauf_zweck") : t("wettbewerb.ablauf_zweck_eigen")}
                </p>
                {abw !== null && (
                  <div className={w.ablaufStatus}>
                    {abw.length === 0 ? (
                      <span className={w.wieKatalog}>
                        <Check aria-hidden />
                        {t("wettbewerb.wie_katalog")}
                      </span>
                    ) : (
                      <Chip ton="info">{t("wettbewerb.abweichungen", { count: abw.length })}</Chip>
                    )}
                    <Button
                      variant="default"
                      leftSection={<RotateCcw aria-hidden />}
                      disabled={gesperrt || (abw.length === 0 && !wettbewerb.catalog_changed)}
                      onClick={zuruecksetzenFragen}
                    >
                      {t("wettbewerb.zuruecksetzen")}
                    </Button>
                  </div>
                )}
                {aktiv && <p className={s.hilfe}>{t("wettbewerb.ablauf_aktiv_hinweis")}</p>}
                <AblaufEditor
                  abschnitte={werte.abschnitte}
                  original={wettbewerb.definition.variant.abschnitte}
                  katalog={katalogVariante}
                  fehler={fehler}
                  gesperrt={gesperrt}
                  onAendern={(abschnitte) => setze({ abschnitte })}
                />
              </div>
            </fieldset>

            {/* Herkunft */}
            <div className={s.herkunft}>
              <span>
                <Info aria-hidden />
                {wettbewerb.definition.source
                  ? t("wettbewerb.herkunft_katalog", {
                      verband: wettbewerb.definition.source.federation.toUpperCase(),
                      kennziffer: wettbewerb.definition.source.code,
                      stand: formatDatum(wettbewerb.definition.source.catalog_stand, sprache),
                    })
                  : t("wettbewerb.herkunft_eigen")}
              </span>
              <Button
                variant="subtle"
                color="gray"
                leftSection={<CopyPlus aria-hidden />}
                disabled={gesperrt}
                onClick={() => {
                  setKopieName(t("wettbewerb.kopie_name", { name: wettbewerb.name }));
                  anlegen.reset();
                  setRueckfrage({ art: "kopieren" });
                }}
              >
                {t("wettbewerb.kopieren")}
              </Button>
            </div>

            {!entwurfsStatus && revisionen.data && revisionen.data.length > 1 && (
              <details className={s.verlauf}>
                <summary>
                  <History aria-hidden />
                  {t("wettbewerb.verlauf", { count: revisionen.data.length - 1 })}
                </summary>
                <ol>
                  {[...revisionen.data].reverse().map((revision) => (
                    <li key={revision.revision}>
                      <span className="num">
                        {t("wettbewerb.revision", { nr: revision.revision })} ·{" "}
                        {formatDatum(revision.created_at, sprache)}{" "}
                        {formatUhrzeit(new Date(revision.created_at), sprache)}
                      </span>
                      <span>{revision.reason ?? t("wettbewerb.revision_ohne_grund")}</span>
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </div>
        )}
      </section>

      {/* Feste Knopfleiste: bleibt am unteren Rand sichtbar, solange der Wettbewerb offen ist */}
      <div className={w.fussLeiste}>
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
      </div>

      {/* Rückfragen */}
      <Bestaetigung
        offen={rueckfrage?.art === "speichern"}
        titel={t("wettbewerb.grund_titel")}
        text={<p>{t("wettbewerb.grund_text")}</p>}
        bestaetigen={t("wettbewerb.grund_knopf")}
        abbrechen={t("aktion.abbrechen")}
        laedt={aendern.isPending}
        gesperrt={grund.trim().length === 0}
        onSchliessen={() => setRueckfrage(null)}
        onBestaetigen={() => void speichern(grund.trim())}
      >
        <Textarea
          label={t("wettbewerb.grund")}
          placeholder={t("wettbewerb.grund_platzhalter")}
          required
          autosize
          minRows={2}
          data-autofocus
          value={grund}
          onChange={(e) => setGrund(e.currentTarget.value)}
        />
      </Bestaetigung>

      <Bestaetigung
        offen={rueckfrage?.art === "zuruecksetzen"}
        titel={
          rueckfrage?.art === "zuruecksetzen" && rueckfrage.variante
            ? t("wettbewerb.variante_titel", {
                name: varianten.find((v) => v.id === rueckfrage.variante)?.name ?? "",
              })
            : wettbewerb.catalog_changed
              ? t("katalog_stand.uebernehmen_titel")
              : t("wettbewerb.zuruecksetzen_titel")
        }
        text={
          <>
            <p>{t("wettbewerb.zuruecksetzen_text")}</p>
            {aktiv && <p>{t("wettbewerb.grund_text")}</p>}
          </>
        }
        bestaetigen={t("wettbewerb.zuruecksetzen_knopf")}
        abbrechen={t("aktion.abbrechen")}
        laedt={zuruecksetzen.isPending}
        gesperrt={aktiv && grund.trim().length === 0}
        fehler={zuruecksetzen.isError ? fehlerText(zuruecksetzen.error) : undefined}
        onSchliessen={() => setRueckfrage(null)}
        onBestaetigen={() =>
          zuruecksetzen.mutate(
            {
              wettbewerbId: wettbewerb.id,
              variante: rueckfrage?.art === "zuruecksetzen" ? rueckfrage.variante : undefined,
              grund: aktiv ? grund.trim() : undefined,
            },
            {
              onSuccess: () => {
                setRueckfrage(null);
                entwurf.verwerfen();
              },
            },
          )
        }
      >
        {aktiv && (
          <Textarea
            label={t("wettbewerb.grund")}
            placeholder={t("wettbewerb.grund_platzhalter")}
            required
            autosize
            minRows={2}
            value={grund}
            onChange={(e) => setGrund(e.currentTarget.value)}
          />
        )}
      </Bestaetigung>

      <Bestaetigung
        offen={rueckfrage?.art === "kopieren"}
        titel={t("wettbewerb.kopieren_titel")}
        text={<p>{t("wettbewerb.kopieren_text")}</p>}
        bestaetigen={t("wettbewerb.kopieren_knopf")}
        abbrechen={t("aktion.abbrechen")}
        laedt={anlegen.isPending}
        gesperrt={kopieName.trim().length === 0}
        fehler={anlegen.isError ? fehlerText(anlegen.error) : undefined}
        onSchliessen={() => setRueckfrage(null)}
        onBestaetigen={() =>
          anlegen.mutate(eigeneKopie(wettbewerb, kopieName.trim()), {
            onSuccess: (neu) => {
              setRueckfrage(null);
              onGeoeffnet(neu.id);
            },
          })
        }
      >
        <TextInput
          label={t("wettbewerb.name")}
          data-autofocus
          value={kopieName}
          onChange={(e) => setKopieName(e.currentTarget.value)}
        />
      </Bestaetigung>
    </form>
  );
}
