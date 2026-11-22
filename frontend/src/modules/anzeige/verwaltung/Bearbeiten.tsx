import {
  ActionIcon,
  Button,
  CopyButton,
  SegmentedControl,
  Select,
  Switch,
  Textarea,
  Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, ExternalLink, Info, Save, TriangleAlert, Undo2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { geraeteAbfrage } from "../../../api/abfragen";
import { ApiFehler, type FeldFehler } from "../../../api/client";
import { Chip } from "../../../components/Chip";
import { ExportKnoepfe } from "../../../components/ExportKnoepfe";
import { useFehlerText } from "../../../components/FehlerHinweis";
import { zeigeMeldung } from "../../../components/Meldungen";
import { bestimmeTurnier } from "../../../components/useAktivesTurnier";
import { uebersichtAbfrage } from "../../turnier/abfragen";
import type { Turnier } from "../../turnier/typen";
import {
  anzeigeAendern,
  anzeigeSchluessel,
  geraetLoesen,
  geraetZuweisen,
  schirmPfad,
  vorschauFeed,
} from "../api";
import { SchirmAnsicht } from "../schirm/Schirm";
import { useFeed } from "../schirm/useFeed";
import type { Anzeige, AnzeigeKonfig, Feed } from "../typen";
import {
  type Entwurf,
  entwurfAus,
  fehlerZu,
  gleicherEntwurf,
  speicherSchritte,
  uebrigeFehler,
  vorschauAnfrage,
} from "./entwurf";
import { SzenenEditor, szenenUnvollstaendig } from "./SzenenEditor";
import s from "./verwaltung.module.css";

const AUTO = "auto";
const FEST = "fest";
const OHNE_GERAET = "";

interface BearbeitenProps {
  anzeige: Anzeige;
  anzeigen: Anzeige[];
  turniere: Turnier[];
  onGeaendert: (geaendert: boolean) => void;
}

/** Felder, die das Formular selbst kennt; alles andere erscheint als Liste über dem Formular. */
function bekanntesFeld(feld: string): boolean {
  return (
    feld === "tournament_id" ||
    feld === "device_id" ||
    feld.startsWith("scenes.") ||
    ["name_mode", "show_club", "ticker", "show_backup_warning", "theme"].includes(feld)
  );
}

/** Mitte: Einstellungen der gewählten Anzeige; rechts: Live-Vorschau. Speichern per Knopf. */
export function Bearbeiten({ anzeige, anzeigen, turniere, onGeaendert }: BearbeitenProps) {
  const { t } = useTranslation("anzeige");
  const queryClient = useQueryClient();
  const fehlerText = useFehlerText();
  const server = useMemo(() => entwurfAus(anzeige), [anzeige]);
  const [entwurf, setEntwurf] = useState<Entwurf>(server);
  const geaendert = !gleicherEntwurf(entwurf, server);

  // Neuer Stand vom Server (z. B. von einem anderen Gerät): übernehmen, solange nichts offen ist.
  const [basis, setBasis] = useState(server);
  if (basis !== server) {
    setBasis(server);
    if (gleicherEntwurf(entwurf, basis)) setEntwurf(server);
  }

  useEffect(() => onGeaendert(geaendert), [geaendert, onGeaendert]);
  useEffect(() => {
    if (!geaendert) return;
    const warnen = (ereignis: BeforeUnloadEvent) => ereignis.preventDefault();
    window.addEventListener("beforeunload", warnen);
    return () => window.removeEventListener("beforeunload", warnen);
  }, [geaendert]);

  const optionenTurnier =
    entwurf.tournament_id ?? bestimmeTurnier(turniere, null).turnier?.id ?? null;
  const uebersicht = useQuery({
    ...uebersichtAbfrage(optionenTurnier ?? ""),
    enabled: optionenTurnier !== null,
  });

  const speichern = useMutation({
    mutationFn: async () => {
      for (const schritt of speicherSchritte(server, entwurf)) {
        if (schritt.art === "anzeige") {
          await anzeigeAendern(anzeige.id, schritt.aenderung);
        } else if (schritt.wert === null) {
          await geraetLoesen(anzeige.id);
        } else {
          await geraetZuweisen(anzeige.id, schritt.wert);
        }
      }
    },
    onSuccess: () => zeigeMeldung({ ton: "erfolg", titel: t("bearbeiten.gespeichert") }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: anzeigeSchluessel.alle }),
  });

  const felder: readonly FeldFehler[] =
    speichern.error instanceof ApiFehler ? speichern.error.felder : [];
  const allgemein = speichern.error
    ? felder.length > 0
      ? [t("bearbeiten.felder_pruefen"), ...uebrigeFehler(felder, bekanntesFeld)]
      : [fehlerText(speichern.error)]
    : [];
  const konfig = entwurf.konfig;
  const setzeKonfig = (aenderung: Partial<AnzeigeKonfig>) =>
    setEntwurf((alt) => ({ ...alt, konfig: { ...alt.konfig, ...aenderung } }));
  const unvollstaendig = szenenUnvollstaendig(konfig.scenes ?? []);

  return (
    <>
      <div className={s.spalte}>
        <section className={`panel ${s.leiste}`} aria-label={t("bearbeiten.leiste")}>
          <div className={s.leisteTitel}>
            <h2 className="h-section">{anzeige.name}</h2>
            {geaendert && <Chip ton="warn">{t("bearbeiten.ungespeichert")}</Chip>}
          </div>
          <div className={s.leisteAktionen}>
            <Button
              variant="default"
              leftSection={<Undo2 aria-hidden />}
              disabled={!geaendert || speichern.isPending}
              onClick={() => {
                speichern.reset();
                setEntwurf(server);
              }}
            >
              {t("bearbeiten.verwerfen")}
            </Button>
            <Button
              leftSection={<Save aria-hidden />}
              disabled={!geaendert || unvollstaendig}
              loading={speichern.isPending}
              onClick={() => speichern.mutate()}
            >
              {t("aktion.speichern")}
            </Button>
          </div>
        </section>

        {allgemein.length > 0 && (
          <div className={s.fehlerListe} role="alert">
            <strong>{t("bearbeiten.fehler_titel")}</strong>
            {allgemein.map((text) => (
              <span key={text}>{text}</span>
            ))}
          </div>
        )}

        <TurnierUndGeraet
          entwurf={entwurf}
          anzeige={anzeige}
          anzeigen={anzeigen}
          turniere={turniere}
          automatischName={
            entwurf.tournament_id === null
              ? (bestimmeTurnier(turniere, null).turnier?.name ?? null)
              : null
          }
          felder={felder}
          onAendern={(aenderung) => setEntwurf((alt) => ({ ...alt, ...aenderung }))}
        />

        <SzenenEditor
          szenen={konfig.scenes ?? []}
          uebersicht={uebersicht.data}
          felder={felder}
          onAendern={(szenen) => setzeKonfig({ scenes: szenen })}
        />

        <section className={`panel ${s.feldgruppe}`} aria-labelledby="darstellung-titel">
          <h3 className="h-section" id="darstellung-titel">
            {t("darstellung.titel")}
          </h3>
          <div className={s.zweispaltig}>
            <Select
              label={t("darstellung.namen")}
              description={t("darstellung.namen_hilfe")}
              data={[
                { value: "as_person", label: t("darstellung.namen_person") },
                { value: "short", label: t("darstellung.namen_kurz") },
              ]}
              value={konfig.name_mode}
              allowDeselect={false}
              onChange={(wert) =>
                wert && setzeKonfig({ name_mode: wert as AnzeigeKonfig["name_mode"] })
              }
              error={fehlerZu(felder, "name_mode")}
            />
            <Select
              label={t("darstellung.verein")}
              data={[
                { value: "as_person", label: t("darstellung.verein_person") },
                { value: "nie", label: t("darstellung.verein_nie") },
              ]}
              value={konfig.show_club === false ? "nie" : "as_person"}
              allowDeselect={false}
              onChange={(wert) => setzeKonfig({ show_club: wert === "nie" ? false : "as_person" })}
              error={fehlerZu(felder, "show_club")}
            />
            <div>
              <span className="h-label">{t("darstellung.thema")}</span>
              <SegmentedControl
                fullWidth
                mt={6}
                value={konfig.theme}
                onChange={(wert) => setzeKonfig({ theme: wert as AnzeigeKonfig["theme"] })}
                data={[
                  { value: "dark", label: t("darstellung.dunkel") },
                  { value: "light", label: t("darstellung.hell") },
                ]}
              />
            </div>
            <Select
              label={t("darstellung.sicherung")}
              description={t("darstellung.sicherung_hilfe")}
              data={[
                { value: "standard", label: t("darstellung.sicherung_standard") },
                { value: "ja", label: t("darstellung.sicherung_ja") },
                { value: "nein", label: t("darstellung.sicherung_nein") },
              ]}
              value={
                konfig.show_backup_warning == null
                  ? "standard"
                  : konfig.show_backup_warning
                    ? "ja"
                    : "nein"
              }
              allowDeselect={false}
              onChange={(wert) =>
                setzeKonfig({
                  show_backup_warning: wert === "standard" ? null : wert === "ja",
                })
              }
              error={fehlerZu(felder, "show_backup_warning")}
            />
          </div>
          <Switch
            label={t("darstellung.vorlaeufig")}
            description={t("darstellung.vorlaeufig_hilfe")}
            checked={konfig.show_provisional_note}
            onChange={(e) => setzeKonfig({ show_provisional_note: e.currentTarget.checked })}
          />
          <Textarea
            label={t("darstellung.laufzeile")}
            description={t("darstellung.laufzeile_hilfe")}
            value={konfig.ticker ?? ""}
            maxLength={500}
            autosize
            minRows={1}
            maxRows={4}
            onChange={(e) => setzeKonfig({ ticker: e.currentTarget.value || null })}
            error={fehlerZu(felder, "ticker")}
          />
        </section>
      </div>
      <div className={s.spalte}>
        <Vorschau
          anzeige={anzeige}
          entwurf={entwurf}
          geaendert={geaendert}
          unvollstaendig={unvollstaendig}
        />
        {optionenTurnier && (
          <ExportKnoepfe
            turnierId={optionenTurnier}
            uebersicht={uebersicht.data}
            darstellung="abschnitt"
          />
        )}
      </div>
    </>
  );
}

function TurnierUndGeraet({
  entwurf,
  anzeige,
  anzeigen,
  turniere,
  automatischName,
  felder,
  onAendern,
}: {
  entwurf: Entwurf;
  anzeige: Anzeige;
  anzeigen: Anzeige[];
  turniere: Turnier[];
  automatischName: string | null;
  felder: readonly FeldFehler[];
  onAendern: (aenderung: Partial<Entwurf>) => void;
}) {
  const { t } = useTranslation("anzeige");
  const fehlerText = useFehlerText();
  const geraete = useQuery(geraeteAbfrage());
  const [modus, setModus] = useState(entwurf.tournament_id ? FEST : AUTO);
  const fest = modus === FEST;

  const geraeteDaten = [
    { value: OHNE_GERAET, label: t("geraet.keins") },
    ...(geraete.data ?? []).map((geraet) => {
      const andere = anzeigen.find((a) => a.device_id === geraet.id && a.id !== anzeige.id);
      const zusatz = geraet.blocked
        ? t("geraet.gesperrt")
        : andere
          ? t("geraet.zeigt", { name: andere.name })
          : null;
      return {
        value: geraet.id,
        label: zusatz ? `${geraet.name} (${zusatz})` : geraet.name,
        disabled: geraet.blocked || Boolean(andere),
      };
    }),
  ];
  // Ein zugewiesenes Gerät, das die Liste nicht (mehr) kennt, bleibt wählbar sichtbar.
  if (entwurf.device_id && !geraeteDaten.some((g) => g.value === entwurf.device_id)) {
    geraeteDaten.push({ value: entwurf.device_id, label: t("geraet.unbekannt"), disabled: false });
  }

  return (
    <section className={`panel ${s.feldgruppe}`} aria-labelledby="turnier-titel">
      <h3 className="h-section" id="turnier-titel">
        {t("turnier.titel")}
      </h3>
      <SegmentedControl
        value={modus}
        onChange={(wert) => {
          setModus(wert);
          if (wert === AUTO) onAendern({ tournament_id: null });
        }}
        data={[
          { value: AUTO, label: t("turnier.auto") },
          { value: FEST, label: t("turnier.fest") },
        ]}
      />
      {fest ? (
        <Select
          label={t("turnier.wahl")}
          placeholder={t("turnier.wahl_platzhalter")}
          data={turniere.map((turnier) => ({ value: turnier.id, label: turnier.name }))}
          value={entwurf.tournament_id}
          onChange={(wert) => onAendern({ tournament_id: wert })}
          searchable
          allowDeselect={false}
          error={
            fehlerZu(felder, "tournament_id") ??
            (!entwurf.tournament_id ? t("turnier.wahl_fehlt") : undefined)
          }
        />
      ) : automatischName ? (
        <p className={s.hilfe}>{t("turnier.auto_hilfe", { name: automatischName })}</p>
      ) : (
        <p className={s.warnHinweis} role="alert">
          <TriangleAlert aria-hidden />
          {t("turnier.auto_keins")}
        </p>
      )}

      <h3 className="h-section">{t("geraet.titel")}</h3>
      <Select
        label={t("geraet.wahl")}
        description={t("geraet.hilfe")}
        data={geraeteDaten}
        value={entwurf.device_id ?? OHNE_GERAET}
        allowDeselect={false}
        disabled={geraete.isError}
        onChange={(wert) => onAendern({ device_id: wert ? wert : null })}
        error={
          fehlerZu(felder, "device_id") ??
          (geraete.isError
            ? t("geraet.liste_fehler", { grund: fehlerText(geraete.error) })
            : undefined)
        }
      />
      {entwurf.device_id && (
        <div>
          <Button variant="default" onClick={() => onAendern({ device_id: null })}>
            {t("geraet.loesen")}
          </Button>
        </div>
      )}
    </section>
  );
}

function Adresse({ pfad, label }: { pfad: string; label: string }) {
  const { t } = useTranslation("anzeige");
  const adresse = `${window.location.origin}${pfad}`;
  return (
    <div>
      <span className="h-label">{label}</span>
      <div className={s.adresse} style={{ marginTop: 6 }}>
        <code>{adresse}</code>
        <CopyButton value={adresse}>
          {({ copied, copy }) => (
            <Tooltip label={copied ? t("vorschau.kopiert") : t("vorschau.kopieren")}>
              <ActionIcon
                variant="subtle"
                color="gray"
                size={36}
                aria-label={t("vorschau.kopieren")}
                onClick={copy}
              >
                {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
              </ActionIcon>
            </Tooltip>
          )}
        </CopyButton>
      </div>
    </div>
  );
}

/** Wartezeit nach der letzten Änderung, bevor die Vorschau den Entwurf beim Server anfragt. */
const VORSCHAU_ENTPRELLEN_MS = 400;

/**
 * Feed für den nicht gespeicherten Entwurf (`POST …/preview-feed`), entprellt. Lädt neu, wenn sich
 * der gespeicherte Feed ändert (neue Ergebnisse). `null`, solange nichts offen ist, der Entwurf
 * unvollständig ist oder der Server ihn ablehnt; dann zeigt die Vorschau den gespeicherten Stand.
 */
function useEntwurfsFeed(
  anzeigeId: string,
  entwurf: Entwurf,
  aktiv: boolean,
  version: string | undefined,
): { feed: Feed | null; fehler: unknown } {
  const anfrage = aktiv ? JSON.stringify(vorschauAnfrage(entwurf)) : null;
  const [ruhig] = useDebouncedValue(anfrage, VORSCHAU_ENTPRELLEN_MS);
  const abfrage = useQuery({
    queryKey: [...anzeigeSchluessel.vorschau(anzeigeId), ruhig, version],
    queryFn: ({ signal }) => vorschauFeed(anzeigeId, JSON.parse(ruhig ?? "{}"), signal),
    enabled: aktiv && ruhig !== null,
    placeholderData: keepPreviousData,
    retry: false,
  });
  if (!aktiv || abfrage.isError) return { feed: null, fehler: abfrage.error };
  return { feed: abfrage.data ?? null, fehler: null };
}

/**
 * Rechts: dieselbe Bildschirm-Komponente verkleinert im 16:9-Rahmen, dazu Adresse und Knopf.
 * Mit offenen Änderungen zeigt sie den Entwurf (noch nicht gespeichert), sonst den Bildschirm.
 */
function Vorschau({
  anzeige,
  entwurf,
  geaendert,
  unvollstaendig,
}: {
  anzeige: Anzeige;
  entwurf: Entwurf;
  geaendert: boolean;
  unvollstaendig: boolean;
}) {
  const { t } = useTranslation("anzeige");
  const fehlerText = useFehlerText();
  const quelle = useMemo(() => ({ art: "anzeige" as const, id: anzeige.id }), [anzeige.id]);
  const gespeichert = useFeed(quelle);
  const vorschau = useEntwurfsFeed(
    anzeige.id,
    entwurf,
    geaendert && !unvollstaendig,
    gespeichert.feed?.version,
  );
  const zeigtEntwurf = vorschau.feed !== null;
  const zustand = zeigtEntwurf ? { ...gespeichert, feed: vorschau.feed } : gespeichert;
  const uebersprungen = zustand.feed?.skipped ?? [];
  const szenen = zeigtEntwurf ? entwurf.konfig.scenes : anzeige.config.scenes;
  const szenenName = (id: string) => {
    const szene = szenen?.find((x) => x.id === id);
    return szene ? (szene.title ?? t(`art.${szene.kind}`)) : id;
  };

  return (
    <section className="panel" aria-labelledby="vorschau-titel">
      <div className="panel-kopf">
        <h3 className="h-section" id="vorschau-titel">
          {t("vorschau.titel")}
        </h3>
        <Button
          component="a"
          href={schirmPfad(anzeige.id)}
          target="_blank"
          rel="noopener"
          variant="default"
          leftSection={<ExternalLink aria-hidden />}
        >
          {t("vorschau.oeffnen")}
        </Button>
      </div>
      <div className={s.rahmen} data-entwurf={zeigtEntwurf || undefined}>
        <SchirmAnsicht zustand={zustand} quelle={quelle} vorschau />
      </div>
      {zeigtEntwurf ? (
        <p className={s.vorschauHinweis} role="status">
          <Info aria-hidden />
          {t("vorschau.entwurf")}
        </p>
      ) : geaendert ? (
        <p className={s.vorschauHinweis}>
          <Info aria-hidden />
          {vorschau.fehler
            ? t("vorschau.entwurf_fehler", { grund: fehlerText(vorschau.fehler) })
            : unvollstaendig
              ? t("vorschau.entwurf_unvollstaendig")
              : t("vorschau.entwurf_laedt")}
        </p>
      ) : (
        <p className={s.hilfe}>{t("vorschau.hilfe")}</p>
      )}
      {uebersprungen.length > 0 && (
        <div>
          <span className="h-label">{t("vorschau.uebersprungen")}</span>
          <ul className={s.uebersprungen} style={{ marginTop: 6 }}>
            {uebersprungen.map((eintrag) => (
              <li key={`${eintrag.scene_id}-${eintrag.competition_id ?? ""}`}>
                <strong>{szenenName(eintrag.scene_id)}</strong>
                <span>{eintrag.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className={s.anleitung}>
        <h4 className="h-label">{t("vorschau.anleitung_titel")}</h4>
        <ol>
          <li>{t("vorschau.anleitung_1")}</li>
          <li>{t("vorschau.anleitung_2")}</li>
          <li>{t("vorschau.anleitung_3")}</li>
        </ol>
      </div>
      <Adresse pfad={schirmPfad(anzeige.id)} label={t("vorschau.adresse")} />
      {anzeige.device_id && <Adresse pfad={schirmPfad()} label={t("vorschau.adresse_geraet")} />}
    </section>
  );
}
