import { ActionIcon, Button, CloseButton, Modal, Radio, Skeleton, TextInput } from "@mantine/core";
import { useDebouncedCallback } from "@mantine/hooks";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Plus,
  Search,
  SearchX,
  Target,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  disziplinAbfrage,
  disziplinenAbfrage,
  gruppenAbfrage,
  verbaendeAbfrage,
} from "../../../api/abfragen";
import type { Disziplin, DisziplinDetail, Verband } from "../../../api/typen";
import { Bestaetigung } from "../../../components/Bestaetigung";
import { Chip } from "../../../components/Chip";
import { formatGeld } from "../../../components/geld";
import { ReihenfolgeKnoepfe, verschiebe } from "../../../components/Reihenfolge";
import { Fehlerzustand, Leerzustand } from "../../../components/Zustand";
import { formatDatum, formatZahl } from "../../../lib/format";
import { useWettbewerbAnlegen, useWettbewerbeSortieren, useWettbewerbLoeschen } from "../abfragen";
import { fehlerText } from "../fehlertext";
import { ablaufKurz, planungKurz, startsKurz } from "../klartext";
import s from "../turnier.module.css";
import type { TurnierUebersicht, Wettbewerb } from "../typen";
import { WettbewerbBearbeiten } from "./WettbewerbBearbeiten";

const SUCHE_VERZOEGERUNG_MS = 250;

interface WettbewerbeProps {
  turnier: TurnierUebersicht;
  gesperrt: boolean;
  offen: string | undefined;
  onOffen: (id: string | undefined) => void;
}

/** Zweigeteilt: links der Katalog zum Hinzufügen, rechts die Wettbewerbe im Turnier. */
export function Wettbewerbe({ turnier, gesperrt, offen, onOffen }: WettbewerbeProps) {
  return (
    <>
      <KatalogAuswahl turnier={turnier} gesperrt={gesperrt} onAngelegt={onOffen} />
      <ImTurnier turnier={turnier} gesperrt={gesperrt} offen={offen} onOffen={onOffen} />
    </>
  );
}

// --- Katalog -----------------------------------------------------------------------------------

function KatalogAuswahl({
  turnier,
  gesperrt,
  onAngelegt,
}: {
  turnier: TurnierUebersicht;
  gesperrt: boolean;
  onAngelegt: (id: string) => void;
}) {
  const { t, i18n } = useTranslation("turnier");
  const verbaende = useQuery(verbaendeAbfrage());
  const [verbandId, setVerbandId] = useState<string | undefined>();
  const [gruppe, setGruppe] = useState<string | undefined>();
  const [eingabe, setEingabe] = useState("");
  const [suche, setSuche] = useState<string | undefined>();
  const sucheVerzoegert = useDebouncedCallback(
    (text: string) => setSuche(text.trim() || undefined),
    SUCHE_VERZOEGERUNG_MS,
  );
  const verband: Verband | undefined =
    verbaende.data?.find((v) => v.id === verbandId) ?? verbaende.data?.[0];

  return (
    <section className={`panel ${s.katalogSpalte}`} aria-labelledby="wb-katalog">
      <div className="panel-kopf">
        <h3 className="h-section" id="wb-katalog">
          {t("katalog.titel")}
        </h3>
        {verband && (
          <span className="gedaempft num">
            {t("katalog.umfang", {
              disziplinen: formatZahl(verband.anzahl_disziplinen, {}, i18n.language),
              gruppen: formatZahl(verband.anzahl_gruppen, {}, i18n.language),
            })}
          </span>
        )}
      </div>
      <TextInput
        type="search"
        size="md"
        value={eingabe}
        placeholder={t("katalog.suche_platzhalter")}
        aria-label={t("katalog.suche")}
        leftSection={<Search aria-hidden />}
        rightSection={
          eingabe ? (
            <CloseButton
              aria-label={t("katalog.suche_leeren")}
              onClick={() => {
                setEingabe("");
                sucheVerzoegert.cancel();
                setSuche(undefined);
              }}
            />
          ) : null
        }
        onChange={(e) => {
          setEingabe(e.currentTarget.value);
          sucheVerzoegert(e.currentTarget.value);
        }}
      />
      {verbaende.isError ? (
        <Fehlerzustand fehler={verbaende.error} onErneut={() => void verbaende.refetch()} />
      ) : !verband ? (
        <Skeleton height={200} radius="md" />
      ) : (
        <>
          {(verbaende.data?.length ?? 0) > 1 && (
            <fieldset className={s.wahlReihe} aria-label={t("katalog.verband")}>
              {verbaende.data?.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  className={s.wahlchip}
                  aria-pressed={v.id === verband.id}
                  title={v.name}
                  onClick={() => {
                    setVerbandId(v.id);
                    setGruppe(undefined);
                  }}
                >
                  {v.kuerzel}
                </button>
              ))}
            </fieldset>
          )}
          <Gruppen verband={verband.id} gruppe={gruppe} onGruppe={setGruppe} />
          <Treffer
            turnier={turnier}
            verband={verband}
            gruppe={gruppe}
            suche={suche}
            gesperrt={gesperrt}
            onAngelegt={onAngelegt}
            onAlleGruppen={() => setGruppe(undefined)}
          />
          <p className={s.katalogFuss}>
            {t("katalog.stand", {
              name: verband.regelwerk.name,
              stand: formatDatum(verband.regelwerk.stand, i18n.language),
            })}
            {" · "}
            {t("katalog.eigener_hinweis")}
          </p>
        </>
      )}
    </section>
  );
}

function Gruppen({
  verband,
  gruppe,
  onGruppe,
}: {
  verband: string;
  gruppe: string | undefined;
  onGruppe: (gruppe: string | undefined) => void;
}) {
  const { t, i18n } = useTranslation("turnier");
  const gruppen = useQuery(gruppenAbfrage(verband));
  if (gruppen.isPending) return <Skeleton height={120} radius="md" />;
  if (gruppen.isError) {
    return <Fehlerzustand fehler={gruppen.error} onErneut={() => void gruppen.refetch()} />;
  }
  return (
    <ul className={`inset ${s.gruppen}`} aria-label={t("katalog.gruppen")}>
      <li>
        <button
          type="button"
          className={s.gruppe}
          aria-pressed={!gruppe}
          onClick={() => onGruppe(undefined)}
        >
          <span>{t("katalog.alle_gruppen")}</span>
        </button>
      </li>
      {gruppen.data.map((eintrag) => (
        <li key={eintrag.id}>
          <button
            type="button"
            className={s.gruppe}
            aria-pressed={gruppe === eintrag.id}
            onClick={() => onGruppe(eintrag.id)}
          >
            <span>{eintrag.name}</span>
            <span className={`num ${s.anzahl}`}>
              {formatZahl(eintrag.anzahl, {}, i18n.language)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

interface TrefferProps {
  turnier: TurnierUebersicht;
  verband: Verband;
  gruppe: string | undefined;
  suche: string | undefined;
  gesperrt: boolean;
  onAngelegt: (id: string) => void;
  onAlleGruppen: () => void;
}

function Treffer({
  turnier,
  verband,
  gruppe,
  suche,
  gesperrt,
  onAngelegt,
  onAlleGruppen,
}: TrefferProps) {
  const { t } = useTranslation("turnier");
  const queryClient = useQueryClient();
  const disziplinen = useQuery({
    ...disziplinenAbfrage(verband.id, { gruppe, q: suche }),
    placeholderData: keepPreviousData,
  });
  const anlegen = useWettbewerbAnlegen(turnier.id);
  const [wahl, setWahl] = useState<{ detail: DisziplinDetail; variante: string } | null>(null);
  const [laedt, setLaedt] = useState<string | null>(null);
  const [fehler, setFehler] = useState<unknown>(null);

  const imTurnier = new Map<string, number>();
  for (const w of turnier.competitions) {
    if (w.catalog_federation === verband.id && w.catalog_code) {
      imTurnier.set(w.catalog_code, (imTurnier.get(w.catalog_code) ?? 0) + 1);
    }
  }

  const anlegenMit = (detail: DisziplinDetail, variante?: string) =>
    anlegen.mutate(
      {
        catalog_federation: detail.verband,
        catalog_code: detail.kennziffer,
        ...(variante ? { variant_id: variante } : {}),
      },
      {
        onSuccess: (neu) => {
          setWahl(null);
          onAngelegt(neu.id);
        },
        onError: (f) => setFehler(f),
        onSettled: () => setLaedt(null),
      },
    );

  const hinzufuegen = async (disziplin: Disziplin) => {
    setFehler(null);
    setLaedt(disziplin.kennziffer);
    try {
      const detail = await queryClient.fetchQuery(
        disziplinAbfrage(verband.id, disziplin.kennziffer),
      );
      const varianten = detail.ablauf.varianten;
      if (varianten.length > 1) {
        setLaedt(null);
        setWahl({ detail, variante: varianten[0]?.id ?? "" });
        return;
      }
      anlegenMit(detail);
    } catch (f) {
      setFehler(f);
      setLaedt(null);
    }
  };

  if (disziplinen.isPending) return <Skeleton height={240} radius="md" />;
  if (disziplinen.isError) {
    return <Fehlerzustand fehler={disziplinen.error} onErneut={() => void disziplinen.refetch()} />;
  }
  if (disziplinen.data.length === 0) {
    return (
      <Leerzustand
        icon={SearchX}
        titel={t("katalog.leer_titel")}
        text={suche ? t("katalog.leer_suche", { q: suche }) : t("katalog.leer_gruppe")}
      >
        {gruppe && suche && (
          <Button variant="default" onClick={onAlleGruppen}>
            {t("katalog.in_allen_suchen")}
          </Button>
        )}
      </Leerzustand>
    );
  }

  return (
    <>
      {fehler !== null && (
        <p className={s.fehlerText} role="alert">
          <TriangleAlert aria-hidden />
          {fehlerText(fehler)}
        </p>
      )}
      <ul className={s.treffer} data-laedt={disziplinen.isPlaceholderData || undefined}>
        {disziplinen.data.map((disziplin) => {
          const anzahl = imTurnier.get(disziplin.kennziffer) ?? 0;
          return (
            <li key={disziplin.kennziffer} className={s.trefferZeile}>
              <span className={`num ${s.kennziffer}`}>{disziplin.kennziffer}</span>
              <span className={s.zeileText}>
                <strong>{disziplin.name}</strong>
                <span className="gedaempft">
                  {gruppe ? disziplin.waffe : disziplin.gruppe_name}
                </span>
              </span>
              {anzahl > 0 ? (
                <span className={s.gewaehlt}>
                  <Check aria-hidden />
                  {t("katalog.im_turnier")}
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    size={40}
                    aria-label={t("katalog.nochmal", { kennziffer: disziplin.kennziffer })}
                    title={t("katalog.nochmal", { kennziffer: disziplin.kennziffer })}
                    disabled={gesperrt}
                    loading={laedt === disziplin.kennziffer}
                    onClick={() => void hinzufuegen(disziplin)}
                  >
                    <Plus aria-hidden />
                  </ActionIcon>
                </span>
              ) : (
                <Button
                  variant="default"
                  size="sm"
                  leftSection={<Plus aria-hidden />}
                  disabled={gesperrt}
                  loading={laedt === disziplin.kennziffer}
                  aria-label={t("katalog.hinzufuegen_name", {
                    name: disziplin.name,
                    kennziffer: disziplin.kennziffer,
                  })}
                  onClick={() => void hinzufuegen(disziplin)}
                  className={s.hinzufuegen}
                >
                  {t("katalog.hinzufuegen")}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      <Modal
        opened={wahl !== null}
        onClose={() => setWahl(null)}
        closeButtonProps={{ "aria-label": t("aktion.abbrechen") }}
        title={wahl ? t("katalog.variante_titel", { name: wahl.detail.name }) : ""}
        centered
      >
        {wahl && (
          <form
            className={s.formular}
            onSubmit={(e) => {
              e.preventDefault();
              anlegenMit(wahl.detail, wahl.variante);
            }}
          >
            <p className={s.hilfe}>{t("katalog.variante_text")}</p>
            <Radio.Group
              value={wahl.variante}
              onChange={(wert) => setWahl({ ...wahl, variante: wert })}
            >
              <div className={s.variantenWahl}>
                {wahl.detail.ablauf.varianten.map((variante) => (
                  <Radio
                    key={variante.id}
                    value={variante.id}
                    label={variante.name}
                    description={ablaufKurz(variante)}
                  />
                ))}
              </div>
            </Radio.Group>
            <div className={s.knopfReihe}>
              <Button variant="default" onClick={() => setWahl(null)}>
                {t("aktion.abbrechen")}
              </Button>
              <Button type="submit" loading={anlegen.isPending}>
                {t("katalog.hinzufuegen")}
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}

// --- Im Turnier --------------------------------------------------------------------------------

function ImTurnier({ turnier, gesperrt, offen, onOffen }: WettbewerbeProps) {
  const { t } = useTranslation("turnier");
  const sortieren = useWettbewerbeSortieren(turnier.id);
  const liste = turnier.competitions;

  return (
    <section className={`panel ${s.turnierSpalte}`} aria-labelledby="wb-im-turnier">
      <div className="panel-kopf">
        <h3 className="h-section" id="wb-im-turnier">
          {t("wettbewerb.im_turnier", { count: liste.length })}
        </h3>
        <span className="gedaempft">{t("wettbewerb.reihenfolge_hinweis")}</span>
      </div>
      {sortieren.isError && (
        <p className={s.fehlerText} role="alert">
          {fehlerText(sortieren.error)}
        </p>
      )}
      {liste.length === 0 ? (
        <Leerzustand
          icon={Target}
          titel={t("wettbewerb.leer_titel")}
          text={t("wettbewerb.leer_text")}
        />
      ) : (
        <ul className={s.wettbewerbe}>
          {liste.map((wettbewerb, index) => (
            <WettbewerbKarte
              key={wettbewerb.id}
              turnier={turnier}
              wettbewerb={wettbewerb}
              index={index}
              offen={offen === wettbewerb.id}
              gesperrt={gesperrt}
              sortiertGerade={sortieren.isPending}
              onOffen={onOffen}
              onVerschieben={(richtung) =>
                sortieren.mutate(verschiebe(liste, index, richtung).map((w) => w.id))
              }
            />
          ))}
        </ul>
      )}
    </section>
  );
}

interface WettbewerbKarteProps {
  turnier: TurnierUebersicht;
  wettbewerb: Wettbewerb;
  index: number;
  offen: boolean;
  gesperrt: boolean;
  sortiertGerade: boolean;
  onOffen: (id: string | undefined) => void;
  onVerschieben: (richtung: -1 | 1) => void;
}

function WettbewerbKarte({
  turnier,
  wettbewerb,
  index,
  offen,
  gesperrt,
  sortiertGerade,
  onOffen,
  onVerschieben,
}: WettbewerbKarteProps) {
  const { t, i18n } = useTranslation("turnier");
  const sprache = i18n.language;
  const loeschen = useWettbewerbLoeschen(turnier.id);
  const [frage, setFrage] = useState(false);
  const stand = turnier.ranges.find((r) => r.id === wettbewerb.range_id);
  const formularId = `wettbewerb-${wettbewerb.id}`;

  return (
    <li className={s.wettbewerb} data-offen={offen || undefined}>
      <div className={s.wettbewerbZeile}>
        <span className={`num ${s.kennziffer}`}>
          {wettbewerb.catalog_code ?? <span className={s.eigen}>{t("wettbewerb.eigen")}</span>}
        </span>
        <button
          type="button"
          className={s.wettbewerbText}
          aria-expanded={offen}
          aria-controls={formularId}
          onClick={() => onOffen(offen ? undefined : wettbewerb.id)}
        >
          <strong>{wettbewerb.name}</strong>
          <span>{ablaufKurz(wettbewerb.definition.variant, sprache)}</span>
          <span className={s.wettbewerbMeta}>
            {stand ? (
              <span>{stand.name}</span>
            ) : (
              <Chip ton="warn" icon={TriangleAlert}>
                {t("wettbewerb.ohne_stand")}
              </Chip>
            )}
            <span>{planungKurz(wettbewerb, sprache)}</span>
            <span>{startsKurz(wettbewerb, sprache)}</span>
            <span className="num">
              {formatGeld(wettbewerb.fee_first_cents, turnier.settings.currency, sprache)}
            </span>
          </span>
        </button>
        <span className={s.zeilenAktionen}>
          <ReihenfolgeKnoepfe
            index={index}
            anzahl={turnier.competitions.length}
            hoch={t("aktion.nach_oben", { name: wettbewerb.name })}
            runter={t("aktion.nach_unten", { name: wettbewerb.name })}
            gesperrt={gesperrt || sortiertGerade}
            onVerschieben={onVerschieben}
          />
          <ActionIcon
            variant="subtle"
            color="gray"
            size={40}
            aria-label={t("aktion.loeschen", { name: wettbewerb.name })}
            title={t("aktion.loeschen", { name: wettbewerb.name })}
            disabled={gesperrt}
            onClick={() => {
              loeschen.reset();
              setFrage(true);
            }}
          >
            <Trash2 aria-hidden />
          </ActionIcon>
          <ActionIcon
            variant="subtle"
            color="gray"
            size={40}
            aria-label={offen ? t("wettbewerb.zuklappen") : t("wettbewerb.aufklappen")}
            aria-expanded={offen}
            aria-controls={formularId}
            onClick={() => onOffen(offen ? undefined : wettbewerb.id)}
          >
            {offen ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />}
          </ActionIcon>
        </span>
      </div>
      {offen && (
        <div id={formularId} className={s.wettbewerbInhalt}>
          <WettbewerbBearbeiten
            turnier={turnier}
            wettbewerb={wettbewerb}
            gesperrt={gesperrt}
            onGeoeffnet={onOffen}
          />
        </div>
      )}
      <Bestaetigung
        offen={frage}
        titel={t("wettbewerb.loeschen_titel", { name: wettbewerb.name })}
        text={<p>{t("wettbewerb.loeschen_text")}</p>}
        bestaetigen={t("aktion.loeschen_knopf")}
        abbrechen={t("aktion.abbrechen")}
        ton="gefahr"
        laedt={loeschen.isPending}
        fehler={loeschen.isError ? fehlerText(loeschen.error) : undefined}
        onSchliessen={() => setFrage(false)}
        onBestaetigen={() =>
          loeschen.mutate(wettbewerb.id, {
            onSuccess: () => {
              setFrage(false);
              if (offen) onOffen(undefined);
            },
          })
        }
      />
    </li>
  );
}
