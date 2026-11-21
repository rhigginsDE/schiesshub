import { Button, Checkbox, NumberInput, PasswordInput, Skeleton, Switch } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CircleCheck,
  CircleX,
  Download,
  FileCheck,
  HardDriveDownload,
  RefreshCw,
  Save,
  TriangleAlert,
  Usb,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  schluessel,
  sicherungsEinstellungenAbfrage,
  sicherungsLaeufeAbfrage,
  sicherungsStatusAbfrage,
} from "../../api/abfragen";
import { apiDatei, apiSenden } from "../../api/client";
import type {
  SicherungsEinstellungen,
  SicherungsLauf,
  SicherungsPruefung,
  SicherungsStatus,
} from "../../api/typenSystem";
import { useDarf } from "../../app/berechtigungen";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { FehlerHinweis, useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { formatZahl } from "../../lib/format";
import { formatGroesse, formatWann, formatZeitpunkt } from "./format";
import s from "./system.module.css";

const PASSWORT_MIN = 12;

export function SicherungBereich() {
  const status = useQuery(sicherungsStatusAbfrage());
  return (
    <>
      {status.isPending ? (
        <Skeleton height={320} radius="lg" />
      ) : status.isError ? (
        <div className="panel">
          <Fehlerzustand fehler={status.error} onErneut={() => void status.refetch()} />
        </div>
      ) : (
        <>
          <StatusPanel status={status.data} />
          <PasswortPanel gesetzt={status.data.passphrase_set} />
        </>
      )}
      <EinstellungenPanel />
      <LaeufePanel />
    </>
  );
}

// --- Zustand ---------------------------------------------------------------------

function StatusPanel({ status }: { status: SicherungsStatus }) {
  const { t, i18n } = useTranslation("system");
  const queryClient = useQueryClient();
  const fehlerText = useFehlerText();
  const darfVerwalten = useDarf("backup.manage");
  const [stickFrage, setStickFrage] = useState(false);
  const sprache = i18n.language;

  const statusSetzen = (neu: SicherungsStatus) => {
    queryClient.setQueryData(schluessel.sicherung.status, neu);
  };

  const sichern = useMutation({
    mutationFn: () => apiSenden<SicherungsLauf[]>("POST", "/backup/run"),
    onSuccess: (laeufe) => {
      const fehler = laeufe.find((lauf) => !lauf.ok);
      zeigeMeldung({
        ton: fehler ? "warn" : "erfolg",
        titel: fehler ? t("sicherung.gesichert_mit_fehler") : t("sicherung.gesichert"),
        text: fehler?.error ?? undefined,
      });
      void queryClient.invalidateQueries({ queryKey: schluessel.sicherung.alle });
    },
    onError: (fehler) =>
      zeigeMeldung({ ton: "krit", titel: t("sicherung.fehler"), text: fehlerText(fehler) }),
  });
  const pruefen = useMutation({
    mutationFn: () => apiSenden<SicherungsStatus>("POST", "/backup/usb/recheck"),
    onSuccess: (neu) => {
      statusSetzen(neu);
      zeigeMeldung({ ton: "info", titel: t("sicherung.geprueft") });
    },
    onError: (fehler) =>
      zeigeMeldung({ ton: "krit", titel: t("sicherung.fehler"), text: fehlerText(fehler) }),
  });
  const einrichten = useMutation({
    mutationFn: () =>
      apiSenden<SicherungsStatus>("POST", "/backup/usb/initialize", { confirm: true }),
    onSuccess: (neu) => {
      statusSetzen(neu);
      setStickFrage(false);
      zeigeMeldung({ ton: "erfolg", titel: t("sicherung.stick_eingerichtet") });
    },
  });

  const { usb, warning, last_snapshot: abzug, last_usb_copy: kopie, journal } = status;
  const zustand = warning ? "gestoert" : "laeuft";

  return (
    <section className="panel" aria-labelledby="sicherung-titel">
      <div className={s.kopf}>
        <div className={s.kopfTitel}>
          <h2 className="h-section" id="sicherung-titel">
            {t("sicherung.titel")}
          </h2>
          <Chip ton={warning ? "krit" : "gruen"} punkt>
            {t(`sicherung.${zustand}`)}
          </Chip>
        </div>
      </div>

      {warning && (
        <div className={`${s.warnkasten} ${s.kritkasten}`} role="status">
          <TriangleAlert className={s.warnSymbol} aria-hidden />
          <div>
            <strong>{warning.message_de}</strong>
            <p className={s.hinweis}>
              <span className="num">{formatZeitpunkt(warning.since, sprache)}</span>
            </p>
          </div>
        </div>
      )}

      <dl className={`inset ${s.zeilen}`}>
        <div>
          <dt>{t("sicherung.stick")}</dt>
          <dd className={usb.present && usb.writable ? s.gut : s.schlecht}>
            {usb.present
              ? usb.writable
                ? usb.free_bytes !== null
                  ? t("sicherung.stick_ok", { frei: formatGroesse(usb.free_bytes, sprache) })
                  : t("sicherung.stick_ok_ohne_platz")
                : t("sicherung.stick_schreibgeschuetzt")
              : usb.last_seen_at
                ? t("sicherung.stick_fehlt_seit", {
                    zeit: formatWann(usb.last_seen_at, new Date(), sprache),
                  })
                : t("sicherung.stick_fehlt")}
          </dd>
        </div>
        <div>
          <dt>{t("sicherung.letzte_sicherung")}</dt>
          <dd className={abzug && !abzug.ok ? s.schlecht : undefined}>
            {!abzug ? (
              t("sicherung.keine")
            ) : abzug.ok ? (
              <span className="num">
                {t("sicherung.letzte_sicherung_wert", {
                  zeit: formatWann(abzug.finished_at, new Date(), sprache),
                  groesse: formatGroesse(abzug.size_bytes ?? 0, sprache),
                })}
              </span>
            ) : (
              t("sicherung.letzte_sicherung_fehler", {
                zeit: formatWann(abzug.finished_at, new Date(), sprache),
              })
            )}
          </dd>
        </div>
        <div>
          <dt>{t("sicherung.letzte_kopie")}</dt>
          <dd className={kopie && !kopie.ok ? s.schlecht : kopie ? s.gut : undefined}>
            {!kopie ? (
              t("sicherung.keine")
            ) : kopie.ok ? (
              <span className="num">{formatWann(kopie.finished_at, new Date(), sprache)}</span>
            ) : (
              t("sicherung.kopie_fehler", {
                zeit: formatWann(kopie.finished_at, new Date(), sprache),
              })
            )}
          </dd>
        </div>
        <div>
          <dt>{t("sicherung.mitschrift")}</dt>
          <dd className={journal.pending > 0 ? undefined : s.gut}>
            {journal.pending > 0
              ? t("sicherung.mitschrift_offen", {
                  count: journal.pending,
                  anzahl: formatZahl(journal.pending, {}, sprache),
                })
              : t("sicherung.mitschrift_aktuell")}
          </dd>
        </div>
        <div>
          <dt>{t("sicherung.passwort")}</dt>
          <dd className={status.passphrase_set ? s.gut : s.schlecht}>
            {status.passphrase_set
              ? t("sicherung.passwort_gesetzt")
              : t("sicherung.passwort_fehlt")}
          </dd>
        </div>
      </dl>
      {kopie && !kopie.ok && kopie.error && <p className={s.laufFehler}>{kopie.error}</p>}

      {darfVerwalten ? (
        <div className={s.aktionen}>
          <Button
            leftSection={<Save aria-hidden />}
            loading={sichern.isPending}
            onClick={() => sichern.mutate()}
          >
            {t("sicherung.jetzt_sichern")}
          </Button>
          <Button
            variant="default"
            leftSection={<RefreshCw aria-hidden />}
            loading={pruefen.isPending}
            onClick={() => pruefen.mutate()}
          >
            {t("sicherung.erneut_pruefen")}
          </Button>
          <Button
            variant="default"
            leftSection={<Usb aria-hidden />}
            onClick={() => {
              einrichten.reset();
              setStickFrage(true);
            }}
          >
            {t("sicherung.stick_einrichten")}
          </Button>
        </div>
      ) : (
        <p className={s.hinweis}>{t("sicherung.nur_mit_recht")}</p>
      )}

      <Bestaetigung
        offen={stickFrage}
        titel={t("sicherung.stick_einrichten_titel")}
        text={<p>{t("sicherung.stick_einrichten_text")}</p>}
        bestaetigen={t("sicherung.stick_einrichten_ok")}
        abbrechen={t("allgemein.abbrechen")}
        laedt={einrichten.isPending}
        fehler={einrichten.isError ? fehlerText(einrichten.error) : undefined}
        onSchliessen={() => setStickFrage(false)}
        onBestaetigen={() => einrichten.mutate()}
      />
    </section>
  );
}

// --- Einstellungen ---------------------------------------------------------------

function EinstellungenPanel() {
  const { t } = useTranslation("system");
  const einstellungen = useQuery(sicherungsEinstellungenAbfrage());
  return (
    <section className="panel" aria-labelledby="sicherung-einstellungen">
      <h2 className="h-section" id="sicherung-einstellungen">
        {t("sicherung.einstellungen")}
      </h2>
      {einstellungen.isPending ? (
        <Skeleton height={260} radius="md" />
      ) : einstellungen.isError ? (
        <Fehlerzustand fehler={einstellungen.error} onErneut={() => void einstellungen.refetch()} />
      ) : (
        <EinstellungenFormular
          key={JSON.stringify(einstellungen.data)}
          gespeichert={einstellungen.data}
        />
      )}
    </section>
  );
}

function EinstellungenFormular({ gespeichert }: { gespeichert: SicherungsEinstellungen }) {
  const { t } = useTranslation("system");
  const queryClient = useQueryClient();
  const darfVerwalten = useDarf("backup.manage");
  const [werte, setWerte] = useState(gespeichert);
  const geaendert = JSON.stringify(werte) !== JSON.stringify(gespeichert);

  const speichern = useMutation({
    mutationFn: () => apiSenden<SicherungsEinstellungen>("PUT", "/backup/settings", werte),
    onSuccess: (neu) => {
      queryClient.setQueryData(schluessel.sicherung.einstellungen, neu);
      void queryClient.invalidateQueries({ queryKey: schluessel.sicherung.status });
      zeigeMeldung({ ton: "erfolg", titel: t("sicherung.einstellungen_gespeichert") });
    },
  });

  const setze = <K extends keyof SicherungsEinstellungen>(
    feld: K,
    wert: SicherungsEinstellungen[K],
  ) => setWerte((alt) => ({ ...alt, [feld]: wert }));

  const schalter = (feld: keyof SicherungsEinstellungen, text: string, hinweis?: string) => (
    <div className={s.einstellung}>
      <span className={s.einstellungText}>
        <span>{text}</span>
        {hinweis && <small>{hinweis}</small>}
      </span>
      <Switch
        size="lg"
        aria-label={text}
        checked={Boolean(werte[feld])}
        disabled={!darfVerwalten}
        onChange={(e) => setze(feld, e.currentTarget.checked as never)}
      />
    </div>
  );

  const zahl = (
    feld: "snapshot_interval_minutes" | "keep_local" | "keep_usb",
    text: string,
    max: number,
    hinweis?: string,
    einheit?: string,
  ) => (
    <div className={s.einstellung}>
      <span className={s.einstellungText}>
        <span>{text}</span>
        {hinweis && <small>{hinweis}</small>}
      </span>
      <NumberInput
        className={s.zahlfeld}
        size="md"
        aria-label={text}
        min={1}
        max={max}
        clampBehavior="strict"
        allowDecimal={false}
        allowNegative={false}
        suffix={einheit ? ` ${einheit}` : undefined}
        value={werte[feld]}
        disabled={!darfVerwalten}
        onChange={(wert) => setze(feld, typeof wert === "number" ? wert : Number(wert) || 1)}
        classNames={{ input: "num" }}
      />
    </div>
  );

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    speichern.mutate();
  };

  return (
    <form className={s.einstellungen} onSubmit={absenden}>
      {schalter("enabled", t("sicherung.an"), t("sicherung.an_hinweis"))}
      {schalter("usb_enabled", t("sicherung.usb_an"))}
      {zahl(
        "snapshot_interval_minutes",
        t("sicherung.intervall"),
        1440,
        t("sicherung.intervall_hinweis"),
        t("sicherung.minuten"),
      )}
      {zahl(
        "keep_local",
        t("sicherung.aufbewahren_server"),
        1000,
        t("sicherung.aufbewahren_hinweis"),
      )}
      {zahl("keep_usb", t("sicherung.aufbewahren_stick"), 1000)}
      {schalter("warn_all_stations", t("sicherung.warnen_alle"))}
      {schalter(
        "warn_on_display",
        t("sicherung.warnen_anzeige"),
        t("sicherung.warnen_anzeige_hinweis"),
      )}
      {schalter("encrypt", t("sicherung.verschluesseln"), t("sicherung.verschluesseln_hinweis"))}
      <FehlerHinweis fehler={speichern.error} />
      {darfVerwalten ? (
        <div className={s.aktionen}>
          <Button
            type="submit"
            variant="default"
            disabled={!geaendert}
            loading={speichern.isPending}
          >
            {t("allgemein.speichern")}
          </Button>
          {geaendert && (
            <Button variant="subtle" color="gray" onClick={() => setWerte(gespeichert)}>
              {t("allgemein.verwerfen")}
            </Button>
          )}
        </div>
      ) : (
        <p className={s.hinweis}>
          {t("allgemein.nur_lesen", { recht: t("berechtigungen.backup_manage") })}
        </p>
      )}
    </form>
  );
}

// --- Passwort ---------------------------------------------------------------------

function PasswortPanel({ gesetzt }: { gesetzt: boolean }) {
  const { t } = useTranslation("system");
  const queryClient = useQueryClient();
  const darfVerwalten = useDarf("backup.manage");
  const [aktuell, setAktuell] = useState("");
  const [neu, setNeu] = useState("");
  const [neu2, setNeu2] = useState("");
  const [bestaetigt, setBestaetigt] = useState(false);
  const [fehler, setFehler] = useState<{ aktuell?: string; neu?: string; neu2?: string }>({});

  const speichern = useMutation({
    mutationFn: () =>
      apiSenden("PUT", "/backup/passphrase", {
        passphrase: neu,
        current_passphrase: gesetzt ? aktuell : null,
      }),
    onSuccess: () => {
      setAktuell("");
      setNeu("");
      setNeu2("");
      setBestaetigt(false);
      void queryClient.invalidateQueries({ queryKey: schluessel.sicherung.status });
      zeigeMeldung({ ton: "erfolg", titel: t("sicherung.passwort_gespeichert") });
    },
  });

  if (!darfVerwalten) return null;

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    const neuFehler: typeof fehler = {};
    if (gesetzt && !aktuell) neuFehler.aktuell = t("sicherung.fehler_passwort_aktuell");
    if (neu.length < PASSWORT_MIN)
      neuFehler.neu = t("sicherung.fehler_passwort_kurz", { anzahl: PASSWORT_MIN });
    else if (neu !== neu2) neuFehler.neu2 = t("sicherung.fehler_passwort_gleich");
    setFehler(neuFehler);
    if (Object.keys(neuFehler).length === 0) speichern.mutate();
  };

  return (
    <section className="panel" aria-labelledby="sicherung-passwort">
      <h2 className="h-section" id="sicherung-passwort">
        {t("sicherung.passwort_titel")}
      </h2>
      <div className={s.warnkasten} role="note">
        <TriangleAlert className={s.warnSymbol} aria-hidden />
        <p>{t("sicherung.passwort_warnung")}</p>
      </div>
      <form className={s.formular} onSubmit={absenden} noValidate>
        {gesetzt && (
          <PasswordInput
            visibilityToggleButtonProps={{ "aria-label": t("shell:sichtbar_umschalten") }}
            size="md"
            label={t("sicherung.passwort_aktuell")}
            value={aktuell}
            onChange={(e) => setAktuell(e.currentTarget.value)}
            error={fehler.aktuell}
            autoComplete="current-password"
          />
        )}
        <PasswordInput
          visibilityToggleButtonProps={{ "aria-label": t("shell:sichtbar_umschalten") }}
          size="md"
          label={t("sicherung.passwort_neu")}
          description={t("sicherung.passwort_neu_hinweis", { anzahl: PASSWORT_MIN })}
          value={neu}
          onChange={(e) => setNeu(e.currentTarget.value)}
          error={fehler.neu}
          autoComplete="new-password"
        />
        <PasswordInput
          visibilityToggleButtonProps={{ "aria-label": t("shell:sichtbar_umschalten") }}
          size="md"
          label={t("sicherung.passwort_wiederholen")}
          value={neu2}
          onChange={(e) => setNeu2(e.currentTarget.value)}
          error={fehler.neu2}
          autoComplete="new-password"
        />
        <Checkbox
          size="md"
          checked={bestaetigt}
          onChange={(e) => setBestaetigt(e.currentTarget.checked)}
          label={t("sicherung.passwort_bestaetigt")}
        />
        <FehlerHinweis fehler={speichern.error} />
        <div className={s.aktionen}>
          <Button
            type="submit"
            variant="default"
            disabled={!bestaetigt}
            loading={speichern.isPending}
          >
            {gesetzt ? t("sicherung.passwort_aendern") : t("sicherung.passwort_setzen")}
          </Button>
        </div>
      </form>
    </section>
  );
}

// --- Läufe ------------------------------------------------------------------------

function LaeufePanel() {
  const { t, i18n } = useTranslation("system");
  const laeufe = useQuery(sicherungsLaeufeAbfrage());
  const darfVerwalten = useDarf("backup.manage");
  const fehlerText = useFehlerText();
  const [pruefling, setPruefling] = useState<SicherungsLauf | null>(null);
  const [laedtHerunter, setLaedtHerunter] = useState<string | null>(null);
  const sprache = i18n.language;

  const herunterladen = async (lauf: SicherungsLauf) => {
    setLaedtHerunter(lauf.id);
    try {
      const datei = await apiDatei(
        `/backup/runs/${encodeURIComponent(lauf.id)}/download`,
        `schiesshub-${lauf.id}.shbak`,
      );
      const adresse = URL.createObjectURL(datei.inhalt);
      const link = document.createElement("a");
      link.href = adresse;
      link.download = datei.name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(adresse), 10_000);
    } catch (fehler) {
      zeigeMeldung({ ton: "krit", titel: t("sicherung.herunterladen"), text: fehlerText(fehler) });
    } finally {
      setLaedtHerunter(null);
    }
  };

  return (
    <section className="panel" aria-labelledby="sicherung-laeufe">
      <div className={s.kopf}>
        <h2 className="h-section" id="sicherung-laeufe">
          {t("sicherung.laeufe")}
        </h2>
        {darfVerwalten && <span className={s.hinweis}>{t("sicherung.herunterladen_hinweis")}</span>}
      </div>
      {laeufe.isPending ? (
        <Skeleton height={200} radius="md" />
      ) : laeufe.isError ? (
        <Fehlerzustand fehler={laeufe.error} onErneut={() => void laeufe.refetch()} />
      ) : laeufe.data.length === 0 ? (
        <Leerzustand
          icon={HardDriveDownload}
          titel={t("sicherung.laeufe_leer_titel")}
          text={t("sicherung.laeufe_leer_text")}
        />
      ) : (
        <ul>
          {laeufe.data.map((lauf) => {
            const abzug = lauf.kind === "snapshot" && lauf.ok && lauf.file_name;
            return (
              <li key={lauf.id} className={s.laufZeile}>
                <span className="num">{formatZeitpunkt(lauf.finished_at, sprache)}</span>
                <span className={s.marken}>
                  <Chip ton="neutral">{t(`sicherung.art_${lauf.kind}`)}</Chip>
                  <Chip ton="info">{t(`sicherung.ziel_${lauf.target}`)}</Chip>
                </span>
                <span>
                  {lauf.ok ? (
                    <span className={s.gut}>
                      <CircleCheck aria-hidden /> {t("sicherung.ok")}
                      {lauf.size_bytes !== null && (
                        <span className="num gedaempft">
                          {" "}
                          · {formatGroesse(lauf.size_bytes, sprache)}
                        </span>
                      )}
                    </span>
                  ) : (
                    <span className={s.laufFehler}>
                      <CircleX aria-hidden /> {lauf.error ?? t("sicherung.fehler")}
                    </span>
                  )}
                </span>
                <span className={s.aktionen}>
                  {darfVerwalten && abzug && (
                    <Button
                      size="sm"
                      variant="default"
                      leftSection={<FileCheck aria-hidden />}
                      onClick={() => setPruefling(lauf)}
                    >
                      {t("sicherung.pruefen")}
                    </Button>
                  )}
                  {darfVerwalten && abzug && lauf.target === "local" && (
                    <Button
                      size="sm"
                      variant="default"
                      leftSection={<Download aria-hidden />}
                      loading={laedtHerunter === lauf.id}
                      onClick={() => void herunterladen(lauf)}
                    >
                      {t("sicherung.herunterladen")}
                    </Button>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {pruefling && <PruefDialog lauf={pruefling} onSchliessen={() => setPruefling(null)} />}
    </section>
  );
}

function PruefDialog({ lauf, onSchliessen }: { lauf: SicherungsLauf; onSchliessen: () => void }) {
  const { t, i18n } = useTranslation("system");
  const fehlerText = useFehlerText();
  const [passwort, setPasswort] = useState("");
  const sprache = i18n.language;
  const pruefen = useMutation({
    mutationFn: () =>
      apiSenden<SicherungsPruefung>("POST", `/backup/runs/${encodeURIComponent(lauf.id)}/verify`, {
        passphrase: passwort || null,
      }),
  });
  const ergebnis = pruefen.data;

  return (
    <Bestaetigung
      offen
      titel={t("sicherung.pruefen_titel")}
      text={
        <>
          <p>{t("sicherung.pruefen_text")}</p>
          <p className="num">
            {formatZeitpunkt(lauf.finished_at, sprache)} · {t(`sicherung.ziel_${lauf.target}`)}
          </p>
        </>
      }
      bestaetigen={t("sicherung.pruefen_start")}
      abbrechen={t("allgemein.abbrechen")}
      laedt={pruefen.isPending}
      fehler={pruefen.isError ? fehlerText(pruefen.error) : undefined}
      onSchliessen={onSchliessen}
      onBestaetigen={() => pruefen.mutate()}
    >
      {lauf.target === "usb" && (
        <PasswordInput
          visibilityToggleButtonProps={{ "aria-label": t("shell:sichtbar_umschalten") }}
          size="md"
          label={t("sicherung.pruefen_passwort")}
          description={t("sicherung.pruefen_passwort_hinweis")}
          value={passwort}
          onChange={(e) => setPasswort(e.currentTarget.value)}
          data-autofocus
        />
      )}
      {ergebnis && (
        <div
          className={`${s.warnkasten} ${ergebnis.ok ? s.gutkasten : s.kritkasten}`}
          role="status"
        >
          {ergebnis.ok ? (
            <CircleCheck className={s.warnSymbol} aria-hidden />
          ) : (
            <CircleX className={s.warnSymbol} aria-hidden />
          )}
          <div>
            <strong>
              {ergebnis.ok ? t("sicherung.pruefung_ok") : t("sicherung.pruefung_fehler")}
            </strong>
            {ergebnis.error && <p>{ergebnis.error}</p>}
            <dl className={s.zeilen} style={{ padding: 0 }}>
              <div>
                <dt>{t("sicherung.pruefung_datei")}</dt>
                <dd className="num">{ergebnis.file_name}</dd>
              </div>
              <div>
                <dt>{t("sicherung.pruefung_ort")}</dt>
                <dd>{t(`sicherung.ziel_${ergebnis.location}`)}</dd>
              </div>
              <div>
                <dt>{t("sicherung.pruefung_verschluesselt")}</dt>
                <dd>{ergebnis.encrypted ? t("allgemein.ja") : t("allgemein.nein")}</dd>
              </div>
              <div>
                <dt>{t("sicherung.pruefung_groesse")}</dt>
                <dd className="num">{formatGroesse(ergebnis.size_bytes, sprache)}</dd>
              </div>
              <div>
                <dt>{t("sicherung.pruefung_pruefsumme")}</dt>
                <dd className={ergebnis.checksum_ok ? s.gut : s.schlecht}>
                  {ergebnis.checksum_ok ? t("sicherung.ok") : t("sicherung.fehler")}
                </dd>
              </div>
              {ergebnis.database_toc_entries !== null && (
                <div>
                  <dt>{t("sicherung.pruefung_eintraege")}</dt>
                  <dd className="num">{formatZahl(ergebnis.database_toc_entries, {}, sprache)}</dd>
                </div>
              )}
            </dl>
          </div>
        </div>
      )}
    </Bestaetigung>
  );
}
