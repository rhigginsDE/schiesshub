import { Button, CloseButton, SegmentedControl, Switch, TextInput } from "@mantine/core";
import { useDebouncedValue, useMediaQuery } from "@mantine/hooks";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Info, Shield, Trash2, TriangleAlert, UserRound } from "lucide-react";
import { type FormEvent, useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiFehler } from "../../api/client";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { type Anzeigeart, anzeigename, bereinigen } from "./anzeigename";
import {
  type Dublette,
  dublettenAbfrage,
  fehlertext,
  type Person,
  type PersonAenderung,
  type PersonNeu,
  personAendern,
  personAnlegen,
  personLoeschen,
  teilnehmerSchluessel,
  vereineAbfrage,
} from "./api";
import s from "./teilnehmer.module.css";
import { VereinFeld } from "./VereinFeld";

export interface Werte {
  name: string;
  club_id: string | null;
  /**
   * Vorgemerkter neuer Verein. Er geht als `club_name` mit der Person an den Server, der ihn in
   * derselben Transaktion anlegt: Scheitert die Person, entsteht auch kein Verein.
   */
  club_neu: string | null;
  member_no: string;
  display_mode: Anzeigeart;
  show_club: boolean;
}

export function werteAus(person: Person | undefined, vorschlag = ""): Werte {
  return {
    name: person?.name ?? vorschlag,
    club_id: person?.club_id ?? null,
    club_neu: null,
    member_no: person?.member_no ?? "",
    display_mode: person?.display_mode ?? "full",
    show_club: person?.show_club ?? true,
  };
}

/** Nur die geänderten Felder, bereinigt; leere Mitgliedsnummer = entfernen. */
export function aenderungen(basis: Werte, werte: Werte): PersonAenderung {
  const diff: PersonAenderung = {};
  const name = bereinigen(werte.name);
  if (name !== bereinigen(basis.name)) diff.name = name;
  const nr = werte.member_no.trim();
  if (nr !== basis.member_no.trim()) diff.member_no = nr || null;
  if (werte.club_neu !== null) diff.club_name = werte.club_neu;
  else if (werte.club_id !== basis.club_id) diff.club_id = werte.club_id;
  if (werte.display_mode !== basis.display_mode) diff.display_mode = werte.display_mode;
  if (werte.show_club !== basis.show_club) diff.show_club = werte.show_club;
  return diff;
}

function neuAus(werte: Werte): PersonNeu {
  return {
    name: bereinigen(werte.name),
    // Entweder ein vorhandener Verein oder der Name eines neuen, nie beides (sonst 422).
    ...(werte.club_neu !== null ? { club_name: werte.club_neu } : { club_id: werte.club_id }),
    member_no: werte.member_no.trim() || null,
    display_mode: werte.display_mode,
    show_club: werte.show_club,
  };
}

const ANZEIGEARTEN: Anzeigeart[] = ["full", "short", "hidden"];

/** Wartezeit nach der letzten Eingabe, bevor der Server nach Dubletten gefragt wird. */
export const DUBLETTEN_PAUSE_MS = 400;

interface PersonFormularProps {
  /** Vorhandene Person; fehlt sie, legt das Formular eine neue an. */
  person?: Person;
  /** Namensvorschlag für eine neue Person (z. B. der Suchtext) */
  vorschlag?: string;
  /** Rückmeldung von außen, z. B. „Person angelegt.“ */
  meldung?: string | null;
  onAngelegt: (person: Person) => void;
  onGeloescht: () => void;
  onOeffnen: (id: string) => void;
  onSchliessen: () => void;
  /** Die Person wurde inzwischen gelöscht (z. B. an einem anderen Gerät). */
  entfernt?: boolean;
  /** Meldet, ob ungespeicherte Eingaben im Formular stehen. */
  onUngespeichert: (ungespeichert: boolean) => void;
  /** Meldet, ob gerade gespeichert wird (die Eingaben sind dann unterwegs, nicht offen). */
  onSpeichert?: (laeuft: boolean) => void;
}

/** Anlegen und Ändern einer Person, mit Live-Vorschau der Anzeige und Dublettenhinweis. */
export function PersonFormular({
  person,
  vorschlag = "",
  meldung,
  entfernt = false,
  onAngelegt,
  onGeloescht,
  onOeffnen,
  onSchliessen,
  onUngespeichert,
  onSpeichert,
}: PersonFormularProps) {
  const { t } = useTranslation("teilnehmer");
  const queryClient = useQueryClient();
  const vereine = useQuery(vereineAbfrage());
  const schmal = useMediaQuery("(max-width: 560px)");
  const titelId = useId();

  // Stand des Servers, von dem aus bearbeitet wird; Eingaben liegen in `werte`.
  const [basis, setBasis] = useState<Person | undefined>(person);
  const [werte, setWerte] = useState<Werte>(() => werteAus(person, vorschlag));
  const [dublette, setDublette] = useState<Dublette | null>(null);
  const [gespeichert, setGespeichert] = useState<string | null>(meldung ?? null);
  const [nameFehlt, setNameFehlt] = useState(false);
  const [loeschenOffen, setLoeschenOffen] = useState(false);

  const ausgang = werteAus(basis, basis ? "" : vorschlag);
  const diff = aenderungen(ausgang, werte);
  const ungespeichert = Object.keys(diff).length > 0 || werte.club_neu !== null;

  // Live-Aktualisierung: Neuer Stand vom Server wird übernommen, solange nichts eingegeben ist.
  // Mit Eingaben bleibt alles stehen; ein Hinweis bietet an, den neuen Stand zu laden.
  const neuerStand =
    person !== undefined &&
    basis !== undefined &&
    Date.parse(person.updated_at) > Date.parse(basis.updated_at);
  if (neuerStand && !ungespeichert) {
    setBasis(person);
    setWerte(werteAus(person));
  }

  useEffect(() => {
    onUngespeichert(ungespeichert);
  }, [ungespeichert, onUngespeichert]);
  useEffect(() => () => onUngespeichert(false), [onUngespeichert]);

  const aendern = <K extends keyof Werte>(feld: K, wert: Werte[K]) => {
    setWerte((alt) => ({ ...alt, [feld]: wert }));
    setGespeichert(null);
    setDublette(null);
    if (feld === "name") setNameFehlt(false);
  };

  /** Vorhandenen Verein wählen oder einen neuen vormerken; das eine hebt das andere auf. */
  const vereinSetzen = (club_id: string | null, club_neu: string | null) => {
    setWerte((alt) => ({ ...alt, club_id, club_neu }));
    setGespeichert(null);
    setDublette(null);
    speichern.reset();
  };

  const merken = (neu: Person) => {
    queryClient.setQueryData(teilnehmerSchluessel.person(neu.id), neu);
    void queryClient.invalidateQueries({ queryKey: teilnehmerSchluessel.alle });
  };

  const speichern = useMutation({
    // Ein vorgemerkter Verein reist als `club_name` mit; der Server legt beides gemeinsam an.
    mutationFn: async ({ trotzdem, stand }: { trotzdem: boolean; stand: Werte }) => {
      if (!basis)
        return { neu: true as const, ergebnis: await personAnlegen(neuAus(stand), trotzdem) };
      return {
        neu: false as const,
        person: await personAendern(basis.id, aenderungen(ausgang, stand)),
      };
    },
    onSuccess: (antwort) => {
      if (antwort.neu) {
        if (antwort.ergebnis.art === "dublette") {
          setDublette(antwort.ergebnis.dublette);
          return;
        }
        merken(antwort.ergebnis.person);
        onAngelegt(antwort.ergebnis.person);
        return;
      }
      merken(antwort.person);
      setBasis(antwort.person);
      setWerte(werteAus(antwort.person));
      setGespeichert(t("formular.gespeichert"));
    },
  });

  const loeschen = useMutation({
    mutationFn: () => personLoeschen(basis?.id ?? ""),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: teilnehmerSchluessel.person(basis?.id ?? "") });
      void queryClient.invalidateQueries({ queryKey: teilnehmerSchluessel.alle });
      setLoeschenOffen(false);
      onGeloescht();
    },
    onError: (fehler) => {
      if (fehler instanceof ApiFehler && fehler.art === "nicht_gefunden") {
        setLoeschenOffen(false);
        onGeloescht();
      }
    },
  });

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    if (!bereinigen(werte.name)) {
      setNameFehlt(true);
      return;
    }
    setDublette(null);
    if (speichern.isPending) return;
    if (basis && !ungespeichert) return;
    speichern.mutate({ trotzdem: false, stand: werte });
  };

  // Mögliche Dubletten schon während der Eingabe (nur beim Anlegen): Der Server prüft wie beim
  // Speichern. Gezeigt wird nur, was zur aktuellen Eingabe gehört, nicht ein älteres Ergebnis.
  // In einem neuen Verein gibt es noch niemanden, also auch keine Dublette.
  const pruefSchluessel = JSON.stringify([
    basis || werte.club_neu !== null ? "" : bereinigen(werte.name),
    werte.club_id,
  ]);
  const [entprellt] = useDebouncedValue(pruefSchluessel, DUBLETTEN_PAUSE_MS);
  const [pruefName, pruefVerein] = JSON.parse(entprellt) as [string, string | null];
  const pruefung = useQuery(dublettenAbfrage(pruefName, pruefVerein));
  const moegliche =
    !basis && !dublette && entprellt === pruefSchluessel ? (pruefung.data?.duplicates ?? []) : [];

  const speichertGerade = speichern.isPending;
  useEffect(() => {
    onSpeichert?.(speichertGerade);
  }, [speichertGerade, onSpeichert]);
  useEffect(() => () => onSpeichert?.(false), [onSpeichert]);

  const verwerfen = () => {
    setBasis(person ?? basis);
    setWerte(werteAus(person ?? basis, (person ?? basis) ? "" : vorschlag));
    setDublette(null);
    setNameFehlt(false);
    speichern.reset();
  };

  // Vorschau: ohne Eingaben genau das, was der Server liefert; sonst dieselbe Regel lokal.
  const vereinName =
    werte.club_neu ?? vereine.data?.find((verein) => verein.id === werte.club_id)?.name ?? null;
  const vorschauName =
    basis && !ungespeichert
      ? basis.display_name
      : anzeigename(werte.name || "—", werte.display_mode);
  const vorschauVerein =
    basis && !ungespeichert ? basis.display_club : werte.show_club ? vereinName : null;

  const vereinFehler = vereinFehlerAus(
    speichern.error,
    speichern.variables?.stand.club_neu != null,
    t("vereinfeld.fehler_recht"),
  );
  const speicherFehler = !speichern.isError
    ? null
    : vereinFehler
      ? t("formular.fehler_verein")
      : (fehlertext(speichern.error) ?? t("formular.fehler_speichern"));

  return (
    <article className={`panel ${s.detailPanel}`} aria-labelledby={titelId}>
      <button type="button" className={s.zurueck} onClick={onSchliessen}>
        <ArrowLeft aria-hidden />
        {t("formular.zurueck")}
      </button>

      <header className={s.detailKopf}>
        <div className={s.detailTitel}>
          <h2 className="h-display" id={titelId}>
            {basis ? basis.name : t("formular.titel_neu")}
          </h2>
          {ungespeichert && (
            <Chip ton="warn" punkt>
              {t("formular.ungespeichert")}
            </Chip>
          )}
        </div>
        <CloseButton
          size={44}
          className={s.schliessen}
          aria-label={t("formular.schliessen")}
          onClick={onSchliessen}
        />
      </header>

      {entfernt && (
        <div className={s.hinweisKrit} role="alert">
          <strong>{t("formular.nicht_gefunden_titel")}</strong>
          <p>{t("formular.nicht_gefunden_text")}</p>
        </div>
      )}

      {neuerStand && ungespeichert && person && !entfernt && (
        <div className={s.hinweisWarn} role="status">
          <TriangleAlert aria-hidden />
          <p>{t("formular.fremd_geaendert")}</p>
          <Button
            variant="default"
            onClick={() => {
              setBasis(person);
              setWerte(werteAus(person));
            }}
          >
            {t("formular.fremd_laden")}
          </Button>
        </div>
      )}

      <form className={s.formular} onSubmit={absenden} noValidate>
        <div className={s.formRaster}>
          <div className={s.formSpalte}>
            <TextInput
              size="md"
              label={t("formular.name")}
              description={t("formular.name_hilfe")}
              value={werte.name}
              onChange={(ereignis) => aendern("name", ereignis.currentTarget.value)}
              error={nameFehlt ? t("formular.name_fehlt") : undefined}
              required
              maxLength={200}
              autoComplete="off"
              spellCheck={false}
              data-autofocus
              autoFocus={!basis}
            />
            <VereinFeld
              label={t("formular.verein")}
              wert={werte.club_id}
              neu={werte.club_neu}
              onAendern={(id) => vereinSetzen(id, null)}
              onNeu={(name) => vereinSetzen(null, name)}
              fehler={vereinFehler}
            />
            {moegliche.length > 0 && (
              <div className={s.moeglicheDublette} role="status">
                <Info aria-hidden />
                <ul>
                  {moegliche.map((kandidat) => (
                    <li key={kandidat.id}>
                      <span>
                        {t("dublette.live", {
                          name: kandidat.name,
                          verein: kandidat.club_name ?? t("suche.ohne_verein"),
                        })}
                      </span>
                      <Button
                        variant="subtle"
                        size="compact-md"
                        onClick={() => onOeffnen(kandidat.id)}
                      >
                        {t("dublette.oeffnen")}
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <TextInput
              size="md"
              label={
                <>
                  {t("formular.mitgliedsnummer")}{" "}
                  <span className={s.optional}>({t("formular.optional")})</span>
                </>
              }
              value={werte.member_no}
              onChange={(ereignis) => aendern("member_no", ereignis.currentTarget.value)}
              maxLength={50}
              autoComplete="off"
              classNames={{ input: "num" }}
            />
          </div>

          <div className={s.formSpalte}>
            <fieldset className={s.feldgruppe}>
              <legend className={s.feldLabel}>{t("formular.anzeige")}</legend>
              <span className={s.feldHilfe}>{t("formular.anzeige_hilfe")}</span>
              <SegmentedControl
                fullWidth
                orientation={schmal ? "vertical" : "horizontal"}
                value={werte.display_mode}
                onChange={(wert) => aendern("display_mode", wert as Anzeigeart)}
                data={ANZEIGEARTEN.map((art) => ({ value: art, label: t(`anzeige.${art}`) }))}
                aria-label={t("formular.anzeige")}
              />
              <Switch
                size="md"
                className={s.schalter}
                label={t("formular.verein_anzeigen")}
                description={
                  werte.club_id || werte.club_neu ? undefined : t("formular.verein_anzeigen_ohne")
                }
                checked={werte.show_club}
                onChange={(ereignis) => aendern("show_club", ereignis.currentTarget.checked)}
              />
            </fieldset>

            <figure className={`inset ${s.vorschau}`} aria-live="polite">
              <figcaption className="h-label">{t("formular.vorschau")}</figcaption>
              {vorschauName ? (
                <strong className={s.vorschauName}>{vorschauName}</strong>
              ) : (
                <strong className={`${s.vorschauName} ${s.vorschauLeer}`}>
                  <UserRound aria-hidden />
                  {t("formular.vorschau_verborgen")}
                </strong>
              )}
              <span className={s.vorschauVerein}>
                <Shield aria-hidden />
                {vorschauVerein ?? t("formular.vorschau_ohne_verein")}
              </span>
            </figure>
          </div>
        </div>

        {dublette && (
          <section
            ref={(knoten) => knoten?.scrollIntoView?.({ block: "nearest" })}
            className={s.dublette}
            aria-labelledby={`${titelId}-dublette`}
            role="alert"
          >
            <strong id={`${titelId}-dublette`}>{t("dublette.titel")}</strong>
            <p>{t("dublette.text", { count: dublette.candidates.length })}</p>
            <ul className={s.kandidaten}>
              {dublette.candidates.map((kandidat) => (
                <li key={kandidat.id}>
                  <span className={s.kandidatText}>
                    <strong>{kandidat.name}</strong>
                    <span className="gedaempft">
                      {kandidat.club_name ?? t("suche.ohne_verein")}
                      {kandidat.member_no &&
                        ` · ${t("suche.mitgliedsnummer", { nr: kandidat.member_no })}`}
                    </span>
                  </span>
                  <Button variant="default" onClick={() => onOeffnen(kandidat.id)}>
                    {t("dublette.oeffnen")}
                  </Button>
                </li>
              ))}
            </ul>
            <div>
              <Button
                variant="default"
                loading={speichern.isPending}
                onClick={() => speichern.mutate({ trotzdem: true, stand: werte })}
              >
                {t("dublette.trotzdem")}
              </Button>
            </div>
          </section>
        )}

        {speicherFehler && (
          <p className={s.fehlerZeile} role="alert">
            {speicherFehler}
          </p>
        )}

        <div className={s.aktionen}>
          {basis && !entfernt && (
            <Button
              variant="default"
              className={s.gefahr}
              leftSection={<Trash2 aria-hidden />}
              onClick={() => {
                loeschen.reset();
                setLoeschenOffen(true);
              }}
            >
              {t("formular.loeschen")}
            </Button>
          )}
          <span className={s.status} role="status">
            {gespeichert && !ungespeichert && (
              <>
                <Check aria-hidden />
                {gespeichert}
              </>
            )}
          </span>
          {ungespeichert && basis && (
            <Button variant="default" onClick={verwerfen}>
              {t("formular.verwerfen")}
            </Button>
          )}
          <Button
            type="submit"
            size="md"
            loading={speichern.isPending}
            disabled={(basis !== undefined && !ungespeichert) || dublette !== null || entfernt}
          >
            {basis ? t("formular.speichern") : t("formular.anlegen")}
          </Button>
        </div>
      </form>

      <Bestaetigung
        offen={loeschenOffen}
        titel={t("loeschen.titel")}
        text={t("loeschen.text", { name: basis?.name ?? "" })}
        bestaetigen={t("loeschen.bestaetigen")}
        abbrechen={t("loeschen.abbrechen")}
        ton="gefahr"
        laedt={loeschen.isPending}
        fehler={
          loeschen.isError
            ? `${t("loeschen.blockiert")}: ${fehlertext(loeschen.error) ?? t("fehler.titel")}`
            : undefined
        }
        onBestaetigen={() => loeschen.mutate()}
        onSchliessen={() => setLoeschenOffen(false)}
      />
    </article>
  );
}

/**
 * Fehler, der zum Vereinsfeld gehört: 403 beim Speichern mit neuem Verein heißt, dass er nicht
 * angelegt werden darf; 422 am Feld `club_name` oder `club_id` nennt der Server selbst.
 * Sonst `undefined`.
 */
export function vereinFehlerAus(
  fehler: unknown,
  mitNeuemVerein: boolean,
  ohneRecht: string,
): string | undefined {
  if (!(fehler instanceof ApiFehler)) return undefined;
  // Ohne neuen Verein heißt 403: Personen ändern ist nicht erlaubt; das gehört nicht ans Feld.
  if (fehler.art === "verboten") return mitNeuemVerein ? ohneRecht : undefined;
  return fehler.felder.find((feld) => feld.feld === "club_name" || feld.feld === "club_id")
    ?.meldung;
}
