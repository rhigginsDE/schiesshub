import { Button, Checkbox, NativeSelect, Radio, Skeleton, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Copy,
  FilePlus2,
  LayoutTemplate,
  type LucideIcon,
  Minus,
} from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "../../components/Dialog";
import { merkeTurnier } from "../../components/useAktivesTurnier";
import { Fehlerzustand } from "../../components/Zustand";
import { formatDatum } from "../../lib/format";
import {
  turnierListeAbfrage,
  useAusVorlageAnlegen,
  useTurnierAnlegen,
  useTurnierKopieren,
  vorlagenAbfrage,
} from "./abfragen";
import {
  geaenderteWettbewerbe,
  heute,
  merkeKopieHinweis,
  naechsterTermin,
  nameMitJahr,
  nameVergeben,
  tage,
  vorbilder,
} from "./anfang";
import a from "./aufgaben.module.css";
import { EINRICHTEN_PFAD } from "./pfade";
import { feldFehlerFuer } from "./senden";
import s from "./turnier.module.css";
import {
  type Turnier,
  type TurnierAnlage,
  type TurnierVorlage,
  VORLAGEN,
  type Vorlage,
} from "./typen";
import { UebungStarten } from "./Uebung";
import v from "./vorlagen.module.css";

const FELDER = ["name", "organizer", "date_from", "date_to", "template", "template_id"] as const;

/** Formular → Anlage für `POST /tournaments`. Leere Angaben fallen weg (eintägig, ohne Veranstalter). */
export function anlageAusFormular(werte: {
  name: string;
  organizer?: string;
  date_from: string;
  date_to: string;
  template: Vorlage;
}): TurnierAnlage {
  const anlage: TurnierAnlage = {
    name: werte.name.trim(),
    date_from: werte.date_from,
    template: werte.template,
  };
  if (werte.organizer?.trim()) anlage.organizer = werte.organizer.trim();
  if (werte.date_to && werte.date_to !== werte.date_from) anlage.date_to = werte.date_to;
  return anlage;
}

/** Wie das neue Turnier beginnt; `wahl` ist die Frage davor. */
export type Weg = "wahl" | "leer" | "kopie" | "vorlage";

interface TurnierAnlegenProps {
  offen: boolean;
  onSchliessen: () => void;
  /** Direkt mit „Wie ein früheres Turnier“ und diesem Vorbild beginnen */
  vorbild?: string;
}

/**
 * Neues Turnier in zwei Schritten: erst eine Frage („Wie möchtest du beginnen?“) mit drei Wegen,
 * dann nur die Angaben, die der Weg braucht (Name, Datum, ggf. Vorbild oder Vorlage). Danach geht
 * es in die Einrichtung mit der Aufgabenliste.
 */
export function TurnierAnlegen({ offen, onSchliessen, vorbild }: TurnierAnlegenProps) {
  const { t } = useTranslation("turnier");
  const navigate = useNavigate();
  const [weg, setWeg] = useState<Weg>(vorbild ? "kopie" : "wahl");
  const liste = useQuery(turnierListeAbfrage());
  const turniere = liste.data ?? [];

  const fertig = (turnierId: string) => {
    // Das neue Turnier ist ab jetzt das dieses Geräts (Startseite und Stationen).
    merkeTurnier(turnierId);
    onSchliessen();
    // Ohne Bereich öffnet die Einrichtung den ersten Schritt, in dem noch etwas fehlt.
    void navigate({ to: EINRICHTEN_PFAD, params: { turnierId }, search: {} });
  };
  const zurueck = () => setWeg("wahl");

  return (
    <Dialog
      opened={offen}
      onClose={onSchliessen}
      title={weg === "wahl" ? t("anlegen.titel") : t(`anlegen.weg.${weg}.titel`)}
      centered
      size="lg"
    >
      {weg === "wahl" && (
        <WegWahl
          mitKopie={turniere.length > 0}
          onWahl={setWeg}
          onAbbrechen={onSchliessen}
          onUebung={onSchliessen}
        />
      )}
      {weg === "leer" && <LeerBeginnen turniere={turniere} onZurueck={zurueck} onFertig={fertig} />}
      {weg === "kopie" && (
        <WieFrueher
          turniere={turniere}
          laedt={liste.isPending}
          vorbild={vorbild}
          onZurueck={zurueck}
          onFertig={fertig}
        />
      )}
      {weg === "vorlage" && (
        <AusVorlage turniere={turniere} onZurueck={zurueck} onFertig={fertig} />
      )}
    </Dialog>
  );
}

const WEGE: { weg: Exclude<Weg, "wahl">; icon: LucideIcon }[] = [
  { weg: "leer", icon: FilePlus2 },
  { weg: "kopie", icon: Copy },
  { weg: "vorlage", icon: LayoutTemplate },
];

function WegWahl({
  mitKopie,
  onWahl,
  onAbbrechen,
  onUebung,
}: {
  mitKopie: boolean;
  onWahl: (weg: Weg) => void;
  onAbbrechen: () => void;
  onUebung: () => void;
}) {
  const { t } = useTranslation("turnier");
  return (
    <div className={s.formular}>
      <p className={v.frage} id="anlegen-frage">
        {t("anlegen.frage")}
      </p>
      <ul className={v.wege} aria-labelledby="anlegen-frage">
        {WEGE.filter((eintrag) => eintrag.weg !== "kopie" || mitKopie).map(
          ({ weg, icon: Icon }, nr) => (
            <li key={weg}>
              <button
                type="button"
                className={v.weg}
                onClick={() => onWahl(weg)}
                data-autofocus={nr === 0 || undefined}
              >
                <span className={v.wegSymbol} aria-hidden>
                  <Icon />
                </span>
                <span className={v.wegText}>
                  <strong>{t(`anlegen.weg.${weg}.titel`)}</strong>
                  <span>{t(`anlegen.weg.${weg}.text`)}</span>
                </span>
                <ChevronRight className={v.wegPfeil} aria-hidden />
              </button>
            </li>
          ),
        )}
      </ul>
      <div className={v.unten}>
        <UebungStarten darstellung="leise" text={t("uebung.starten_kurz")} onGeoeffnet={onUebung} />
        <Button variant="default" size="md" onClick={onAbbrechen} className={v.rechts}>
          {t("aktion.abbrechen")}
        </Button>
      </div>
    </div>
  );
}

/** Fußleiste der Formulare: links zurück zur Frage, rechts die eine grüne Hauptaktion. */
function Leiste({
  onZurueck,
  knopf,
  laedt,
  gesperrt,
}: {
  onZurueck: () => void;
  knopf: string;
  laedt: boolean;
  gesperrt?: boolean;
}) {
  const { t } = useTranslation("turnier");
  return (
    <div className={v.leiste}>
      <Button
        variant="subtle"
        color="gray"
        size="md"
        leftSection={<ArrowLeft aria-hidden />}
        onClick={onZurueck}
      >
        {t("anlegen.zurueck")}
      </Button>
      <Button type="submit" size="md" loading={laedt} disabled={gesperrt} className={v.rechts}>
        {knopf}
      </Button>
    </div>
  );
}

function Fehlermeldung({ text }: { text?: string }) {
  if (!text) return null;
  return (
    <p className={s.fehlerText} role="alert">
      {text}
    </p>
  );
}

interface Termin {
  date_from: string;
  date_to: string;
  mehrtaegig: boolean;
}

/** Datum, bei Bedarf „mehrere Tage“ mit Enddatum. */
function TerminFelder({
  termin,
  fehler,
  onAendern,
}: {
  termin: Termin;
  fehler: Record<string, string>;
  onAendern: (termin: Termin) => void;
}) {
  const { t } = useTranslation("turnier");
  return (
    <>
      <div className={s.zweiSpalten}>
        <TextInput
          type="date"
          label={termin.mehrtaegig ? t("feld.datum_von") : t("feld.datum")}
          required
          size="md"
          value={termin.date_from}
          error={fehler.date_from}
          onChange={(e) => onAendern({ ...termin, date_from: e.currentTarget.value })}
        />
        {termin.mehrtaegig && (
          <TextInput
            type="date"
            label={t("feld.datum_bis")}
            size="md"
            value={termin.date_to}
            min={termin.date_from}
            error={fehler.date_to}
            onChange={(e) => onAendern({ ...termin, date_to: e.currentTarget.value })}
          />
        )}
      </div>
      <Checkbox
        size="md"
        label={t("anlegen.mehrtaegig")}
        checked={termin.mehrtaegig}
        onChange={(e) => onAendern({ ...termin, mehrtaegig: e.currentTarget.checked })}
      />
    </>
  );
}

/** Prüfung im Browser: Name fehlt oder doppelt, Datum fehlt, Enddatum vor Beginn. */
function eigeneFehler(
  t: (schluessel: string) => string,
  geprueft: boolean,
  name: string,
  termin: { date_from: string; date_to?: string; mehrtaegig?: boolean },
  turniere: readonly Turnier[],
): Record<string, string> {
  const fehler: Record<string, string> = {};
  if (nameVergeben(name, turniere)) fehler.name = t("anlegen.name_doppelt");
  else if (geprueft && !name.trim()) fehler.name = t("anlegen.name_fehlt");
  if (geprueft && !termin.date_from) fehler.date_from = t("anlegen.datum_fehlt");
  if (
    termin.mehrtaegig &&
    termin.date_to &&
    termin.date_from &&
    termin.date_to < termin.date_from
  ) {
    fehler.date_to = t("pruefung.datum_reihenfolge");
  }
  return fehler;
}

function bisDatum(termin: Termin): string | undefined {
  return termin.mehrtaegig && termin.date_to && termin.date_to !== termin.date_from
    ? termin.date_to
    : undefined;
}

// --- Leer beginnen -----------------------------------------------------------------------------

function LeerBeginnen({
  turniere,
  onZurueck,
  onFertig,
}: {
  turniere: readonly Turnier[];
  onZurueck: () => void;
  onFertig: (id: string) => void;
}) {
  const { t } = useTranslation("turnier");
  const anlegen = useTurnierAnlegen();
  const [name, setName] = useState("");
  const [art, setArt] = useState<Vorlage>("open");
  const [termin, setTermin] = useState<Termin>({
    date_from: heute(),
    date_to: "",
    mehrtaegig: false,
  });
  const [geprueft, setGeprueft] = useState(false);

  const eigene = eigeneFehler(t, geprueft, name, termin, turniere);
  const server = anlegen.isError ? feldFehlerFuer(anlegen.error, FELDER) : {};
  const fehler = { ...server, ...eigene };
  const zuruecksetzen = () => {
    if (anlegen.isError) anlegen.reset();
  };

  const senden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    setGeprueft(true);
    if (!name.trim() || !termin.date_from || Object.keys(eigene).length > 0) return;
    anlegen.mutate(
      anlageAusFormular({
        name,
        date_from: termin.date_from,
        date_to: bisDatum(termin) ?? "",
        template: art,
      }),
      { onSuccess: (turnier) => onFertig(turnier.id) },
    );
  };

  return (
    <form className={s.formular} noValidate onSubmit={senden}>
      <p className={s.hilfe}>{t("anlegen.text")}</p>
      <TextInput
        label={t("feld.name")}
        placeholder={t("feld.name_platzhalter")}
        required
        size="md"
        data-autofocus
        value={name}
        error={fehler.name}
        onChange={(e) => {
          setName(e.currentTarget.value);
          zuruecksetzen();
        }}
      />
      <TerminFelder
        termin={termin}
        fehler={fehler}
        onAendern={(neu) => {
          setTermin(neu);
          zuruecksetzen();
        }}
      />
      <Radio.Group
        label={t("anlegen.art")}
        size="md"
        value={art}
        onChange={(wert) => setArt(wert as Vorlage)}
      >
        <div className={a.arten}>
          {VORLAGEN.map((vorlage) => (
            <Radio.Card
              key={vorlage}
              value={vorlage}
              withBorder={false}
              radius="md"
              className={a.art}
              aria-label={t(`vorlage.${vorlage}.name`)}
            >
              <Radio.Indicator size="md" />
              <span className={a.artText}>
                <strong>{t(`vorlage.${vorlage}.name`)}</strong>
                <span>{t(`vorlage.${vorlage}.text`)}</span>
              </span>
            </Radio.Card>
          ))}
        </div>
      </Radio.Group>
      <Fehlermeldung text={fehler[""]} />
      <Leiste onZurueck={onZurueck} knopf={t("anlegen.knopf")} laedt={anlegen.isPending} />
    </form>
  );
}

// --- Wie ein früheres Turnier ------------------------------------------------------------------

function WieFrueher({
  turniere,
  laedt,
  vorbild,
  onZurueck,
  onFertig,
}: {
  turniere: readonly Turnier[];
  laedt: boolean;
  vorbild?: string;
  onZurueck: () => void;
  onFertig: (id: string) => void;
}) {
  const { t, i18n } = useTranslation("turnier");
  const kopieren = useTurnierKopieren();
  const auswahl = vorbilder(turniere);
  const [quelleId, setQuelleId] = useState<string | undefined>(vorbild);
  // Datum und Name folgen dem Vorbild, bis sie jemand selbst ändert.
  const [datumEigen, setDatumEigen] = useState<string | null>(null);
  const [nameEigen, setNameEigen] = useState<string | null>(null);
  const [geprueft, setGeprueft] = useState(false);

  if (laedt) return <Skeleton height={240} radius="md" />;
  const quelle = auswahl.find((x) => x.id === quelleId) ?? auswahl[0];
  if (!quelle) {
    return (
      <div className={s.formular}>
        <p className={v.hilfe}>{t("kopie.leer")}</p>
        <Leiste onZurueck={onZurueck} knopf={t("kopie.knopf")} laedt={false} gesperrt />
      </div>
    );
  }

  const datum = datumEigen ?? naechsterTermin(quelle.date_from);
  const jahr = datum.slice(0, 4) || heute().slice(0, 4);
  const name = nameEigen ?? nameMitJahr(quelle.name, jahr);
  const dauer = tage(quelle);

  const eigene = eigeneFehler(t, geprueft, name, { date_from: datum }, turniere);
  const server = kopieren.isError ? feldFehlerFuer(kopieren.error, FELDER) : {};
  const fehler = { ...server, ...eigene };
  const zuruecksetzen = () => {
    if (kopieren.isError) kopieren.reset();
  };

  const senden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    setGeprueft(true);
    if (!name.trim() || !datum || Object.keys(eigene).length > 0) return;
    kopieren.mutate(
      { quelleId: quelle.id, daten: { name: name.trim(), date_from: datum } },
      {
        onSuccess: (ergebnis) => {
          merkeKopieHinweis(ergebnis.tournament.id, {
            quelle: quelle.name,
            wettbewerbe: geaenderteWettbewerbe(ergebnis.competitions),
          });
          onFertig(ergebnis.tournament.id);
        },
      },
    );
  };

  return (
    <form className={s.formular} noValidate onSubmit={senden}>
      <NativeSelect
        label={t("kopie.quelle")}
        size="md"
        value={quelle.id}
        data-autofocus
        onChange={(e) => {
          setQuelleId(e.currentTarget.value);
          setDatumEigen(null);
          setNameEigen(null);
          zuruecksetzen();
        }}
        data={auswahl.map((turnier) => {
          const titel = turnier.is_practice
            ? t("kopie.quelle_uebung", { name: turnier.name })
            : turnier.name;
          return {
            value: turnier.id,
            label: `${titel} · ${formatDatum(turnier.date_from, i18n.language)}`,
          };
        })}
      />
      <Umfang />
      <TextInput
        label={t("feld.name")}
        required
        size="md"
        value={name}
        error={fehler.name}
        description={nameEigen === null ? t("kopie.name_hilfe") : undefined}
        inputWrapperOrder={["label", "input", "description", "error"]}
        onChange={(e) => {
          setNameEigen(e.currentTarget.value);
          zuruecksetzen();
        }}
      />
      <TextInput
        type="date"
        label={dauer > 1 ? t("kopie.erster_tag") : t("kopie.datum")}
        required
        size="md"
        value={datum}
        error={fehler.date_from}
        description={dauer > 1 ? t("kopie.dauer", { count: dauer }) : undefined}
        inputWrapperOrder={["label", "input", "description", "error"]}
        onChange={(e) => {
          setDatumEigen(e.currentTarget.value);
          zuruecksetzen();
        }}
      />
      <Fehlermeldung text={fehler[""]} />
      <Leiste onZurueck={onZurueck} knopf={t("kopie.knopf")} laedt={kopieren.isPending} />
    </form>
  );
}

/** Was beim Kopieren mitkommt und was nicht, in zwei kurzen Sätzen. */
function Umfang() {
  const { t } = useTranslation("turnier");
  const teil = (art: "mit" | "ohne", Icon: LucideIcon, titel: string, text: string): ReactNode => (
    <div className={v.umfangTeil} data-art={art}>
      <Icon aria-hidden />
      <strong>{titel}</strong>
      <span>{text}</span>
    </div>
  );
  return (
    <div className={v.umfang}>
      {teil("mit", Check, t("kopie.uebernommen"), t("kopie.uebernommen_text"))}
      {teil("ohne", Minus, t("kopie.nicht_uebernommen"), t("kopie.nicht_uebernommen_text"))}
    </div>
  );
}

// --- Aus einer Vorlage -------------------------------------------------------------------------

function vorlageVerfuegbar(vorlage: TurnierVorlage): boolean {
  return vorlage.competitions.every((w) => w.available);
}

function AusVorlage({
  turniere,
  onZurueck,
  onFertig,
}: {
  turniere: readonly Turnier[];
  onZurueck: () => void;
  onFertig: (id: string) => void;
}) {
  const { t } = useTranslation("turnier");
  const vorlagen = useQuery(vorlagenAbfrage());
  const anlegen = useAusVorlageAnlegen();
  const [vorlageId, setVorlageId] = useState<string | null>(null);
  const [nameEigen, setNameEigen] = useState<string | null>(null);
  const [termin, setTermin] = useState<Termin>({
    date_from: heute(),
    date_to: "",
    mehrtaegig: false,
  });
  const [geprueft, setGeprueft] = useState(false);

  const liste = vorlagen.data ?? [];
  const vorlage = liste.find((x) => x.id === vorlageId) ?? null;
  const jahr = (termin.date_from || heute()).slice(0, 4);
  const name =
    nameEigen ?? (vorlage ? t("aus_vorlage.name_vorschlag", { vorlage: vorlage.name, jahr }) : "");
  const eigene = eigeneFehler(t, geprueft, name, termin, turniere);
  const server = anlegen.isError ? feldFehlerFuer(anlegen.error, FELDER) : {};
  const fehler = { ...server, ...eigene };
  const zuruecksetzen = () => {
    if (anlegen.isError) anlegen.reset();
  };

  if (vorlagen.isPending) return <Skeleton height={280} radius="md" />;
  if (vorlagen.isError) {
    return <Fehlerzustand fehler={vorlagen.error} onErneut={() => void vorlagen.refetch()} />;
  }

  const senden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    setGeprueft(true);
    if (!vorlage || !name.trim() || !termin.date_from || Object.keys(eigene).length > 0) return;
    const bis = bisDatum(termin);
    anlegen.mutate(
      {
        template_id: vorlage.id,
        name: name.trim(),
        date_from: termin.date_from,
        ...(bis ? { date_to: bis } : {}),
      },
      { onSuccess: (turnier) => onFertig(turnier.id) },
    );
  };

  return (
    <form className={s.formular} noValidate onSubmit={senden}>
      {liste.length === 0 ? (
        <p className={v.hilfe}>{t("aus_vorlage.leer")}</p>
      ) : (
        <Radio.Group
          label={t("aus_vorlage.frage")}
          size="md"
          value={vorlageId}
          error={geprueft && !vorlage ? t("pruefung.pflicht") : undefined}
          onChange={(wert) => {
            setVorlageId(wert);
            zuruecksetzen();
          }}
        >
          <div className={a.arten}>
            {liste.map((eintrag, nr) => {
              const verfuegbar = vorlageVerfuegbar(eintrag);
              return (
                <Radio.Card
                  key={eintrag.id}
                  value={eintrag.id}
                  withBorder={false}
                  radius="md"
                  className={a.art}
                  disabled={!verfuegbar}
                  aria-label={eintrag.name}
                  data-autofocus={nr === 0 || undefined}
                >
                  <Radio.Indicator size="md" disabled={!verfuegbar} />
                  <span className={a.artText}>
                    <strong>{eintrag.name}</strong>
                    <span>{eintrag.description}</span>
                    <span className={v.vorlageZeile}>
                      {[
                        t("aus_vorlage.wettbewerbe", { count: eintrag.competitions.length }),
                        ...eintrag.ranges.map((stand) => stand.name),
                      ].join(" · ")}
                    </span>
                    {!verfuegbar && (
                      <span className={v.vorlageFehlt}>{t("aus_vorlage.fehlt")}</span>
                    )}
                  </span>
                </Radio.Card>
              );
            })}
          </div>
        </Radio.Group>
      )}
      {vorlage && (
        <>
          <TextInput
            label={t("feld.name")}
            required
            size="md"
            value={name}
            error={fehler.name}
            onChange={(e) => {
              setNameEigen(e.currentTarget.value);
              zuruecksetzen();
            }}
          />
          <TerminFelder
            termin={termin}
            fehler={fehler}
            onAendern={(neu) => {
              setTermin(neu);
              zuruecksetzen();
            }}
          />
          <p className={v.hilfe}>{t("aus_vorlage.hinweis")}</p>
        </>
      )}
      <Fehlermeldung text={fehler[""]} />
      <Leiste
        onZurueck={onZurueck}
        knopf={t("aus_vorlage.knopf")}
        laedt={anlegen.isPending}
        gesperrt={liste.length === 0}
      />
    </form>
  );
}
