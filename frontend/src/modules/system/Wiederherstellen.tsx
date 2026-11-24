import { Button, Checkbox, PasswordInput, Radio, Skeleton } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ArrowLeft,
  ChevronRight,
  CircleCheck,
  CircleDashed,
  CircleMinus,
  CircleX,
  HardDriveDownload,
  Info,
  LifeBuoy,
  LoaderCircle,
  Printer,
  RefreshCw,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiSenden } from "../../api/client";
import { useDarf } from "../../app/berechtigungen";
import { FehlerHinweis } from "../../components/FehlerHinweis";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { formatDatum, formatZahl } from "../../lib/format";
import { formatGroesse, formatWann, formatZeitpunkt } from "./format";
import s from "./wiederherstellen.module.css";
import {
  ANSICHTEN,
  type Ansicht,
  aktuellerSchritt,
  ausfuehrenAnfrage,
  datenUnveraendert,
  ergebnisHinweise,
  fehltInSicherung,
  grundText,
  istKurzeUnterbrechung,
  istZugangWeg,
  kopieOhnePasswort,
  type Meldung,
  meldungTexte,
  nachDerWahl,
  nachtragenMoeglich,
  orteDerQuelle,
  type Quelle,
  quellenAbfrage,
  quellenZusammenfassen,
  serverTexte,
  startAnsicht,
  statusAbfrage,
  type Uebersetzer,
  type UebersprungenerStart,
  uebersprungeneStarts,
  umschaltenLaeuft,
  type Vorschau,
  verloreneEingaben,
  WIEDERHERSTELLEN_SCHLUESSEL,
  type WiederherstellungsSchritt,
  type WiederherstellungsStatus,
  type Zugang,
} from "./wiederherstellenAblauf";

/** `t` als einfache Funktion, für die Texte nach Kennungen in wiederherstellenAblauf.ts. */
function useUebersetzer(): Uebersetzer {
  const { t } = useTranslation("system");
  return (schluessel, werte) => t(schluessel, { ...werte });
}

/** So viele Sicherungen zeigt die Auswahl, bevor „Ältere zeigen“ nötig ist. */
const QUELLEN_KURZ = 6;

/** Einstieg auf der Seite Sicherung; nur mit `backup.restore` sichtbar. */
export function WiederherstellenEinstieg() {
  const { t } = useTranslation("system");
  const darf = useDarf("backup.restore");
  if (!darf) return null;
  return (
    <section className="panel" aria-labelledby="wiederherstellen-einstieg">
      <h2 className="h-section" id="wiederherstellen-einstieg">
        {t("wiederherstellen.einstieg_titel")}
      </h2>
      <p className={s.text}>{t("wiederherstellen.einstieg_text")}</p>
      <div className={s.aktionen}>
        <Button
          component={Link}
          to="/system/sicherung/wiederherstellen"
          variant="default"
          leftSection={<LifeBuoy aria-hidden />}
        >
          {t("wiederherstellen.einstieg_knopf")}
        </Button>
      </div>
    </section>
  );
}

/** Seite „Sicherung wiederherstellen“: geführt in fünf Schritten. */
export function WiederherstellenBereich() {
  const { t } = useTranslation("system");
  const darf = useDarf("backup.restore");
  if (!darf) {
    return (
      <div className="panel">
        <Leerzustand
          icon={ShieldAlert}
          titel={t("wiederherstellen.nur_admin_titel")}
          text={t("wiederherstellen.nur_admin_text")}
        >
          <Button component={Link} to="/system/sicherung" variant="default">
            {t("wiederherstellen.zur_sicherung")}
          </Button>
        </Leerzustand>
      </div>
    );
  }
  return <Ablauf />;
}

function Ablauf() {
  const { t } = useTranslation("system");
  const queryClient = useQueryClient();
  const [gewaehlteAnsicht, setAnsicht] = useState<Ansicht | null>(null);
  const [quelle, setQuelle] = useState<Quelle | null>(null);
  const [passwort, setPasswort] = useState("");
  const [vorschau, setVorschau] = useState<Vorschau | null>(null);
  const [nachtragen, setNachtragen] = useState(true);
  const [aussperren, setAussperren] = useState(false);

  // Fortschritt beobachten, solange er zu sehen ist (oder die Seite gerade erst öffnet).
  const status = useQuery(
    statusAbfrage(gewaehlteAnsicht === null || gewaehlteAnsicht === "fortschritt"),
  );
  const ansicht = gewaehlteAnsicht ?? (status.isPending ? null : startAnsicht(status.data));
  // Das Ende der Wartung (und das Neuladen aller Daten) erfährt die App-Shell selbst: über das
  // Ereignis `backup.maintenance`, das der Server erst schickt, wenn die neuen Daten antworten,
  // und über ihr eigenes Nachfragen, solange die Wartung läuft (app/wartung.ts).

  const vorschauLaden = useMutation({
    mutationFn: (eingabe: { quelle: Quelle; passwort: string }) =>
      apiSenden<Vorschau>("POST", "/backup/restore/preview", {
        source_id: eingabe.quelle.id,
        passphrase: eingabe.quelle.needs_passphrase ? eingabe.passwort : null,
      }),
    onSuccess: (neu) => {
      setVorschau(neu);
      setAussperren(false);
      setNachtragen(true);
      setAnsicht("vorschau");
    },
  });

  const ausfuehren = useMutation({
    mutationFn: (anfrage: ReturnType<typeof ausfuehrenAnfrage>) =>
      apiSenden<WiederherstellungsStatus>("POST", "/backup/restore/execute", anfrage),
    onSuccess: (neu) => {
      queryClient.setQueryData(WIEDERHERSTELLEN_SCHLUESSEL.status, neu);
      setPasswort("");
      setAnsicht("fortschritt");
    },
  });

  const neuBeginnen = () => {
    setQuelle(null);
    setPasswort("");
    setVorschau(null);
    vorschauLaden.reset();
    ausfuehren.reset();
    void queryClient.invalidateQueries({ queryKey: WIEDERHERSTELLEN_SCHLUESSEL.quellen });
    setAnsicht("waehlen");
  };

  const waehlen = (neu: Quelle) => {
    setQuelle(neu);
    vorschauLaden.reset();
    const weiter = nachDerWahl(neu);
    if (weiter === "vorschau") vorschauLaden.mutate({ quelle: neu, passwort: "" });
    else setAnsicht(weiter);
  };

  return (
    <>
      <section className="panel" aria-labelledby="wiederherstellen-titel">
        <div className={s.kopf}>
          <h2 className="h-section" id="wiederherstellen-titel">
            {t("wiederherstellen.titel")}
          </h2>
          {ansicht !== "fortschritt" && (
            <Button
              component={Link}
              to="/system/sicherung"
              variant="subtle"
              color="gray"
              leftSection={<ArrowLeft aria-hidden />}
            >
              {t("wiederherstellen.zur_sicherung")}
            </Button>
          )}
        </div>
        {ansicht && <Schrittleiste aktiv={ansicht} />}
      </section>

      {ansicht === null ? (
        <Skeleton height={320} radius="lg" />
      ) : ansicht === "waehlen" ? (
        <Waehlen
          status={status.data}
          gewaehlt={quelle}
          laedt={vorschauLaden.isPending}
          fehler={vorschauLaden.error}
          onWeiter={waehlen}
          onFortschritt={() => setAnsicht("fortschritt")}
        />
      ) : ansicht === "passwort" && quelle ? (
        <Passwort
          quelle={quelle}
          passwort={passwort}
          onPasswort={setPasswort}
          laedt={vorschauLaden.isPending}
          fehler={vorschauLaden.error}
          onPruefen={() => vorschauLaden.mutate({ quelle, passwort })}
          onKopie={(kopie) => {
            setQuelle(kopie);
            setPasswort("");
            vorschauLaden.mutate({ quelle: kopie, passwort: "" });
          }}
          onZurueck={neuBeginnen}
        />
      ) : ansicht === "vorschau" && vorschau ? (
        <VorschauAnsicht
          vorschau={vorschau}
          nachtragen={nachtragen}
          onNachtragen={setNachtragen}
          aussperren={aussperren}
          onAussperren={setAussperren}
          onWeiter={() => setAnsicht("bestaetigen")}
          onZurueck={neuBeginnen}
        />
      ) : ansicht === "bestaetigen" && vorschau ? (
        <Bestaetigen
          vorschau={vorschau}
          nachtragen={nachtragen}
          laedt={ausfuehren.isPending}
          fehler={ausfuehren.error}
          onAusfuehren={() =>
            ausfuehren.mutate(ausfuehrenAnfrage(vorschau, passwort, nachtragen, aussperren))
          }
          onZurueck={() => {
            ausfuehren.reset();
            setAnsicht("vorschau");
          }}
        />
      ) : ansicht === "fortschritt" ? (
        <Fortschritt
          status={status.data}
          fehler={status.error}
          laedt={status.isPending}
          onNeu={neuBeginnen}
        />
      ) : (
        // Zwischenstand ohne Daten (z. B. nach Neuladen mitten im Ablauf): von vorn.
        <Waehlen
          status={status.data}
          gewaehlt={null}
          laedt={false}
          fehler={null}
          onWeiter={waehlen}
          onFortschritt={() => setAnsicht("fortschritt")}
        />
      )}
    </>
  );
}

// --- Schrittleiste ------------------------------------------------------------------

function Schrittleiste({ aktiv }: { aktiv: Ansicht }) {
  const { t } = useTranslation("system");
  const index = ANSICHTEN.indexOf(aktiv);
  return (
    <nav aria-label={t("wiederherstellen.schritte_beschriftung")}>
      <ol className={s.leiste}>
        {ANSICHTEN.map((ansicht, i) => {
          const zustand = i < index ? "erledigt" : i === index ? "aktiv" : "offen";
          return (
            <li
              key={ansicht}
              className={s.leistenSchritt}
              data-zustand={zustand}
              aria-current={zustand === "aktiv" ? "step" : undefined}
            >
              <span className={`${s.leistenNr} num`} aria-hidden>
                {i + 1}
              </span>
              <span className={s.leistenText}>{t(`wiederherstellen.schritt.${ansicht}`)}</span>
            </li>
          );
        })}
      </ol>
      <p className={s.leisteKurz} aria-hidden>
        {t("wiederherstellen.schritt_nummer", { nummer: index + 1, gesamt: ANSICHTEN.length })}:{" "}
        {t(`wiederherstellen.schritt.${aktiv}`)}
      </p>
    </nav>
  );
}

// --- a) Sicherung wählen ------------------------------------------------------------

function ortText(t: (schluessel: string) => string, ort: Quelle["location"]): string {
  return t(`wiederherstellen.ort_${ort}`);
}

function Waehlen({
  status,
  gewaehlt,
  laedt,
  fehler,
  onWeiter,
  onFortschritt,
}: {
  status: WiederherstellungsStatus | undefined;
  gewaehlt: Quelle | null;
  laedt: boolean;
  fehler: unknown;
  onWeiter: (quelle: Quelle) => void;
  onFortschritt: () => void;
}) {
  const { t, i18n } = useTranslation("system");
  const sprache = i18n.language;
  const quellen = useQuery(quellenAbfrage());
  const [auswahl, setAuswahl] = useState<string | null>(gewaehlt?.id ?? null);
  const [alle, setAlle] = useState(false);
  const [fehlt, setFehlt] = useState(false);

  const liste = quellenZusammenfassen(quellen.data?.sources ?? []);
  const sichtbar = alle ? liste : liste.slice(0, QUELLEN_KURZ);
  // Eine Auswahl unter „Ältere“ bleibt sichtbar.
  const gewaehlteQuelle = liste.find((quelle) => quelle.id === auswahl) ?? null;
  if (gewaehlteQuelle && !sichtbar.includes(gewaehlteQuelle)) sichtbar.push(gewaehlteQuelle);

  const weiter = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    if (!gewaehlteQuelle) {
      setFehlt(true);
      return;
    }
    onWeiter(gewaehlteQuelle);
  };

  const letzte =
    status && (status.state === "succeeded" || status.state === "failed") && status.finished_at
      ? status
      : null;

  return (
    <section className="panel" aria-labelledby="wiederherstellen-waehlen">
      <form className={s.schritt} onSubmit={weiter} noValidate>
        <div className={s.abschnitt}>
          <h3 className="h-section" id="wiederherstellen-waehlen">
            {t("wiederherstellen.waehlen_titel")}
          </h3>
          <p className={s.text}>{t("wiederherstellen.waehlen_text")}</p>
        </div>

        {letzte && (
          <div className={`${s.kasten} ${letzte.state === "succeeded" ? s.gut : s.krit}`}>
            {letzte.state === "succeeded" ? <CircleCheck aria-hidden /> : <CircleX aria-hidden />}
            <div className={s.kastenInhalt}>
              <span>
                {t("wiederherstellen.letzte", {
                  zustand:
                    letzte.state === "succeeded"
                      ? t("wiederherstellen.letzte_ok")
                      : t("wiederherstellen.letzte_fehler"),
                  zeit: formatWann(letzte.finished_at ?? "", new Date(), sprache),
                })}
              </span>
              <div>
                <Button variant="default" onClick={onFortschritt}>
                  {t("wiederherstellen.letzte_ansehen")}
                </Button>
              </div>
            </div>
          </div>
        )}

        {quellen.isPending ? (
          <Skeleton height={240} radius="md" />
        ) : quellen.isError ? (
          <Fehlerzustand fehler={quellen.error} onErneut={() => void quellen.refetch()} />
        ) : quellen.data.restore_running ? (
          <div className={`${s.kasten} ${s.info}`}>
            <Info aria-hidden />
            <div className={s.kastenInhalt}>
              <strong>{t("wiederherstellen.laeuft_schon")}</strong>
              <div>
                <Button onClick={onFortschritt}>
                  {t("wiederherstellen.laeuft_schon_ansehen")}
                </Button>
              </div>
            </div>
          </div>
        ) : liste.length === 0 ? (
          <Leerzustand
            icon={HardDriveDownload}
            titel={t("wiederherstellen.leer_titel")}
            text={
              quellen.data.usb_present
                ? t("wiederherstellen.leer_text")
                : t("wiederherstellen.leer_text_ohne_stick")
            }
          >
            <Button
              variant="default"
              leftSection={<RefreshCw aria-hidden />}
              loading={quellen.isFetching}
              onClick={() => void quellen.refetch()}
            >
              {t("wiederherstellen.neu_suchen")}
            </Button>
          </Leerzustand>
        ) : (
          <>
            {!quellen.data.usb_present && (
              <div className={`${s.kasten} ${s.warn}`}>
                <TriangleAlert aria-hidden />
                <div className={s.kastenInhalt}>
                  <span>{t("wiederherstellen.stick_fehlt")}</span>
                </div>
              </div>
            )}
            <Radio.Group
              value={auswahl}
              onChange={(wert) => {
                setAuswahl(wert);
                setFehlt(false);
              }}
              error={fehlt ? t("wiederherstellen.fehler_keine_wahl") : undefined}
            >
              <div className={s.quellen}>
                {sichtbar.map((quelle) => (
                  <QuelleKarte key={quelle.id} quelle={quelle} />
                ))}
              </div>
            </Radio.Group>
            <FehlerHinweis fehler={fehler} />
            <div className={s.aktionen}>
              <Button type="submit" loading={laedt}>
                {t("wiederherstellen.weiter")}
              </Button>
              {liste.length > QUELLEN_KURZ && !alle && (
                <Button variant="default" onClick={() => setAlle(true)}>
                  {t("wiederherstellen.mehr", {
                    anzahl: formatZahl(liste.length - QUELLEN_KURZ, {}, sprache),
                  })}
                </Button>
              )}
              <Button
                variant="subtle"
                color="gray"
                leftSection={<RefreshCw aria-hidden />}
                loading={quellen.isFetching && !quellen.isPending}
                onClick={() => void quellen.refetch()}
              >
                {t("wiederherstellen.neu_suchen")}
              </Button>
            </div>
            {laedt && <p className={s.klein}>{t("wiederherstellen.liest")}</p>}
          </>
        )}
      </form>
    </section>
  );
}

function QuelleKarte({ quelle }: { quelle: Quelle }) {
  const { t, i18n } = useTranslation("system");
  const sprache = i18n.language;
  const merkmale = [
    formatGroesse(quelle.size_bytes, sprache),
    quelle.needs_passphrase && t("wiederherstellen.passwort_noetig"),
    // Ohne mitgesicherte Schlüssel lassen sich die Namen nur mit den Schlüsseln dieses Servers lesen.
    !quelle.contains_keys && t("wiederherstellen.ohne_schluessel"),
    !quelle.checksum_present && t("wiederherstellen.ohne_pruefsumme"),
    quelle.journal_available && t("wiederherstellen.nachtragen_moeglich"),
  ].filter(Boolean);
  return (
    <Radio.Card value={quelle.id} className={s.quelle} radius="md">
      <Radio.Indicator className={s.quelleIndikator} />
      <span className={s.quelleInhalt}>
        <span className={s.quelleZeile}>
          <span className={`${s.quelleZeit} num`}>
            {formatZeitpunkt(quelle.created_at, sprache)}
          </span>
          <span className={s.quelleWann}>
            {new Intl.ListFormat(sprache, { type: "conjunction" }).format(
              orteDerQuelle(quelle).map((ort) => t(`wiederherstellen.orte.${ort}`)),
            )}
          </span>
        </span>
        <span className={s.quelleMerkmale}>{merkmale.join(" · ")}</span>
      </span>
    </Radio.Card>
  );
}

// --- b) Passwort ------------------------------------------------------------------------

function Passwort({
  quelle,
  passwort,
  onPasswort,
  laedt,
  fehler,
  onPruefen,
  onKopie,
  onZurueck,
}: {
  quelle: Quelle;
  passwort: string;
  onPasswort: (wert: string) => void;
  laedt: boolean;
  fehler: unknown;
  onPruefen: () => void;
  /** Dieselbe Sicherung vom Server, ohne Passwort */
  onKopie: (kopie: Quelle) => void;
  onZurueck: () => void;
}) {
  const { t, i18n } = useTranslation("system");
  const [leer, setLeer] = useState(false);
  const kopie = kopieOhnePasswort(quelle);
  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    if (!passwort) {
      setLeer(true);
      return;
    }
    onPruefen();
  };
  return (
    <section className="panel" aria-labelledby="wiederherstellen-passwort">
      <form className={s.schritt} onSubmit={absenden} noValidate>
        <div className={s.abschnitt}>
          <h3 className="h-section" id="wiederherstellen-passwort">
            {t("wiederherstellen.passwort_titel")}
          </h3>
          <p className={s.text}>
            {t("wiederherstellen.gewaehlt", {
              zeit: formatZeitpunkt(quelle.created_at, i18n.language),
              ort: ortText(t, quelle.location),
            })}
          </p>
          <p className={s.text}>{t("wiederherstellen.passwort_text")}</p>
        </div>
        <div className={s.formular}>
          <PasswordInput
            visibilityToggleButtonProps={{ "aria-label": t("shell:sichtbar_umschalten") }}
            size="md"
            label={t("wiederherstellen.passwort_feld")}
            value={passwort}
            onChange={(e) => {
              onPasswort(e.currentTarget.value);
              setLeer(false);
            }}
            error={leer ? t("wiederherstellen.passwort_fehlt") : undefined}
            autoComplete="current-password"
            data-autofocus
            autoFocus
          />
          <FehlerHinweis fehler={fehler} />
        </div>
        <div className={s.aktionen}>
          <Button type="submit" loading={laedt}>
            {t("wiederherstellen.pruefen")}
          </Button>
          <Button variant="default" onClick={onZurueck} disabled={laedt}>
            {t("wiederherstellen.andere_waehlen")}
          </Button>
        </div>
        {laedt && <p className={s.klein}>{t("wiederherstellen.liest")}</p>}
        {kopie && (
          <div className={`${s.abschnitt} ${s.nebenweg}`}>
            <h4 className={s.abschnittTitel}>{t("wiederherstellen.passwort_vergessen_titel")}</h4>
            <p className={s.text}>{t("wiederherstellen.passwort_vergessen_text")}</p>
            <div>
              <Button variant="default" onClick={() => onKopie(kopie)} disabled={laedt}>
                {t("wiederherstellen.passwort_vergessen_knopf")}
              </Button>
            </div>
          </div>
        )}
      </form>
    </section>
  );
}

// --- c) Vorschau --------------------------------------------------------------------------

function Kasten({
  ton,
  icon,
  children,
}: {
  ton?: "krit" | "warn" | "gut" | "info";
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={[s.kasten, ton && s[ton]].filter(Boolean).join(" ")}>
      {icon}
      <div className={s.kastenInhalt}>{children}</div>
    </div>
  );
}

function VorschauAnsicht({
  vorschau,
  nachtragen,
  onNachtragen,
  aussperren,
  onAussperren,
  onWeiter,
  onZurueck,
}: {
  vorschau: Vorschau;
  nachtragen: boolean;
  onNachtragen: (wert: boolean) => void;
  aussperren: boolean;
  onAussperren: (wert: boolean) => void;
  onWeiter: () => void;
  onZurueck: () => void;
}) {
  const { t, i18n } = useTranslation("system");
  const uebersetzen = useUebersetzer();
  const sprache = i18n.language;
  const zahl = (wert: number) => formatZahl(wert, {}, sprache);
  const [aussperrenFehlt, setAussperrenFehlt] = useState(false);
  const { access: zugang } = vorschau;
  const zeit = formatZeitpunkt(vorschau.created_at ?? vorschau.source.created_at, sprache);
  const hinweise = meldungTexte(vorschau.note_items, uebersetzen);
  const ort = ortText(t, vorschau.source.location);

  const weiter = () => {
    if (zugang.lockout_risk && !aussperren) {
      setAussperrenFehlt(true);
      return;
    }
    onWeiter();
  };

  if (!vorschau.restorable) {
    return (
      <section className="panel" aria-labelledby="wiederherstellen-vorschau">
        <div className={s.schritt}>
          <div className={s.abschnitt}>
            <h3 className="h-section" id="wiederherstellen-vorschau">
              {t("wiederherstellen.vorschau_titel")}
            </h3>
            <p className={s.text}>{t("wiederherstellen.gewaehlt", { zeit, ort })}</p>
          </div>
          <Kasten ton="krit" icon={<CircleX aria-hidden />}>
            <strong>{t("wiederherstellen.nicht_moeglich_titel")}</strong>
            <ul>
              {meldungTexte(vorschau.problem_items, uebersetzen).map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
            <span>{t("wiederherstellen.nicht_moeglich_text")}</span>
          </Kasten>
          <Einzelheiten
            zeilen={[
              ...serverTexte(vorschau.problem_items),
              ...serverTexte(vorschau.note_items),
              `${t("wiederherstellen.datei")}: ${vorschau.source.file_name}`,
            ]}
          />
          <div className={s.aktionen}>
            <Button onClick={onZurueck}>{t("wiederherstellen.andere_waehlen")}</Button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="wiederherstellen-vorschau">
      <div className={s.schritt}>
        <div className={s.abschnitt}>
          <h3 className="h-section" id="wiederherstellen-vorschau">
            {t("wiederherstellen.vorschau_titel")}
          </h3>
          <p className={s.text}>
            {t("wiederherstellen.gewaehlt", { zeit, ort })}
            {vorschau.persons !== null &&
              ` · ${t("wiederherstellen.teilnehmer", { count: vorschau.persons, anzahl: zahl(vorschau.persons) })}`}
          </p>
          {vorschau.schema_check.state === "older" && (
            <p className={s.klein}>{t("wiederherstellen.aelter")}</p>
          )}
        </div>

        {vorschau.tournaments.length === 0 ? (
          <p className={s.text}>{t("wiederherstellen.turniere_keine")}</p>
        ) : (
          <ul className={`inset ${s.turniere}`} style={{ padding: "0 14px" }}>
            {vorschau.tournaments.map((turnier) => (
              <li key={turnier.id} className={s.turnier}>
                <span className={s.turnierName}>{turnier.name}</span>
                <span className="gedaempft">
                  {t(`wiederherstellen.turnier_status.${turnier.status}`, {
                    defaultValue: turnier.status,
                  })}
                  {turnier.date_from && (
                    <span className="num"> · {formatDatum(turnier.date_from, sprache)}</span>
                  )}
                </span>
                <span className={s.turnierZahlen}>
                  {t("wiederherstellen.turnier_zeile", {
                    starts: zahl(turnier.starts),
                    fertig: zahl(turnier.final_results),
                  })}
                </span>
              </li>
            ))}
          </ul>
        )}

        <Vergleich vorschau={vorschau} nachtragen={nachtragen} onNachtragen={onNachtragen} />

        <div className={s.abschnitt}>
          <h4 className={s.abschnittTitel}>{t("wiederherstellen.ersetzt_titel")}</h4>
          <ul className={s.liste}>
            <li>{t("wiederherstellen.ersetzt_text")}</li>
            <li>{t("wiederherstellen.vorher_gesichert")}</li>
            <li>{t("wiederherstellen.bleibt")}</li>
            {/* Ist Koppeln und PIN weder jetzt noch danach Pflicht, sagt das „Dein Zugang danach“. */}
            {zugang.enforced_now && <li>{t("wiederherstellen.pin_bleibt")}</li>}
            {zugang.enforced_after && !zugang.enforced_now && (
              <li>{t("wiederherstellen.pin_wird_pflicht")}</li>
            )}
          </ul>
        </div>

        <ZugangDanach zugang={zugang}>
          <Checkbox
            size="md"
            checked={aussperren}
            onChange={(e) => {
              onAussperren(e.currentTarget.checked);
              if (e.currentTarget.checked) setAussperrenFehlt(false);
            }}
            label={t("wiederherstellen.aussperren_bestaetigen")}
            error={aussperrenFehlt ? t("wiederherstellen.aussperren_fehlt") : undefined}
          />
        </ZugangDanach>

        {hinweise.length > 0 && (
          <div className={s.abschnitt}>
            <h4 className={s.abschnittTitel}>{t("wiederherstellen.hinweise_titel")}</h4>
            <ul className={s.liste}>
              {hinweise.map((hinweis) => (
                <li key={hinweis}>{hinweis}</li>
              ))}
            </ul>
          </div>
        )}

        <Einzelheiten
          zeilen={[
            vorschau.comparison.summary_de,
            vorschau.schema_check.message_de,
            vorschau.keys.message_de,
            ...serverTexte(zugang.reasons),
            ...serverTexte(vorschau.note_items),
            `${t("wiederherstellen.datei")}: ${vorschau.source.file_name}`,
          ]}
        />

        <div className={s.aktionen}>
          <Button onClick={weiter}>{t("wiederherstellen.weiter_bestaetigen")}</Button>
          <Button variant="default" onClick={onZurueck}>
            {t("wiederherstellen.andere_waehlen")}
          </Button>
        </div>
      </div>
    </section>
  );
}

function Vergleich({
  vorschau,
  nachtragen,
  onNachtragen,
}: {
  vorschau: Vorschau;
  nachtragen: boolean;
  onNachtragen?: (wert: boolean) => void;
}) {
  const { t, i18n } = useTranslation("system");
  const zahl = (wert: number) => formatZahl(wert, {}, i18n.language);
  const v = vorschau.comparison;
  const verloren = verloreneEingaben(vorschau, nachtragen);
  const nichts = v.events_since_backup === 0 && v.starts_since_backup === 0;
  const gruende = [
    v.lost_start_missing > 0 &&
      t("wiederherstellen.grund_start_fehlt", { anzahl: zahl(v.lost_start_missing) }),
    v.lost_not_in_journal > 0 &&
      t("wiederherstellen.grund_nicht_mitgeschrieben", { anzahl: zahl(v.lost_not_in_journal) }),
    v.lost_conflict > 0 &&
      t("wiederherstellen.grund_passt_nicht", { anzahl: zahl(v.lost_conflict) }),
  ].filter((grund): grund is string => Boolean(grund));

  return (
    <div className={s.abschnitt}>
      <h4 className={s.abschnittTitel}>{t("wiederherstellen.vergleich_titel")}</h4>
      {nichts ? (
        <p className={s.text}>{t("wiederherstellen.vergleich_gleich")}</p>
      ) : (
        <ul className={s.liste}>
          {v.events_since_backup > 0 && (
            <li>
              {t("wiederherstellen.vergleich_eingaben", {
                count: v.events_since_backup,
                anzahl: zahl(v.events_since_backup),
              })}
              {nachtragen && v.events_from_journal > 0 && (
                <>
                  {" "}
                  {t("wiederherstellen.vergleich_nachgetragen", {
                    anzahl: zahl(v.events_from_journal),
                  })}
                </>
              )}
            </li>
          )}
          {verloren > 0 && (
            <li className={s.schlecht}>
              {t("wiederherstellen.vergleich_verloren", {
                count: verloren,
                anzahl: zahl(verloren),
              })}
              {nachtragen && gruende.length > 0 && (
                <ul>
                  {gruende.map((grund) => (
                    <li key={grund}>{grund}</li>
                  ))}
                </ul>
              )}
            </li>
          )}
          {v.starts_since_backup > 0 && (
            <li>
              {t("wiederherstellen.vergleich_starts", {
                count: v.starts_since_backup,
                anzahl: zahl(v.starts_since_backup),
              })}
            </li>
          )}
          <li>{t("wiederherstellen.vergleich_sonst")}</li>
        </ul>
      )}
      {onNachtragen && nachtragenMoeglich(vorschau) && (
        <Checkbox
          size="md"
          checked={nachtragen}
          onChange={(e) => onNachtragen(e.currentTarget.checked)}
          label={t("wiederherstellen.nachtragen")}
          description={
            nachtragen
              ? t("wiederherstellen.nachtragen_hinweis")
              : t("wiederherstellen.nachtragen_aus")
          }
        />
      )}
    </div>
  );
}

/** Kennungen, die erklären, warum du danach nicht mehr in die Verwaltung kommst. */
const SPERR_GRUENDE: ReadonlySet<string> = new Set(["lockout", "enforcement_on_after_restore"]);

/**
 * Was nach der Wiederherstellung mit deinem Zugang geschieht, nach den Kennungen des Servers.
 * `children` ist die Bestätigung, die bei drohendem Aussperren nötig ist.
 */
function ZugangDanach({ zugang, children }: { zugang: Zugang; children: ReactNode }) {
  const { t, i18n } = useTranslation("system");
  const uebersetzen = useUebersetzer();
  const fehlt = fehltInSicherung(zugang);
  const was =
    fehlt.length > 0
      ? new Intl.ListFormat(i18n.language, { type: "conjunction" }).format(
          fehlt.map((teil) => t(`wiederherstellen.fehlt.${teil}`)),
        )
      : t("wiederherstellen.fehlt.unbekannt");
  const texte = (meldungen: Meldung[]) => meldungTexte(meldungen, uebersetzen, { was });

  const gruende = zugang.reasons ?? [];
  const sperre = gruende.filter((grund) => zugang.lockout_risk && SPERR_GRUENDE.has(grund.code));
  const pin = gruende.filter((grund) => grund.code === "pin_changed");
  const sonst = gruende.filter((grund) => !sperre.includes(grund) && !pin.includes(grund));
  if (gruende.length === 0 && !zugang.lockout_risk) return null;

  return (
    <div className={s.abschnitt}>
      <h4 className={s.abschnittTitel}>{t("wiederherstellen.zugang_titel")}</h4>
      {sonst.length > 0 && (
        <ul className={s.liste}>
          {texte(sonst).map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      )}
      {pin.length > 0 && (
        <Kasten ton="warn" icon={<TriangleAlert aria-hidden />}>
          {texte(pin).map((text) => (
            <span key={text}>{text}</span>
          ))}
        </Kasten>
      )}
      {zugang.lockout_risk && (
        <Kasten ton="krit" icon={<ShieldAlert aria-hidden />}>
          <strong>{t("wiederherstellen.aussperren_titel")}</strong>
          {texte(sperre).map((text) => (
            <span key={text}>{text}</span>
          ))}
          <span>{t("wiederherstellen.aussperren_text")}</span>
          {children}
        </Kasten>
      )}
    </div>
  );
}

function Einzelheiten({ zeilen }: { zeilen: readonly (string | null | undefined)[] }) {
  const { t } = useTranslation("system");
  const sichtbar = zeilen.filter((zeile): zeile is string => Boolean(zeile));
  if (sichtbar.length === 0) return null;
  return (
    <details className={s.einzelheiten}>
      <summary>
        <ChevronRight aria-hidden />
        {t("wiederherstellen.einzelheiten")}
      </summary>
      <ul>
        {sichtbar.map((zeile) => (
          <li key={zeile}>{zeile}</li>
        ))}
      </ul>
    </details>
  );
}

// --- d) Bestätigen ----------------------------------------------------------------------

function Bestaetigen({
  vorschau,
  nachtragen,
  laedt,
  fehler,
  onAusfuehren,
  onZurueck,
}: {
  vorschau: Vorschau;
  nachtragen: boolean;
  laedt: boolean;
  fehler: unknown;
  onAusfuehren: () => void;
  onZurueck: () => void;
}) {
  const { t, i18n } = useTranslation("system");
  const sprache = i18n.language;
  const [ersetzen, setErsetzen] = useState(false);
  const [fehlt, setFehlt] = useState(false);
  const verloren = verloreneEingaben(vorschau, nachtragen);
  const zeit = formatZeitpunkt(vorschau.created_at ?? vorschau.source.created_at, sprache);

  const los = () => {
    if (!ersetzen) {
      setFehlt(true);
      return;
    }
    onAusfuehren();
  };

  return (
    <section className="panel" aria-labelledby="wiederherstellen-bestaetigen">
      <div className={s.schritt}>
        <h3 className="h-section" id="wiederherstellen-bestaetigen">
          {t("wiederherstellen.bestaetigen_titel")}
        </h3>
        <Kasten ton="krit" icon={<TriangleAlert aria-hidden />}>
          <strong>{t("wiederherstellen.bestaetigen_text", { zeit })}</strong>
          <ul>
            {verloren > 0 && (
              <li>
                {t("wiederherstellen.vergleich_verloren", {
                  count: verloren,
                  anzahl: formatZahl(verloren, {}, sprache),
                })}
              </li>
            )}
            {vorschau.comparison.starts_since_backup > 0 && (
              <li>
                {t("wiederherstellen.vergleich_starts", {
                  count: vorschau.comparison.starts_since_backup,
                  anzahl: formatZahl(vorschau.comparison.starts_since_backup, {}, sprache),
                })}
              </li>
            )}
            {vorschau.access.lockout_risk && <li>{t("wiederherstellen.aussperren_titel")}</li>}
            <li>{t("wiederherstellen.bestaetigen_sperre")}</li>
            <li>{t("wiederherstellen.vorher_gesichert")}</li>
          </ul>
        </Kasten>
        <Checkbox
          size="md"
          checked={ersetzen}
          onChange={(e) => {
            setErsetzen(e.currentTarget.checked);
            if (e.currentTarget.checked) setFehlt(false);
          }}
          label={t("wiederherstellen.ersetzen_bestaetigen")}
          error={fehlt ? t("wiederherstellen.ersetzen_fehlt") : undefined}
        />
        <FehlerHinweis fehler={fehler} />
        <div className={s.aktionen}>
          {/* Gefährliche Aktion: Meldefarbe „kritisch“, nicht grün. */}
          <Button className={s.gefahr} loading={laedt} onClick={los}>
            {t("wiederherstellen.ausfuehren")}
          </Button>
          <Button variant="default" onClick={onZurueck} disabled={laedt}>
            {t("wiederherstellen.zurueck_vorschau")}
          </Button>
        </div>
      </div>
    </section>
  );
}

// --- e) Fortschritt -----------------------------------------------------------------------

const SYMBOL: Record<WiederherstellungsSchritt["state"], typeof CircleCheck> = {
  pending: CircleDashed,
  running: LoaderCircle,
  done: CircleCheck,
  skipped: CircleMinus,
  failed: CircleX,
};

function Fortschritt({
  status,
  fehler,
  laedt,
  onNeu,
}: {
  status: WiederherstellungsStatus | undefined;
  fehler: unknown;
  laedt: boolean;
  onNeu: () => void;
}) {
  const { t, i18n } = useTranslation("system");
  const sprache = i18n.language;

  if (laedt) return <Skeleton height={320} radius="lg" />;

  if (istZugangWeg(fehler)) {
    return (
      <section className="panel" aria-labelledby="wiederherstellen-fortschritt">
        <div className={s.schritt}>
          <h3 className="h-section" id="wiederherstellen-fortschritt">
            {t("wiederherstellen.zugang_weg_titel")}
          </h3>
          <p className={s.text}>{t("wiederherstellen.zugang_weg_text")}</p>
          <div className={s.aktionen}>
            <Button component={Link} to="/anmelden">
              {t("wiederherstellen.zum_einloggen")}
            </Button>
          </div>
        </div>
      </section>
    );
  }

  if (!status) {
    return (
      <div className="panel">
        <Fehlerzustand fehler={fehler} />
      </div>
    );
  }

  const unterbrochen = Boolean(fehler) && istKurzeUnterbrechung(fehler);
  const fertig = status.state === "succeeded";
  const gescheitert = status.state === "failed";
  const titel = fertig
    ? t("wiederherstellen.fertig_titel")
    : gescheitert
      ? t("wiederherstellen.fehler_titel")
      : t("wiederherstellen.laeuft_titel");
  const schritt = aktuellerSchritt(status);

  return (
    <section className="panel" aria-labelledby="wiederherstellen-fortschritt">
      <div className={s.schritt}>
        <div className={s.abschnitt} aria-live="polite">
          <h3 className="h-section" id="wiederherstellen-fortschritt">
            {titel}
          </h3>
          {status.state === "running" && (
            <p className={s.text}>{t("wiederherstellen.laeuft_text")}</p>
          )}
          {(unterbrochen || umschaltenLaeuft(status)) && status.state === "running" && (
            <Kasten ton="info" icon={<Info aria-hidden />}>
              <span>{t("wiederherstellen.umschalten")}</span>
            </Kasten>
          )}
        </div>

        {fertig && status.result && <Ergebnis status={status} />}

        {gescheitert && (
          <Kasten ton="krit" icon={<CircleX aria-hidden />}>
            {status.error_de && <strong>{status.error_de}</strong>}
            <span>
              {datenUnveraendert(status)
                ? t("wiederherstellen.fehler_unveraendert")
                : t("wiederherstellen.fehler_betreuer")}
            </span>
          </Kasten>
        )}

        <ol className={`inset ${s.schritte}`} aria-label={t("wiederherstellen.fortschritt")}>
          {status.steps.map((eintrag) => {
            const Zeichen = SYMBOL[eintrag.state];
            return (
              <li
                key={eintrag.key}
                className={s.lauf}
                data-zustand={eintrag.state}
                aria-current={
                  eintrag.key === schritt && status.state === "running" ? "step" : undefined
                }
              >
                <Zeichen className={s.laufSymbol} aria-hidden />
                <span className={s.laufText}>
                  <span>
                    {t(`wiederherstellen.schritte.${eintrag.key}`, {
                      defaultValue: eintrag.label_de,
                    })}
                  </span>
                  {eintrag.detail_de && <small>{eintrag.detail_de}</small>}
                </span>
                <span className={s.laufZustand}>
                  {t(`wiederherstellen.schritt_zustand.${eintrag.state}`)}
                </span>
              </li>
            );
          })}
        </ol>

        {status.finished_at && (
          <p className={`${s.klein} num`}>{formatZeitpunkt(status.finished_at, sprache)}</p>
        )}

        {fertig && (
          <div className={s.aktionen}>
            <Button component={Link} to="/system/sicherung">
              {t("wiederherstellen.fertig_knopf")}
            </Button>
          </div>
        )}
        {gescheitert && (
          <div className={s.aktionen}>
            <Button onClick={onNeu}>{t("wiederherstellen.erneut")}</Button>
            <Button component={Link} to="/system/sicherung" variant="default">
              {t("wiederherstellen.zur_sicherung")}
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}

function Ergebnis({ status }: { status: WiederherstellungsStatus }) {
  const { t, i18n } = useTranslation("system");
  const uebersetzen = useUebersetzer();
  const sprache = i18n.language;
  const ergebnis = status.result;
  if (!ergebnis) return null;
  const zahl = (wert: number) => formatZahl(wert, {}, sprache);
  const bericht = ergebnis.journal;
  const fehlen = bericht ? bericht.missing_events + bericht.conflicts : 0;
  const zeit = status.source ? formatZeitpunkt(status.source.created_at, sprache) : "";
  const hinweise = ergebnisHinweise(status);
  const hinweisTexte = meldungTexte(hinweise, uebersetzen);
  const starts = uebersprungeneStarts(status);

  return (
    <>
      <Kasten ton="gut" icon={<CircleCheck aria-hidden />}>
        <strong>{t("wiederherstellen.fertig_text", { zeit })}</strong>
        <ul>
          {bericht && bericht.applied > 0 && (
            <li>
              {t("wiederherstellen.fertig_nachgetragen", {
                count: bericht.applied,
                anzahl: zahl(bericht.applied),
              })}
            </li>
          )}
          {fehlen > 0 && (
            <li className={s.schlecht}>
              {t("wiederherstellen.fertig_fehlen", { count: fehlen, anzahl: zahl(fehlen) })}
            </li>
          )}
          {ergebnis.pre_restore_backup && <li>{t("wiederherstellen.vorher_liegt")}</li>}
          {ergebnis.after_backup_ok === false && (
            <li className={s.schlecht}>{t("wiederherstellen.nachher_sicherung_fehler")}</li>
          )}
        </ul>
      </Kasten>
      {hinweisTexte.length > 0 && (
        <Kasten ton="warn" icon={<TriangleAlert aria-hidden />}>
          {hinweisTexte.map((text) => (
            <span key={text}>{text}</span>
          ))}
        </Kasten>
      )}
      {starts.length > 0 && <NachtragenListe starts={starts} zeit={zeit} />}
      <div className={s.abschnitt}>
        <h4 className={s.abschnittTitel}>{t("wiederherstellen.naechster_schritt")}</h4>
        <p className={s.text}>{t("wiederherstellen.naechster_text")}</p>
      </div>
      <Einzelheiten
        zeilen={[
          ...(bericht?.lines ?? []),
          ...serverTexte(ergebnis.note_items),
          `${t("wiederherstellen.datenbank")}: ${ergebnis.database}`,
          `${t("wiederherstellen.vorherige_datenbank")}: ${ergebnis.previous_database}`,
          ergebnis.pre_restore_backup &&
            `${t("wiederherstellen.sicherung_davor")}: ${ergebnis.pre_restore_backup}`,
        ]}
      />
    </>
  );
}

/** Merkmal am html-Element, solange die Liste gedruckt wird (Druckregeln in der CSS-Datei). */
const DRUCK_MERKMAL = "nachtragen";

function listeDrucken() {
  const wurzel = document.documentElement;
  wurzel.dataset.druck = DRUCK_MERKMAL;
  const aufraeumen = () => {
    if (wurzel.dataset.druck === DRUCK_MERKMAL) delete wurzel.dataset.druck;
    window.removeEventListener("afterprint", aufraeumen);
  };
  window.addEventListener("afterprint", aufraeumen);
  window.print();
}

/**
 * Starts, deren Ergebnisse sich nicht nachtragen ließen: zum Abarbeiten mit den Startzetteln in
 * der Hand, auch ausgedruckt.
 */
function NachtragenListe({ starts, zeit }: { starts: UebersprungenerStart[]; zeit: string }) {
  const { t } = useTranslation("system");
  const uebersetzen = useUebersetzer();
  const spalte = (name: string) => t(`wiederherstellen.spalte.${name}`);
  return (
    <section className={s.nachtragen} data-druckliste="" aria-labelledby="nachtragen-titel">
      <div className={s.nachtragenKopf}>
        <h4 className={s.abschnittTitel} id="nachtragen-titel">
          {t("wiederherstellen.nachtragen_liste_titel")}
        </h4>
        <Button
          variant="default"
          className={s.nichtDrucken}
          leftSection={<Printer aria-hidden />}
          onClick={listeDrucken}
        >
          {t("wiederherstellen.drucken")}
        </Button>
      </div>
      <p className={s.text}>{t("wiederherstellen.nachtragen_liste_text")}</p>
      {zeit && (
        <p className={s.klein}>{t("wiederherstellen.nachtragen_liste_sicherung", { zeit })}</p>
      )}
      <table className={s.tabelle}>
        <thead>
          <tr>
            <th scope="col">{spalte("startnummer")}</th>
            <th scope="col">{spalte("wettbewerb")}</th>
            <th scope="col">{spalte("start")}</th>
            <th scope="col">{spalte("grund")}</th>
          </tr>
        </thead>
        <tbody>
          {starts.map((start) => (
            <tr
              key={`${start.competition_code}-${start.start_number}-${start.attempt}-${start.reason_code}`}
              data-grund={start.reason_code}
            >
              <td data-beschriftung={spalte("startnummer")} className={`${s.startnummer} num`}>
                {start.start_number ?? "–"}
              </td>
              <td data-beschriftung={spalte("wettbewerb")}>
                <span>
                  <span className={s.wettbewerb}>
                    {start.competition_name ?? t("wiederherstellen.wettbewerb_unbekannt")}
                  </span>
                  {start.competition_code && (
                    <span className={s.kennziffer}>
                      {t("wiederherstellen.kennziffer", { kennziffer: start.competition_code })}
                    </span>
                  )}
                </span>
              </td>
              <td data-beschriftung={spalte("start")}>
                {start.attempt !== null
                  ? t("wiederherstellen.start_nr", { nummer: start.attempt })
                  : "–"}
              </td>
              <td data-beschriftung={spalte("grund")}>{grundText(start, uebersetzen)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
