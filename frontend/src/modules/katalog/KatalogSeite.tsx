import { Button, CloseButton, Skeleton, TextInput } from "@mantine/core";
import { useDebouncedCallback } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, Outlet } from "@tanstack/react-router";
import { ChevronRight, FolderOpen, Search, SearchX, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  disziplinenAbfrage,
  gruppenAbfrage,
  healthAbfrage,
  verbaendeAbfrage,
} from "../../api/abfragen";
import type { Disziplin, Gruppe, Verband } from "../../api/typen";
import { useModule } from "../../app/modul";
import { Chip } from "../../components/Chip";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { formatDatum, formatZahl } from "../../lib/format";
import s from "./katalog.module.css";
import { DISZIPLIN_PFAD, type KatalogAuswahl, type KatalogSuche } from "./pfade";

const SUCHE_VERZOEGERUNG_MS = 250;

interface KatalogSeiteProps {
  suche: KatalogSuche;
  auswahl: KatalogAuswahl | null;
  /** Schreibt die Filter in die Adresse. `auswahlBehalten: false` schließt die Detailansicht. */
  onSucheAendern: (suche: KatalogSuche, auswahlBehalten?: boolean) => void;
}

/** Disziplin-Katalog: Verband, Gruppen, Suche und Liste; die Detailansicht kommt über die Unterroute. */
export function KatalogSeite({ suche, auswahl, onSucheAendern }: KatalogSeiteProps) {
  const { t, i18n } = useTranslation("katalog");
  const verbaende = useQuery(verbaendeAbfrage());
  const verband =
    verbaende.data?.find((eintrag) => eintrag.id === suche.verband) ?? verbaende.data?.[0];

  return (
    <div className={s.seite} data-layout="fenster" data-detail={auswahl ? "offen" : "zu"}>
      <Seitenkopf verband={verband} sprache={i18n.language} />
      <Importfehler />

      {verbaende.isPending ? (
        <div className={s.spalten} aria-busy="true">
          <Skeleton height={360} radius="lg" />
          <Skeleton height={360} radius="lg" />
          <Skeleton height={360} radius="lg" className={s.detail} />
        </div>
      ) : verbaende.isError ? (
        <div className="panel">
          <Fehlerzustand fehler={verbaende.error} onErneut={() => void verbaende.refetch()} />
        </div>
      ) : !verband ? (
        <div className="panel">
          <Leerzustand icon={FolderOpen} titel={t("leer.titel")} text={t("leer.text")} />
        </div>
      ) : (
        <div className={s.spalten}>
          <Filter
            verbaende={verbaende.data}
            verband={verband}
            suche={suche}
            onSucheAendern={onSucheAendern}
          />
          <Disziplinliste
            verband={verband}
            suche={suche}
            auswahl={auswahl}
            onSucheAendern={onSucheAendern}
          />
          <div className={s.detail}>
            <Outlet />
          </div>
        </div>
      )}
    </div>
  );
}

function Seitenkopf({ verband, sprache }: { verband: Verband | undefined; sprache: string }) {
  const { t } = useTranslation();
  const module = useModule();
  const navigation = module.find((modul) => modul.id === "katalog")?.navigation;
  const stationId = navigation?.art === "bereich" ? navigation.station : undefined;
  const station = module.find((modul) => modul.id === stationId);

  return (
    <header className={s.kopf}>
      {station && (
        <nav className={s.pfad} aria-label={t("shell:navigation.stationen")}>
          <Link to={station.navigation.pfad}>{t(`${station.namensraum}:titel`)}</Link>
          <ChevronRight aria-hidden />
        </nav>
      )}
      <div className={s.kopfzeile}>
        <h1 className="h-display">{t("katalog:titel")}</h1>
        {verband?.status === "entwurf" && (
          <Chip ton="warn" icon={TriangleAlert} title={t("katalog:kopf.entwurf_hinweis")}>
            {t("katalog:kopf.entwurf")}
          </Chip>
        )}
      </div>
      {verband && (
        <p className="gedaempft">
          <span>
            {t("katalog:kopf.umfang", {
              disziplinen: formatZahl(verband.anzahl_disziplinen, {}, sprache),
              gruppen: formatZahl(verband.anzahl_gruppen, {}, sprache),
            })}
          </span>
          {" · "}
          {t("katalog:kopf.regelwerk", {
            name: verband.regelwerk.name,
            stand: formatDatum(verband.regelwerk.stand, sprache),
          })}
        </p>
      )}
    </header>
  );
}

/** Warnung, wenn der Server beim Einlesen des Katalogs Fehler gemeldet hat. */
function Importfehler() {
  const { t } = useTranslation("katalog");
  const health = useQuery({ ...healthAbfrage(), refetchInterval: false });
  const fehler = health.data?.katalog?.fehler ?? [];
  if (fehler.length === 0) return null;

  return (
    <div className={s.banner} role="alert">
      <TriangleAlert aria-hidden />
      <div>
        <strong>{t("importfehler.titel")}</strong>
        <p>{t("importfehler.text")}</p>
        <ul className={s.bannerListe}>
          {fehler.map((eintrag) => {
            const ort = [eintrag.datei, eintrag.pfad].filter(Boolean).join(" → ");
            return (
              <li key={`${ort}|${eintrag.meldung}`}>
                {ort && <strong>{ort}: </strong>}
                {eintrag.meldung}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

interface FilterProps {
  verbaende: Verband[];
  verband: Verband;
  suche: KatalogSuche;
  onSucheAendern: KatalogSeiteProps["onSucheAendern"];
}

function Filter({ verbaende, verband, suche, onSucheAendern }: FilterProps) {
  const { t, i18n } = useTranslation("katalog");
  const gruppen = useQuery(gruppenAbfrage(verband.id));
  const [eingabe, setEingabe] = useState(suche.q ?? "");

  const sucheVerzoegert = useDebouncedCallback((text: string) => {
    onSucheAendern({ ...suche, q: text.trim() || undefined });
  }, SUCHE_VERZOEGERUNG_MS);

  // Die Adresse ist die Quelle: Wird die Suche woanders geleert, folgt das Eingabefeld.
  const [bekannteSuche, setBekannteSuche] = useState(suche.q);
  if (bekannteSuche !== suche.q) {
    setBekannteSuche(suche.q);
    if ((suche.q ?? "") !== eingabe.trim()) setEingabe(suche.q ?? "");
  }

  return (
    <section className={`panel ${s.filter}`} aria-label={t("suche.beschriftung")}>
      <TextInput
        type="search"
        size="md"
        value={eingabe}
        onChange={(ereignis) => {
          setEingabe(ereignis.currentTarget.value);
          sucheVerzoegert(ereignis.currentTarget.value);
        }}
        placeholder={t("suche.platzhalter")}
        aria-label={t("suche.beschriftung")}
        leftSection={<Search aria-hidden />}
        rightSection={
          eingabe ? (
            <CloseButton
              aria-label={t("suche.leeren")}
              onClick={() => {
                setEingabe("");
                sucheVerzoegert.cancel();
                onSucheAendern({ ...suche, q: undefined });
              }}
            />
          ) : null
        }
      />

      <fieldset className={s.verbaende}>
        <legend className="h-label">{t("verband.beschriftung")}</legend>
        {verbaende.map((eintrag) => (
          <button
            key={eintrag.id}
            type="button"
            className={s.wahlchip}
            aria-pressed={eintrag.id === verband.id}
            title={eintrag.name}
            onClick={() => onSucheAendern({ verband: eintrag.id, q: suche.q }, false)}
          >
            {eintrag.kuerzel}
          </button>
        ))}
      </fieldset>

      <div className={s.gruppenBlock}>
        <h2 className="h-label" id="katalog-gruppen">
          {t("gruppen.beschriftung")}
        </h2>
        {gruppen.isPending ? (
          <div className={s.skelettListe} aria-busy="true">
            {[0, 1, 2, 3, 4, 5].map((nr) => (
              <Skeleton key={nr} height={30} radius="sm" />
            ))}
          </div>
        ) : gruppen.isError ? (
          <Fehlerzustand fehler={gruppen.error} onErneut={() => void gruppen.refetch()} />
        ) : gruppen.data.length === 0 ? (
          <Leerzustand
            icon={FolderOpen}
            titel={t("gruppen.leer_titel")}
            text={t("gruppen.leer_text")}
          />
        ) : (
          <ul className={`inset ${s.gruppen}`} aria-labelledby="katalog-gruppen">
            <li>
              <Gruppenknopf
                name={t("gruppen.alle")}
                anzahl={verband.anzahl_disziplinen}
                aktiv={!suche.gruppe}
                sprache={i18n.language}
                onClick={() => onSucheAendern({ ...suche, gruppe: undefined })}
              />
            </li>
            {gruppen.data.map((gruppe) => (
              <li key={gruppe.id}>
                <Gruppenknopf
                  name={gruppe.name}
                  anzahl={gruppe.anzahl}
                  aktiv={suche.gruppe === gruppe.id}
                  ungeprueft={!gruppe.geprueft}
                  sprache={i18n.language}
                  onClick={() => onSucheAendern({ ...suche, gruppe: gruppe.id })}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

interface GruppenknopfProps {
  name: string;
  anzahl: number;
  aktiv: boolean;
  ungeprueft?: boolean;
  sprache: string;
  onClick: () => void;
}

function Gruppenknopf({ name, anzahl, aktiv, ungeprueft, sprache, onClick }: GruppenknopfProps) {
  const { t } = useTranslation("katalog");
  return (
    <button type="button" className={s.gruppe} aria-pressed={aktiv} onClick={onClick}>
      <span className={s.gruppeName}>
        {name}
        {ungeprueft && (
          <span className={s.ungeprueft} title={t("gruppen.ungeprueft")}>
            <TriangleAlert aria-hidden />
            <span className="nur-screenreader">{t("gruppen.ungeprueft")}</span>
          </span>
        )}
      </span>
      <span className={`num ${s.anzahl}`}>{formatZahl(anzahl, {}, sprache)}</span>
    </button>
  );
}

interface DisziplinlisteProps {
  verband: Verband;
  suche: KatalogSuche;
  auswahl: KatalogAuswahl | null;
  onSucheAendern: KatalogSeiteProps["onSucheAendern"];
}

function Disziplinliste({ verband, suche, auswahl, onSucheAendern }: DisziplinlisteProps) {
  const { t } = useTranslation("katalog");
  const gruppen = useQuery(gruppenAbfrage(verband.id));
  const disziplinen = useQuery({
    ...disziplinenAbfrage(verband.id, { gruppe: suche.gruppe, q: suche.q }),
    placeholderData: keepPreviousData,
  });
  const gruppe: Gruppe | undefined = gruppen.data?.find((eintrag) => eintrag.id === suche.gruppe);
  const bereich = suche.gruppe ? (gruppe?.name ?? suche.gruppe) : t("gruppen.alle");

  return (
    <section className={`panel ${s.liste}`} aria-labelledby="katalog-liste">
      <div className="panel-kopf">
        <h2 className="h-section" id="katalog-liste">
          {bereich}
        </h2>
        {disziplinen.data && (
          <span className={`gedaempft ${s.treffer}`} aria-live="polite">
            {suche.q
              ? t("liste.treffer_suche", { count: disziplinen.data.length, q: suche.q })
              : t("liste.treffer", { count: disziplinen.data.length })}
          </span>
        )}
      </div>

      {disziplinen.isPending ? (
        <div className={s.skelettListe} aria-busy="true">
          {[0, 1, 2, 3, 4, 5, 6, 7].map((nr) => (
            <Skeleton key={nr} height={44} radius="sm" />
          ))}
        </div>
      ) : disziplinen.isError ? (
        <Fehlerzustand fehler={disziplinen.error} onErneut={() => void disziplinen.refetch()} />
      ) : disziplinen.data.length === 0 ? (
        <Leerzustand
          icon={SearchX}
          titel={t("liste.leer_titel")}
          text={
            suche.q && suche.gruppe
              ? t("liste.leer_suche_gruppe", { gruppe: bereich, q: suche.q })
              : suche.q
                ? t("liste.leer_suche", { q: suche.q })
                : t("liste.leer_gruppe")
          }
        >
          {suche.q && suche.gruppe && (
            <Button onClick={() => onSucheAendern({ ...suche, gruppe: undefined })}>
              {t("liste.in_allen_suchen")}
            </Button>
          )}
          {suche.q && !suche.gruppe && (
            <Button variant="default" onClick={() => onSucheAendern({ ...suche, q: undefined })}>
              {t("suche.leeren")}
            </Button>
          )}
        </Leerzustand>
      ) : (
        <ul className={s.disziplinen} data-laedt={disziplinen.isPlaceholderData || undefined}>
          {disziplinen.data.map((disziplin) => (
            <Disziplinzeile
              key={disziplin.kennziffer}
              disziplin={disziplin}
              verband={verband.id}
              suche={suche}
              mitGruppe={!suche.gruppe}
              aktiv={auswahl?.verband === verband.id && auswahl.kennziffer === disziplin.kennziffer}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

interface DisziplinzeileProps {
  disziplin: Disziplin;
  verband: string;
  suche: KatalogSuche;
  mitGruppe: boolean;
  aktiv: boolean;
}

function Disziplinzeile({ disziplin, verband, suche, mitGruppe, aktiv }: DisziplinzeileProps) {
  const { t } = useTranslation("katalog");
  return (
    <li>
      <Link
        to={DISZIPLIN_PFAD}
        params={{ verband, kennziffer: disziplin.kennziffer }}
        search={suche}
        className={s.disziplin}
        aria-current={aktiv ? "true" : undefined}
      >
        <span className={`num ${s.kennziffer}`}>{disziplin.kennziffer}</span>
        <span className={s.disziplinText}>
          <strong>{disziplin.name}</strong>
          <span>
            {mitGruppe ? `${disziplin.gruppe_name} · ${disziplin.waffe}` : disziplin.waffe}
          </span>
        </span>
        {disziplin.optional && (
          <Chip ton="info" title={t("liste.optional_hinweis")}>
            {t("liste.optional")}
          </Chip>
        )}
        <ChevronRight className={s.weiter} aria-hidden />
      </Link>
    </li>
  );
}
