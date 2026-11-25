import { Button } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CircleCheck, Info, type LucideIcon, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useBereiche } from "../../app/modul";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { Dialog } from "../../components/Dialog";
import { formatGeld } from "../../components/geld";
import { PersonenSuche } from "../../components/PersonenSuche";
import { MitTurnier, TurnierWechsel } from "../../components/TurnierWahl";
import { Fehlerzustand } from "../../components/Zustand";
import { formatZahl } from "../../lib/format";
import { type Person, personAbfrage, vereineAbfrage } from "../teilnehmer/api";
import { PersonFormular } from "../teilnehmer/PersonFormular";
import { uebersichtAbfrage } from "../turnier/abfragen";
import type { Turnier } from "../turnier/typen";
import { Angemeldet } from "./Angemeldet";
import { AnmeldungFormular, type Schuetze } from "./AnmeldungFormular";
import s from "./AnmeldungSeite.module.css";
import {
  type Anmeldung,
  type AnmeldungAenderung,
  anmeldungenAbfrage,
  type StartrechtMeldung,
} from "./api";
import type { BuchungsErgebnis } from "./buchen";
import { type BestaetigungsArt, bestaetigungsArt } from "./logik";
import { StartrechtHinweise } from "./Startrecht";

interface AnmeldungSeiteProps {
  station: string;
  icon: LucideIcon;
}

/** Station Anmeldung: Schützen anmelden und Starts buchen, in genau einem Turnier. */
export function AnmeldungSeite({ station, icon }: AnmeldungSeiteProps) {
  const { t } = useTranslation("anmeldung");
  return (
    <MitTurnier hinweis={t("turnier_hinweis")} kopf={<Kopf station={station} icon={icon} />}>
      {(wahl) => (
        <Station station={station} icon={icon} turnier={wahl.turnier} onWechseln={wahl.wechseln} />
      )}
    </MitTurnier>
  );
}

interface KopfProps {
  station: string;
  icon: LucideIcon;
  turnier?: Turnier;
  onWechseln?: () => void;
}

function Kopf({ station, icon: Icon, turnier, onWechseln }: KopfProps) {
  const { t } = useTranslation();
  const bereiche = useBereiche(station);
  return (
    <header className={s.kopf}>
      <div className={s.titel}>
        <span className={s.symbol}>
          <Icon aria-hidden />
        </span>
        <h1 className="h-display">{t("anmeldung:titel")}</h1>
      </div>
      {turnier && onWechseln && <TurnierWechsel turnier={turnier} onWechseln={onWechseln} />}
      {bereiche.length > 0 && (
        <nav className={s.bereiche} aria-label={t("anmeldung:bereiche")}>
          {bereiche.map((modul) => {
            const BereichIcon = modul.navigation.icon;
            return (
              <Button
                key={modul.id}
                component={Link}
                to={modul.navigation.pfad}
                variant="subtle"
                color="gray"
                size="md"
                leftSection={<BereichIcon aria-hidden />}
              >
                {t(`${modul.namensraum}:titel`)}
              </Button>
            );
          })}
        </nav>
      )}
      <p className={s.anleitung}>{t("anmeldung:anleitung")}</p>
    </header>
  );
}

function schuetzeAusPerson(person: Person): Schuetze {
  return {
    id: person.id,
    name: person.name,
    verein: person.club_name,
    mitgliedsnummer: person.member_no,
    anzeige: person.display_name,
  };
}

function schuetzeAusAnmeldung(anmeldung: Anmeldung): Schuetze {
  return {
    id: anmeldung.person.id,
    name: anmeldung.person.name,
    verein: anmeldung.person.club,
    mitgliedsnummer: null,
    anzeige: anmeldung.person.display_name,
  };
}

interface Bestaetigt {
  art: BestaetigungsArt;
  startnummer: number;
  name: string;
  starts: number;
  cents: number;
  waehrung: string;
  /** Nur bei „geaendert“: was geändert wurde, als Klartext (z. B. „Klasse D1“) */
  aenderungen: string[];
  /** Warnungen und Hinweise zum Startrecht an den eben gebuchten Starts */
  startrecht: StartrechtMeldung[];
}

interface StationProps {
  station: string;
  icon: LucideIcon;
  turnier: Turnier;
  onWechseln: () => void;
}

function Station({ station, icon, turnier, onWechseln }: StationProps) {
  const { t, i18n } = useTranslation("anmeldung");
  const queryClient = useQueryClient();
  const uebersicht = useQuery(uebersichtAbfrage(turnier.id));
  const anmeldungen = useQuery(anmeldungenAbfrage(turnier.id));
  // Vereine früh laden, damit „neue Person“ sofort Vereine anbietet.
  useQuery(vereineAbfrage());

  const [auswahl, setAuswahl] = useState<Schuetze | null>(null);
  const [neuePerson, setNeuePerson] = useState<{ name: string; nr: number } | null>(null);
  const [durchlauf, setDurchlauf] = useState(0);
  const [bestaetigt, setBestaetigt] = useState<Bestaetigt | null>(null);
  const ungespeichert = useRef(false);
  const [ausstehend, setAusstehend] = useState<(() => void) | null>(null);

  const liste = anmeldungen.data ?? [];
  const nachPerson = useMemo(
    () => new Map((anmeldungen.data ?? []).map((a) => [a.person.id, a])),
    [anmeldungen.data],
  );
  const anmeldung = auswahl ? (nachPerson.get(auswahl.id) ?? null) : null;

  const merkeUngespeichert = useCallback((wert: boolean) => {
    ungespeichert.current = wert;
  }, []);

  /** Wechselt den Schützen; mit ungespeicherten Eingaben erst nach Rückfrage. */
  const waehle = useCallback((neu: Schuetze | null) => {
    const ausfuehren = () => {
      ungespeichert.current = false;
      setAuswahl(neu);
      if (neu) setBestaetigt(null);
      if (!neu) setDurchlauf((n) => n + 1);
    };
    if (ungespeichert.current) setAusstehend(() => ausfuehren);
    else ausfuehren();
  }, []);

  const zurSuche = useCallback(() => waehle(null), [waehle]);

  // Esc außerhalb von Eingabefeldern: zurück zur Suche (wie in der Teilnehmerverwaltung).
  useEffect(() => {
    if (!auswahl) return;
    const beiTaste = (ereignis: KeyboardEvent) => {
      if (ereignis.key !== "Escape" || ereignis.defaultPrevented) return;
      const ziel = ereignis.target as HTMLElement | null;
      if (ziel?.closest("input, textarea, select, [role=dialog], [role=listbox]")) return;
      if (document.querySelector("[role=dialog]")) return;
      zurSuche();
    };
    window.addEventListener("keydown", beiTaste);
    return () => window.removeEventListener("keydown", beiTaste);
  }, [auswahl, zurSuche]);

  const fertig = (
    ergebnis: BuchungsErgebnis,
    aenderung: AnmeldungAenderung,
    schuetze: Schuetze,
  ) => {
    ungespeichert.current = false;
    const aenderungen: string[] = [];
    if (aenderung.class_id) {
      const klasse = uebersicht.data?.classes.find((k) => k.id === aenderung.class_id);
      aenderungen.push(t("fertig.aenderung_klasse", { klasse: klasse?.short ?? "" }));
    }
    if (aenderung.start_number != null) {
      aenderungen.push(
        t("fertig.aenderung_startnummer", {
          nr: formatZahl(aenderung.start_number, {}, i18n.language),
        }),
      );
    }
    setBestaetigt({
      art: bestaetigungsArt(ergebnis.neu, ergebnis.starts.length),
      startnummer: ergebnis.anmeldung.start_number,
      name: schuetze.name,
      starts: ergebnis.starts.length,
      cents: ergebnis.starts.reduce((n, start) => n + start.fee_cents, 0),
      waehrung: uebersicht.data?.settings.currency ?? "EUR",
      aenderungen,
      startrecht: ergebnis.starts.flatMap((start) => start.start_rights ?? []),
    });
    setAuswahl(null);
    setDurchlauf((n) => n + 1);
  };

  const nachStartnummer = (text: string): Anmeldung | undefined =>
    /^\d+$/.test(text) ? liste.find((a) => a.start_number === Number(text)) : undefined;

  const sprache = i18n.language;
  const kopf = <Kopf station={station} icon={icon} turnier={turnier} onWechseln={onWechseln} />;

  if (uebersicht.isError) {
    return (
      <div className={s.seiteFluss}>
        {kopf}
        <div className="panel">
          <Fehlerzustand fehler={uebersicht.error} onErneut={() => void uebersicht.refetch()} />
        </div>
      </div>
    );
  }

  return (
    <div className={s.seite} data-layout="fenster" data-auswahl={auswahl ? "offen" : "zu"}>
      {kopf}
      <div className={s.spalten}>
        <section className={s.links} aria-label={t("schuetze.bereich")}>
          {bestaetigt && !auswahl && (
            <div
              className={`panel ${s.bestaetigt}`}
              role="status"
              data-ton={
                bestaetigt.art === "angemeldet" || bestaetigt.art === "gebucht"
                  ? "erfolg"
                  : "hinweis"
              }
            >
              <div className={s.bestaetigtNr}>
                <span className="h-label">{t("fertig.startnummer")}</span>
                <b className="num">{formatZahl(bestaetigt.startnummer, {}, sprache)}</b>
              </div>
              <div className={s.bestaetigtText}>
                <strong>
                  {bestaetigt.art === "angemeldet" || bestaetigt.art === "gebucht" ? (
                    <CircleCheck aria-hidden className={s.bestaetigtSymbol} />
                  ) : (
                    <Info aria-hidden className={s.bestaetigtSymbol} />
                  )}
                  {t(`fertig.${bestaetigt.art}`, {
                    name: bestaetigt.name,
                    was: bestaetigt.aenderungen.join(", "),
                  })}
                </strong>
                {bestaetigt.art === "ohne_start" ? (
                  <span>{t("fertig.ohne_start_text")}</span>
                ) : bestaetigt.art === "geaendert" ? (
                  <span>{t("fertig.geaendert_text")}</span>
                ) : (
                  <span>
                    {t("fertig.starts", { count: bestaetigt.starts })}
                    {" · "}
                    {t("fertig.zu_zahlen")}{" "}
                    <b className="num">
                      {formatGeld(bestaetigt.cents, bestaetigt.waehrung, sprache)}
                    </b>
                    {bestaetigt.aenderungen.length > 0 &&
                      ` · ${t("fertig.auch_geaendert", { was: bestaetigt.aenderungen.join(", ") })}`}
                  </span>
                )}
                <StartrechtHinweise meldungen={bestaetigt.startrecht} />
              </div>
              <Button
                variant="subtle"
                color="gray"
                size="md"
                aria-label={t("fertig.ausblenden")}
                onClick={() => setBestaetigt(null)}
              >
                <X aria-hidden />
              </Button>
            </div>
          )}

          {auswahl && uebersicht.data ? (
            <AnmeldungFormular
              key={auswahl.id}
              uebersicht={uebersicht.data}
              schuetze={auswahl}
              anmeldung={anmeldung}
              anmeldungen={liste}
              onFertig={(ergebnis, aenderung) => fertig(ergebnis, aenderung, auswahl)}
              onZurueck={zurSuche}
              onGeloescht={() => {
                ungespeichert.current = false;
                setAuswahl(null);
                setDurchlauf((n) => n + 1);
              }}
              onUngespeichert={merkeUngespeichert}
            />
          ) : (
            <div className={`panel ${s.suchPanel}`}>
              <div className={s.suchKopf}>
                <h2 className="h-section">{t("schuetze.titel")}</h2>
                <p className="gedaempft">{t("schuetze.suche_hinweis")}</p>
              </div>
              <PersonenSuche
                key={durchlauf}
                autoFokus={durchlauf > 0}
                onAuswahl={(person) => waehle(schuetzeAusPerson(person))}
                onNeu={(name) => setNeuePerson((alt) => ({ name, nr: (alt?.nr ?? 0) + 1 }))}
                markierung={(person) => {
                  const vorhanden = nachPerson.get(person.id);
                  return vorhanden ? (
                    <Chip ton="gruen">
                      {t("schuetze.angemeldet_nr", {
                        nr: formatZahl(vorhanden.start_number, {}, sprache),
                      })}
                    </Chip>
                  ) : null;
                }}
                vorTreffern={(text) => {
                  const treffer = nachStartnummer(text);
                  if (!treffer) return null;
                  return (
                    <button
                      type="button"
                      className={s.nummernTreffer}
                      onClick={() => waehle(schuetzeAusAnmeldung(treffer))}
                    >
                      <span className={`num ${s.nummer}`}>{treffer.start_number}</span>
                      <span className={s.nummernText}>
                        <strong>{treffer.person.name}</strong>
                        <span className="gedaempft">{t("schuetze.treffer_startnummer")}</span>
                      </span>
                    </button>
                  );
                }}
                enterVorrang={(text) => {
                  const treffer = nachStartnummer(text);
                  if (treffer) waehle(schuetzeAusAnmeldung(treffer));
                  return treffer !== undefined;
                }}
              />
            </div>
          )}
        </section>

        <Angemeldet
          uebersicht={uebersicht.data}
          abfrage={anmeldungen}
          aktivPersonId={auswahl?.id ?? null}
          onAuswahl={(eintrag) => waehle(schuetzeAusAnmeldung(eintrag))}
        />
      </div>

      <Dialog
        opened={neuePerson !== null}
        onClose={() => setNeuePerson(null)}
        withCloseButton={false}
        size="xl"
        padding={0}
        // Der Name des Dialogs kommt aus dem Titel; sichtbar ist die Überschrift des Formulars.
        title={t("schuetze.neu")}
        classNames={{ header: "nur-screenreader" }}
      >
        {neuePerson && (
          <PersonFormular
            key={neuePerson.nr}
            vorschlag={neuePerson.name}
            onAngelegt={(person) => {
              setNeuePerson(null);
              waehle(schuetzeAusPerson(person));
            }}
            onGeloescht={() => setNeuePerson(null)}
            onOeffnen={(id) => {
              setNeuePerson(null);
              void queryClient
                .fetchQuery(personAbfrage(id))
                .then((person) => waehle(schuetzeAusPerson(person)));
            }}
            onSchliessen={() => setNeuePerson(null)}
            onUngespeichert={() => undefined}
          />
        )}
      </Dialog>

      <Bestaetigung
        offen={ausstehend !== null}
        titel={t("verwerfen.titel")}
        text={anmeldung ? t("verwerfen.text_vorhanden") : t("verwerfen.text")}
        bestaetigen={t("verwerfen.bestaetigen")}
        abbrechen={t("verwerfen.weiter")}
        ton="gefahr"
        onBestaetigen={() => {
          const aktion = ausstehend;
          setAusstehend(null);
          aktion?.();
        }}
        onSchliessen={() => setAusstehend(null)}
      />
    </div>
  );
}
