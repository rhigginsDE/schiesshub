import {
  ActionIcon,
  Button,
  Menu,
  MultiSelect,
  NumberInput,
  Select,
  Switch,
  Textarea,
  TextInput,
} from "@mantine/core";
import {
  LayoutGrid,
  ListOrdered,
  type LucideIcon,
  Medal,
  MessageSquareText,
  Plus,
  Radio,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FeldFehler } from "../../../api/client";
import { ReihenfolgeKnoepfe, verschiebe } from "../../../components/Reihenfolge";
import type { TurnierUebersicht } from "../../turnier/typen";
import type { Szene, SzenenArt } from "../typen";
import { fehlerZu, neueSzene, SZENEN_ARTEN } from "./entwurf";
import s from "./verwaltung.module.css";

export const SZENEN_SYMBOL: Record<SzenenArt, LucideIcon> = {
  live_ranking: Radio,
  startlist: ListOrdered,
  winners: Medal,
  range: LayoutGrid,
  notice: MessageSquareText,
};

interface Auswahl {
  value: string;
  label: string;
}

/** Auswahl aus dem Turnier; IDs, die es dort nicht (mehr) gibt, bleiben sichtbar und gekennzeichnet. */
function mitUnbekannten(daten: Auswahl[], werte: readonly string[], unbekannt: string): Auswahl[] {
  const fehlend = werte.filter((wert) => !daten.some((eintrag) => eintrag.value === wert));
  return [...daten, ...fehlend.map((value) => ({ value, label: unbekannt }))];
}

interface SzenenEditorProps {
  szenen: Szene[];
  uebersicht: TurnierUebersicht | undefined;
  felder: readonly FeldFehler[];
  onAendern: (szenen: Szene[]) => void;
}

/** Geordnete Liste der Szenen: hinzufügen je Art, Dauer, Optionen, Reihenfolge, löschen. */
export function SzenenEditor({ szenen, uebersicht, felder, onAendern }: SzenenEditorProps) {
  const { t } = useTranslation("anzeige");
  const hinzufuegen = (art: SzenenArt) =>
    onAendern([
      ...szenen,
      neueSzene(
        art,
        szenen.map((szene) => szene.id),
        uebersicht?.ranges[0]?.id ?? null,
        t("szene.hinweis_vorgabe"),
      ),
    ]);

  return (
    <section className="panel" aria-labelledby="szenen-titel">
      <div className="panel-kopf">
        <h3 className="h-section" id="szenen-titel">
          {t("szenen.titel")}
        </h3>
        <Menu position="bottom-end" withinPortal>
          <Menu.Target>
            <Button variant="default" leftSection={<Plus aria-hidden />}>
              {t("szenen.hinzufuegen")}
            </Button>
          </Menu.Target>
          <Menu.Dropdown>
            {SZENEN_ARTEN.map((art) => {
              const Icon = SZENEN_SYMBOL[art];
              return (
                <Menu.Item
                  key={art}
                  leftSection={<Icon aria-hidden />}
                  onClick={() => hinzufuegen(art)}
                >
                  {t(`art.${art}`)}
                </Menu.Item>
              );
            })}
          </Menu.Dropdown>
        </Menu>
      </div>
      <p className={s.hilfe}>{t("szenen.hilfe")}</p>
      {fehlerZu(felder, "scenes") && szenen.length === 0 && (
        <p className={s.fehlerListe}>{fehlerZu(felder, "scenes")}</p>
      )}
      {szenen.length === 0 ? (
        <p className="gedaempft">{t("szenen.leer")}</p>
      ) : (
        <ol className={s.szenen}>
          {szenen.map((szene, index) => (
            <SzeneKarte
              key={szene.id}
              szene={szene}
              index={index}
              anzahl={szenen.length}
              uebersicht={uebersicht}
              felder={felder}
              onAendern={(neu) => onAendern(szenen.map((alt, nr) => (nr === index ? neu : alt)))}
              onVerschieben={(richtung) => onAendern(verschiebe(szenen, index, richtung))}
              onLoeschen={() => onAendern(szenen.filter((_, nr) => nr !== index))}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

interface SzeneKarteProps {
  szene: Szene;
  index: number;
  anzahl: number;
  uebersicht: TurnierUebersicht | undefined;
  felder: readonly FeldFehler[];
  onAendern: (szene: Szene) => void;
  onVerschieben: (richtung: -1 | 1) => void;
  onLoeschen: () => void;
}

function SzeneKarte({
  szene,
  index,
  anzahl,
  uebersicht,
  felder,
  onAendern,
  onVerschieben,
  onLoeschen,
}: SzeneKarteProps) {
  const { t } = useTranslation("anzeige");
  const Icon = SZENEN_SYMBOL[szene.kind];
  const pfad = `scenes.${index}`;
  const fehler = (feld: string) => fehlerZu(felder, `${pfad}.${feld}`);
  const art = t(`art.${szene.kind}`);

  return (
    <li className={`inset ${s.szene}`}>
      <div className={s.szeneKopf}>
        <span className={`num ${s.szeneNr}`}>{index + 1}</span>
        <span className={s.szeneArt}>
          <Icon aria-hidden />
          {art} <span className={`num ${s.szeneId}`}>{szene.id}</span>
        </span>
        <ReihenfolgeKnoepfe
          index={index}
          anzahl={anzahl}
          hoch={t("szene.hoch", { art, nr: index + 1 })}
          runter={t("szene.runter", { art, nr: index + 1 })}
          onVerschieben={onVerschieben}
        />
        <ActionIcon
          variant="subtle"
          color="red"
          size={40}
          aria-label={t("szene.loeschen", { art, nr: index + 1 })}
          title={t("szene.loeschen", { art, nr: index + 1 })}
          onClick={onLoeschen}
        >
          <Trash2 aria-hidden />
        </ActionIcon>
      </div>
      <div className={s.zweispaltig}>
        <TextInput
          label={t("szene.ueberschrift")}
          description={t("szene.ueberschrift_hilfe")}
          value={szene.title ?? ""}
          maxLength={120}
          onChange={(e) => onAendern({ ...szene, title: e.currentTarget.value || null })}
          error={fehler("title")}
        />
        <NumberInput
          label={t("szene.dauer")}
          description={t("szene.dauer_hilfe")}
          suffix=" s"
          min={5}
          max={600}
          step={5}
          clampBehavior="blur"
          allowDecimal={false}
          value={szene.seconds}
          onChange={(wert) => onAendern({ ...szene, seconds: Number(wert) || 5 })}
          error={fehler("seconds")}
        />
      </div>
      <SzenenOptionen szene={szene} uebersicht={uebersicht} fehler={fehler} onAendern={onAendern} />
    </li>
  );
}

function SzenenOptionen({
  szene,
  uebersicht,
  fehler,
  onAendern,
}: {
  szene: Szene;
  uebersicht: TurnierUebersicht | undefined;
  fehler: (feld: string) => string | undefined;
  onAendern: (szene: Szene) => void;
}) {
  const { t } = useTranslation("anzeige");
  const unbekannt = t("szene.unbekannt");
  const wettbewerbe: Auswahl[] = (uebersicht?.competitions ?? []).map((w) => ({
    value: w.id,
    label: [w.catalog_code, w.name].filter(Boolean).join(" · "),
  }));
  const klassen: Auswahl[] = (uebersicht?.classes ?? []).map((k) => ({
    value: k.id,
    label: `${k.short} · ${k.name}`,
  }));
  const staende: Auswahl[] = (uebersicht?.ranges ?? []).map((r) => ({
    value: r.id,
    label: r.name,
  }));
  const ohneTurnier = !uebersicht;

  const wettbewerbFeld = (werte: string[], aendern: (ids: string[]) => void) => (
    <MultiSelect
      label={t("szene.wettbewerbe")}
      placeholder={werte.length === 0 ? t("szene.alle_wettbewerbe") : undefined}
      data={mitUnbekannten(wettbewerbe, werte, unbekannt)}
      value={werte}
      onChange={aendern}
      disabled={ohneTurnier}
      searchable
      clearable
      error={fehler("competition_ids")}
    />
  );
  const klassenFeld = (werte: string[], aendern: (ids: string[]) => void) => (
    <MultiSelect
      label={t("szene.klassen")}
      placeholder={werte.length === 0 ? t("szene.alle_klassen") : undefined}
      data={mitUnbekannten(klassen, werte, unbekannt)}
      value={werte}
      onChange={aendern}
      disabled={ohneTurnier}
      searchable
      clearable
      error={fehler("class_ids")}
    />
  );

  switch (szene.kind) {
    case "live_ranking":
      return (
        <div className={s.zweispaltig}>
          {wettbewerbFeld(szene.competition_ids ?? [], (ids) =>
            onAendern({ ...szene, competition_ids: ids }),
          )}
          {klassenFeld(szene.class_ids ?? [], (ids) => onAendern({ ...szene, class_ids: ids }))}
          <NumberInput
            label={t("szene.zeilen")}
            description={t("szene.zeilen_hilfe")}
            min={1}
            max={50}
            clampBehavior="blur"
            allowDecimal={false}
            value={szene.rows}
            onChange={(wert) => onAendern({ ...szene, rows: Number(wert) || 1 })}
            error={fehler("rows")}
          />
          <Switch
            label={t("szene.laufende")}
            description={t("szene.laufende_hilfe")}
            checked={szene.show_running}
            onChange={(e) => onAendern({ ...szene, show_running: e.currentTarget.checked })}
          />
        </div>
      );
    case "startlist":
      return (
        <div className={s.zweispaltig}>
          {wettbewerbFeld(szene.competition_ids ?? [], (ids) =>
            onAendern({ ...szene, competition_ids: ids }),
          )}
          <MultiSelect
            label={t("szene.staende")}
            placeholder={(szene.range_ids ?? []).length === 0 ? t("szene.alle_staende") : undefined}
            data={mitUnbekannten(staende, szene.range_ids ?? [], unbekannt)}
            value={szene.range_ids ?? []}
            onChange={(ids) => onAendern({ ...szene, range_ids: ids })}
            disabled={ohneTurnier}
            clearable
            error={fehler("range_ids")}
          />
          <NumberInput
            label={t("szene.starts")}
            description={t("szene.starts_hilfe")}
            min={1}
            max={50}
            clampBehavior="blur"
            allowDecimal={false}
            value={szene.rows}
            onChange={(wert) => onAendern({ ...szene, rows: Number(wert) || 1 })}
            error={fehler("rows")}
          />
          <Switch
            label={t("szene.abgeschlossene")}
            description={t("szene.abgeschlossene_hilfe")}
            checked={szene.include_finished}
            onChange={(e) => onAendern({ ...szene, include_finished: e.currentTarget.checked })}
          />
        </div>
      );
    case "winners":
      return (
        <div className={s.zweispaltig}>
          {wettbewerbFeld(szene.competition_ids ?? [], (ids) =>
            onAendern({ ...szene, competition_ids: ids }),
          )}
          {klassenFeld(szene.class_ids ?? [], (ids) => onAendern({ ...szene, class_ids: ids }))}
          <NumberInput
            label={t("szene.top")}
            description={t("szene.top_hilfe")}
            min={1}
            max={20}
            clampBehavior="blur"
            allowDecimal={false}
            value={szene.top}
            onChange={(wert) => onAendern({ ...szene, top: Number(wert) || 1 })}
            error={fehler("top")}
          />
          <Switch
            label={t("szene.vorlaeufige")}
            description={t("szene.vorlaeufige_hilfe")}
            checked={szene.include_provisional}
            onChange={(e) => onAendern({ ...szene, include_provisional: e.currentTarget.checked })}
          />
        </div>
      );
    case "range":
      return (
        <div className={s.zweispaltig}>
          <Select
            label={t("szene.stand")}
            placeholder={t("szene.stand_waehlen")}
            data={mitUnbekannten(staende, szene.range_id ? [szene.range_id] : [], unbekannt)}
            value={szene.range_id || null}
            onChange={(wert) => onAendern({ ...szene, range_id: wert ?? "" })}
            disabled={ohneTurnier}
            required
            allowDeselect={false}
            error={fehler("range_id") ?? (!szene.range_id ? t("szene.stand_fehlt") : undefined)}
          />
          <NumberInput
            label={t("szene.naechste")}
            description={t("szene.naechste_hilfe")}
            min={0}
            max={30}
            clampBehavior="blur"
            allowDecimal={false}
            value={szene.next_count}
            onChange={(wert) => onAendern({ ...szene, next_count: Number(wert) || 0 })}
            error={fehler("next_count")}
          />
          <Switch
            label={t("szene.ablauf")}
            description={t("szene.ablauf_hilfe")}
            checked={szene.show_procedure}
            onChange={(e) => onAendern({ ...szene, show_procedure: e.currentTarget.checked })}
          />
        </div>
      );
    case "notice":
      return (
        <div className={s.feldgruppe}>
          <TextInput
            label={t("szene.hinweis_ueberschrift")}
            value={szene.heading}
            maxLength={120}
            required
            onChange={(e) => onAendern({ ...szene, heading: e.currentTarget.value })}
            error={
              fehler("heading") ??
              (!szene.heading.trim() ? t("szene.hinweis_ueberschrift_fehlt") : undefined)
            }
          />
          <Textarea
            label={t("szene.hinweis_text")}
            value={szene.text ?? ""}
            maxLength={2000}
            autosize
            minRows={2}
            maxRows={6}
            onChange={(e) => onAendern({ ...szene, text: e.currentTarget.value })}
            error={fehler("text")}
          />
        </div>
      );
  }
}

/** Szenen, die so nicht gespeichert werden können (Pflichtfelder leer). */
export function szenenUnvollstaendig(szenen: readonly Szene[]): boolean {
  return szenen.some(
    (szene) =>
      (szene.kind === "range" && !szene.range_id) ||
      (szene.kind === "notice" && !szene.heading.trim()),
  );
}
