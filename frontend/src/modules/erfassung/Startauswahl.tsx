import { ActionIcon, Popover, Select, Skeleton, Switch, TextInput } from "@mantine/core";
import { useLocalStorage } from "@mantine/hooks";
import type { UseQueryResult } from "@tanstack/react-query";
import {
  Ban,
  Check,
  CheckCheck,
  Grid3x3,
  MapPin,
  PenLine,
  Search,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Chip, type ChipTon } from "../../components/Chip";
import { Ziffernfeld } from "../../components/Ziffernfeld";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { formatUhrzeit } from "../../lib/format";
import type { StationStart } from "../anmeldung/api";
import type { Stand, Turnier, TurnierUebersicht } from "../turnier/typen";
import type { PruefEintrag } from "./api";
import {
  bahnenAmStand,
  istOffen,
  type KachelStatus,
  kachelStatus,
  type Namen,
  nameVon,
  suche,
  uebrige,
  wartende,
} from "./auswahl";
import s from "./erfassung.module.css";

const NUR_OFFENE_SPEICHER = "schiesshub.erfassung.nur-offene";

const STATUS_TON: Record<KachelStatus, ChipTon> = {
  offen: "neutral",
  in_erfassung: "info",
  erfasst: "gruen",
  abgeschlossen: "gruen",
  abgebrochen: "krit",
};

const STATUS_ICON = {
  offen: undefined,
  in_erfassung: PenLine,
  erfasst: Check,
  abgeschlossen: CheckCheck,
  abgebrochen: Ban,
} as const;

interface StartauswahlProps {
  turnier: Turnier;
  uebersicht: UseQueryResult<TurnierUebersicht>;
  startliste: UseQueryResult<StationStart[]>;
  staende: Stand[];
  stand: Stand | null;
  onStand: (id: string) => void;
  namen: Namen;
  kennziffern: ReadonlyMap<string, string | null>;
  pruefliste: PruefEintrag[];
  offenId: string | null;
  onWahl: (startId: string) => void;
}

/** Linke Spalte: Stand, zu prüfende Ergebnisse, Bahnen am Stand, Wartende, Suche. */
export function Startauswahl({
  uebersicht,
  startliste,
  staende,
  stand,
  onStand,
  namen,
  kennziffern,
  pruefliste,
  offenId,
  onWahl,
}: StartauswahlProps) {
  const { t } = useTranslation("erfassung");
  const [text, setText] = useState("");
  const [ziffernOffen, setZiffernOffen] = useState(false);
  const [nurOffene, setNurOffene] = useLocalStorage<boolean>({
    key: NUR_OFFENE_SPEICHER,
    defaultValue: true,
    getInitialValueInEffect: false,
  });

  if (uebersicht.isPending || startliste.isPending) {
    return (
      <aside className={`panel ${s.auswahl}`} aria-busy="true" aria-label={t("auswahl.titel")}>
        <Skeleton height={56} radius="md" />
        <Skeleton height={220} radius="md" />
      </aside>
    );
  }
  if (uebersicht.isError || startliste.isError) {
    return (
      <aside className={`panel ${s.auswahl}`} aria-label={t("auswahl.titel")}>
        <Fehlerzustand
          fehler={uebersicht.error ?? startliste.error}
          onErneut={() => {
            void uebersicht.refetch();
            void startliste.refetch();
          }}
        />
      </aside>
    );
  }

  const starts = startliste.data;
  const treffer = suche(starts, text, namen, nurOffene);
  const suchtGerade = text.trim() !== "";
  const waehlenAusSuche = () => {
    const erster = treffer[0];
    if (erster && (treffer.length === 1 || String(erster.start_number) === text.trim())) {
      onWahl(erster.start_id);
      setText("");
      setZiffernOffen(false);
    }
  };

  return (
    <aside className={`panel ${s.auswahl}`} aria-label={t("auswahl.titel")}>
      {staende.length === 0 ? (
        <Leerzustand icon={MapPin} titel={t("stand.leer_titel")} text={t("stand.leer_text")} />
      ) : (
        <Select
          label={t("stand.beschriftung")}
          placeholder={t("stand.waehlen")}
          data={staende.map((r) => ({ value: r.id, label: r.name }))}
          value={stand?.id ?? null}
          onChange={(wert) => wert && onStand(wert)}
          allowDeselect={false}
          size="md"
          classNames={{ input: s.grossesFeld }}
          comboboxProps={{ withinPortal: true }}
        />
      )}

      <div className={s.suche}>
        <TextInput
          className={s.sucheFeld}
          value={text}
          onChange={(e) => setText(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              waehlenAusSuche();
            }
            if (e.key === "Escape") setText("");
          }}
          placeholder={t("suche.platzhalter")}
          aria-label={t("suche.beschriftung")}
          leftSection={<Search aria-hidden />}
          size="md"
          classNames={{ input: s.grossesFeld }}
          type="search"
          autoComplete="off"
        />
        <Popover
          opened={ziffernOffen}
          onChange={setZiffernOffen}
          position="bottom-end"
          withinPortal
          trapFocus
        >
          <Popover.Target>
            <ActionIcon
              variant="default"
              className={s.ziffernKnopf}
              aria-label={t("suche.ziffernfeld")}
              aria-expanded={ziffernOffen}
              onClick={() => setZiffernOffen((offen) => !offen)}
            >
              <Grid3x3 aria-hidden />
            </ActionIcon>
          </Popover.Target>
          <Popover.Dropdown>
            <Ziffernfeld
              wert={/^\d*$/.test(text) ? text : ""}
              onChange={setText}
              onFertig={waehlenAusSuche}
              fertigText={t("suche.oeffnen")}
              beschriftung={t("suche.startnummer")}
              verdeckt={false}
              maxLaenge={5}
            />
          </Popover.Dropdown>
        </Popover>
      </div>
      <Switch
        checked={nurOffene}
        onChange={(e) => setNurOffene(e.currentTarget.checked)}
        label={t("filter.nur_offene")}
        size="md"
      />

      {suchtGerade ? (
        <section className={s.gruppe} aria-labelledby="erf-treffer">
          <h2 className="h-label" id="erf-treffer">
            {t("suche.treffer", { count: treffer.length })}
          </h2>
          {treffer.length === 0 ? (
            <p className="gedaempft">{t("suche.keine")}</p>
          ) : (
            <ul className={s.zeilen}>
              {treffer.slice(0, 30).map((start) => (
                <li key={start.start_id}>
                  <StartZeile
                    start={start}
                    namen={namen}
                    kennziffern={kennziffern}
                    offenId={offenId}
                    onWahl={(id) => {
                      onWahl(id);
                      setText("");
                    }}
                    mitStand
                    staende={staende}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : (
        <>
          {pruefliste.length > 0 && (
            <ZuPruefen eintraege={pruefliste} offenId={offenId} onWahl={onWahl} />
          )}
          {stand ? (
            <StandListen
              starts={starts}
              stand={stand}
              namen={namen}
              kennziffern={kennziffern}
              offenId={offenId}
              onWahl={onWahl}
              nurOffene={nurOffene}
            />
          ) : (
            staende.length > 0 && <p className="gedaempft">{t("stand.text")}</p>
          )}
        </>
      )}
    </aside>
  );
}

interface ListenProps {
  starts: StationStart[];
  stand: Stand;
  namen: Namen;
  kennziffern: ReadonlyMap<string, string | null>;
  offenId: string | null;
  onWahl: (startId: string) => void;
  nurOffene: boolean;
}

function StandListen({
  starts,
  stand,
  namen,
  kennziffern,
  offenId,
  onWahl,
  nurOffene,
}: ListenProps) {
  const { t } = useTranslation("erfassung");
  const belegung = bahnenAmStand(starts, stand.id, stand.lane_count);
  const warten = wartende(starts, stand.id);
  const rest = uebrige(starts, stand.id, belegung).filter((st) => !nurOffene || istOffen(st));
  const amStand = belegung.filter((b) => b.start !== null);

  return (
    <>
      <section className={s.gruppe} aria-labelledby="erf-am-stand">
        <h2 className="h-label" id="erf-am-stand">
          {t("auswahl.am_stand", { count: amStand.length })}
        </h2>
        <ul className={s.bahnen}>
          {belegung.map(({ bahn, start }) => (
            <li key={bahn}>
              {start ? (
                <button
                  type="button"
                  className={s.bahnKachel}
                  aria-current={start.start_id === offenId ? "true" : undefined}
                  onClick={() => onWahl(start.start_id)}
                >
                  <span className={`${s.bahnNr} num`}>
                    <span className="nur-screenreader">{t("auswahl.bahn_kurz")} </span>
                    {bahn}
                  </span>
                  <span className={s.bahnName}>
                    <span className="num gedaempft">{start.start_number}</span>{" "}
                    {nameVon(start, namen) ?? t("auswahl.ohne_name")}
                  </span>
                  <span className={s.bahnMeta}>
                    <WettbewerbKurz start={start} kennziffern={kennziffern} />
                    <StatusChip start={start} offenId={offenId} />
                  </span>
                </button>
              ) : (
                <div className={s.bahnFrei}>
                  <span className={`${s.bahnNr} num`}>{bahn}</span>
                  <span>{t("auswahl.bahn_frei")}</span>
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className={s.gruppe} aria-labelledby="erf-wartend">
        <h2 className="h-label" id="erf-wartend">
          {t("auswahl.wartend", { count: warten.length })}
        </h2>
        {warten.length === 0 ? (
          <p className="gedaempft">{t("auswahl.wartend_leer")}</p>
        ) : (
          <ul className={s.zeilen}>
            {warten.map((start) => (
              <li key={start.start_id}>
                <StartZeile
                  start={start}
                  namen={namen}
                  kennziffern={kennziffern}
                  offenId={offenId}
                  onWahl={onWahl}
                />
              </li>
            ))}
          </ul>
        )}
        <p className={s.klein}>{t("auswahl.wartend_hinweis")}</p>
      </section>

      {rest.length > 0 && (
        <section className={s.gruppe} aria-labelledby="erf-weitere">
          <h2 className="h-label" id="erf-weitere">
            {t(nurOffene ? "auswahl.erfasst" : "auswahl.weitere", { count: rest.length })}
          </h2>
          <ul className={s.zeilen}>
            {rest.map((start) => (
              <li key={start.start_id}>
                <StartZeile
                  start={start}
                  namen={namen}
                  kennziffern={kennziffern}
                  offenId={offenId}
                  onWahl={onWahl}
                />
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function WettbewerbKurz({
  start,
  kennziffern,
}: {
  start: StationStart;
  kennziffern: ReadonlyMap<string, string | null>;
}) {
  const kennziffer = kennziffern.get(start.competition_id);
  return (
    <span className={s.wettbewerbKurz}>
      {kennziffer && <span className="num">{kennziffer}</span>}
      <span>{start.competition_name}</span>
    </span>
  );
}

function StatusChip({ start, offenId }: { start: StationStart; offenId: string | null }) {
  const { t } = useTranslation("erfassung");
  const status = kachelStatus(start, offenId);
  const text =
    status === "abgebrochen" && start.abort_reason
      ? t(`abbruch.kurz.${start.abort_reason}`)
      : t(`kachel.${status}`);
  return (
    <Chip ton={STATUS_TON[status]} icon={STATUS_ICON[status]}>
      {text}
    </Chip>
  );
}

interface StartZeileProps {
  start: StationStart;
  namen: Namen;
  kennziffern: ReadonlyMap<string, string | null>;
  offenId: string | null;
  onWahl: (startId: string) => void;
  mitStand?: boolean;
  staende?: Stand[];
}

function StartZeile({
  start,
  namen,
  kennziffern,
  offenId,
  onWahl,
  mitStand,
  staende,
}: StartZeileProps) {
  const { t } = useTranslation("erfassung");
  const standName = mitStand ? staende?.find((r) => r.id === start.range_id)?.name : undefined;
  const wo =
    start.lane != null
      ? t("auswahl.bahn", { bahn: start.lane })
      : start.heat_starts_at
        ? t("auswahl.durchgang", {
            nummer: start.heat_number,
            zeit: formatUhrzeit(new Date(start.heat_starts_at)),
          })
        : start.queue_position != null
          ? t("auswahl.platz", { platz: start.queue_position })
          : null;
  return (
    <button
      type="button"
      className={s.zeile}
      aria-current={start.start_id === offenId ? "true" : undefined}
      onClick={() => onWahl(start.start_id)}
    >
      <span className={`${s.zeileNr} num`}>{start.start_number}</span>
      <span className={s.zeileText}>
        <strong>{nameVon(start, namen) ?? t("auswahl.ohne_name")}</strong>
        <span className="gedaempft">
          <WettbewerbKurz start={start} kennziffern={kennziffern} />
          {start.attempt > 1 && <span> · {t("auswahl.versuch", { nr: start.attempt })}</span>}
          {wo && <span className="num"> · {wo}</span>}
          {standName && <span> · {standName}</span>}
        </span>
      </span>
      <StatusChip start={start} offenId={offenId} />
    </button>
  );
}

function ZuPruefen({
  eintraege,
  offenId,
  onWahl,
}: {
  eintraege: PruefEintrag[];
  offenId: string | null;
  onWahl: (startId: string) => void;
}) {
  const { t } = useTranslation("erfassung");
  return (
    <section className={`${s.gruppe} ${s.pruefen}`} aria-labelledby="erf-pruefen">
      <h2 className={`h-label ${s.pruefenTitel}`} id="erf-pruefen">
        <TriangleAlert aria-hidden />
        {t("pruefen.titel", { count: eintraege.length })}
      </h2>
      <ul className={s.zeilen}>
        {eintraege.map((eintrag) => (
          <li key={eintrag.start_id}>
            <button
              type="button"
              className={s.zeile}
              aria-current={eintrag.start_id === offenId ? "true" : undefined}
              onClick={() => onWahl(eintrag.start_id)}
            >
              <span className={`${s.zeileNr} num`}>{eintrag.start_number}</span>
              <span className={s.zeileText}>
                <strong>{eintrag.display_name ?? t("auswahl.ohne_name")}</strong>
                <span className="gedaempft">
                  {eintrag.competition_name} · {eintrag.review_reason}
                </span>
              </span>
              <Chip ton="warn">{t("pruefen.chip")}</Chip>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
