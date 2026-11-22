import { Button, Checkbox, Loader } from "@mantine/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CircleCheck, Download, FileDown, FileUp, Upload } from "lucide-react";
import { type DragEvent, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../app/berechtigungen";
import { Chip, type ChipTon } from "../../components/Chip";
import { Fehlerzustand } from "../../components/Zustand";
import { formatZahl } from "../../lib/format";
import {
  exportLaden,
  IMPORT_MAX_BYTES,
  type ImportBericht,
  type ImportZeile,
  personenImportieren,
  teilnehmerSchluessel,
} from "./api";
import { beispielCsv, blobAnbieten, dateiAnbieten, vorschauZeilen } from "./csv";
import { ablehnungsgrund } from "./importFehler";
import { Kopf } from "./Kopf";
import { TEILNEHMER_PFAD } from "./pfade";
import s from "./teilnehmer.module.css";

interface Datei {
  name: string;
  inhalt: ArrayBuffer;
  text: string;
}

/** Wie der Server: UTF-8, sonst Windows-1252 (Excel „CSV (Trennzeichen-getrennt)“). */
function dateiText(inhalt: ArrayBuffer): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(inhalt);
  } catch {
    return new TextDecoder("windows-1252").decode(inhalt);
  }
}

const STATUS_TON: Record<ImportZeile["status"], ChipTon> = {
  new: "gruen",
  duplicate: "warn",
  error: "krit",
};

/** Import (immer erst Vorschau) und Export der Personen als CSV. */
export function ImportSeite() {
  const darfExport = useDarf("person.export");
  return (
    <div className={s.seiteFluss}>
      <Kopf aktiv="import" />
      <div className={s.importRaster}>
        <Import />
        <aside className={s.importSeite}>
          <Spalten />
          {darfExport && <Export />}
        </aside>
      </div>
    </div>
  );
}

function Export() {
  const { t } = useTranslation("teilnehmer");
  const laden = useMutation({
    mutationFn: exportLaden,
    onSuccess: (datei) => blobAnbieten(datei.name, datei.inhalt),
  });
  return (
    <section className="panel" aria-labelledby="export-titel">
      <h2 className="h-section" id="export-titel">
        {t("export.titel")}
      </h2>
      <p className={s.text}>{t("export.text")}</p>
      {laden.isError && <Fehlerzustand fehler={laden.error} onErneut={() => laden.mutate()} />}
      <div>
        <Button
          variant="default"
          leftSection={<FileDown aria-hidden />}
          loading={laden.isPending}
          onClick={() => laden.mutate()}
        >
          {t("export.herunterladen")}
        </Button>
      </div>
    </section>
  );
}

function Spalten() {
  const { t } = useTranslation("teilnehmer");
  const spalten = [
    ["Name", "spalte_name"],
    ["Verein", "spalte_verein"],
    ["Mitgliedsnummer", "spalte_mitgliedsnummer"],
    ["Anzeige", "spalte_anzeige"],
    ["Verein anzeigen", "spalte_verein_anzeigen"],
  ] as const;
  return (
    <section className="panel" aria-labelledby="spalten-titel">
      <h2 className="h-section" id="spalten-titel">
        {t("import.spalten_titel")}
      </h2>
      <p className={s.text}>{t("import.spalten_text")}</p>
      <dl className={s.spaltenListe}>
        {spalten.map(([spalte, text]) => (
          <div key={spalte}>
            <dt>
              <code>{spalte}</code>
            </dt>
            <dd>{t(`import.${text}`)}</dd>
          </div>
        ))}
      </dl>
      <div>
        <Button
          variant="default"
          leftSection={<Download aria-hidden />}
          onClick={() => dateiAnbieten("personen-beispiel.csv", beispielCsv())}
        >
          {t("import.beispiel")}
        </Button>
      </div>
    </section>
  );
}

function Import() {
  const { t, i18n } = useTranslation("teilnehmer");
  const queryClient = useQueryClient();
  const eingabe = useRef<HTMLInputElement>(null);
  const titelId = useId();
  const [datei, setDatei] = useState<Datei | null>(null);
  const [dateiFehler, setDateiFehler] = useState<string | null>(null);
  const [ziehen, setZiehen] = useState(false);
  const [nurAuffaellige, setNurAuffaellige] = useState(false);
  const zahl = (wert: number) => formatZahl(wert, {}, i18n.language);

  const pruefen = useMutation({
    mutationFn: (inhalt: ArrayBuffer) => personenImportieren(inhalt, true),
  });
  const importieren = useMutation({
    mutationFn: (inhalt: ArrayBuffer) => personenImportieren(inhalt, false),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: teilnehmerSchluessel.alle }),
  });

  const zuruecksetzen = () => {
    setDatei(null);
    setDateiFehler(null);
    setNurAuffaellige(false);
    pruefen.reset();
    importieren.reset();
    if (eingabe.current) eingabe.current.value = "";
  };

  /** Nach einer abgelehnten Datei: zurück zum Anfang und gleich die Dateiauswahl öffnen. */
  const andereDatei = () => {
    zuruecksetzen();
    eingabe.current?.click();
  };

  const uebernehmen = async (gewaehlt: File | undefined) => {
    if (!gewaehlt) return;
    zuruecksetzen();
    if (!/\.(csv|txt)$/i.test(gewaehlt.name) && !gewaehlt.type.includes("csv")) {
      setDateiFehler(t("import.keine_csv"));
      return;
    }
    if (gewaehlt.size > IMPORT_MAX_BYTES) {
      setDateiFehler(t("import.zu_gross"));
      return;
    }
    const inhalt = await gewaehlt.arrayBuffer();
    const text = dateiText(inhalt);
    setDatei({ name: gewaehlt.name, inhalt, text });
    pruefen.mutate(inhalt);
  };

  const beiAblegen = (ereignis: DragEvent) => {
    ereignis.preventDefault();
    setZiehen(false);
    void uebernehmen(ereignis.dataTransfer.files[0]);
  };

  const zeilen = useMemo(() => (datei ? vorschauZeilen(datei.text) : new Map()), [datei]);
  const bericht: ImportBericht | undefined = pruefen.data;

  if (importieren.isSuccess) {
    const fertig = importieren.data;
    return (
      <section className={`panel ${s.importPanel}`} aria-labelledby={titelId}>
        <h2 className="h-section" id={titelId}>
          {t("import.titel")}
        </h2>
        <div className={s.fertig} role="status">
          <CircleCheck aria-hidden />
          <div>
            <strong>{t("import.fertig", { count: fertig.new, anzahl: zahl(fertig.new) })}</strong>
            <Zusammenfassung bericht={fertig} />
          </div>
        </div>
        <div className={s.zeileAktionen}>
          <Button component={Link} to={TEILNEHMER_PFAD} variant="default">
            {t("import.zu_personen")}
          </Button>
          <Button variant="default" leftSection={<Upload aria-hidden />} onClick={zuruecksetzen}>
            {t("import.weiter")}
          </Button>
        </div>
      </section>
    );
  }

  const sichtbareZeilen = (bericht?.rows ?? []).filter(
    (zeile) => !nurAuffaellige || zeile.status !== "new",
  );

  return (
    <section className={`panel ${s.importPanel}`} aria-labelledby={titelId}>
      <h2 className="h-section" id={titelId}>
        {t("import.titel")}
      </h2>

      {!datei ? (
        <section
          aria-label={t("import.waehlen")}
          className={s.ablage}
          data-ziehen={ziehen || undefined}
          onDragOver={(ereignis) => {
            ereignis.preventDefault();
            setZiehen(true);
          }}
          onDragLeave={() => setZiehen(false)}
          onDrop={beiAblegen}
        >
          <FileUp className={s.ablageSymbol} aria-hidden />
          <p>{t("import.text")}</p>
          <Button variant="default" size="md" onClick={() => eingabe.current?.click()}>
            {t("import.waehlen")}
          </Button>
          <span className="gedaempft">{t("import.ablegen")}</span>
          {dateiFehler && (
            <p className={s.fehlerZeile} role="alert">
              {dateiFehler}
            </p>
          )}
        </section>
      ) : (
        <div className={s.dateiZeile}>
          <span className={s.dateiName}>{t("import.datei", { name: datei.name })}</span>
          <Button variant="default" onClick={zuruecksetzen}>
            {t("import.andere")}
          </Button>
        </div>
      )}
      <input
        ref={eingabe}
        type="file"
        accept=".csv,text/csv"
        hidden
        onChange={(ereignis) => void uebernehmen(ereignis.currentTarget.files?.[0])}
      />

      {pruefen.isPending && (
        <p className={s.status} role="status">
          <Loader size="xs" />
          {t("import.pruefen")}
        </p>
      )}

      {pruefen.isError &&
        (ablehnungsgrund(pruefen.error) ? (
          <DateiFehlerHinweis fehler={pruefen.error} onAndereDatei={andereDatei} />
        ) : (
          <Fehlerzustand
            fehler={pruefen.error}
            onErneut={datei ? () => pruefen.mutate(datei.inhalt) : undefined}
          />
        ))}

      {bericht && (
        <>
          <div className={s.vorschauKopf}>
            <h3 className="h-label">{t("import.vorschau_titel")}</h3>
            <Zusammenfassung bericht={bericht} />
            <p className="gedaempft">{t("import.hinweis_ueberspringen")}</p>
            {(bericht.ignored_columns?.length ?? 0) > 0 && (
              <p className="gedaempft">
                {t("import.ignoriert", {
                  count: bericht.ignored_columns?.length,
                  spalten: bericht.ignored_columns?.join(", "),
                })}
              </p>
            )}
          </div>

          {bericht.rows.length > 0 && (bericht.duplicate > 0 || bericht.error > 0) && (
            <Checkbox
              label={t("import.nur_auffaellige")}
              checked={nurAuffaellige}
              onChange={(ereignis) => setNurAuffaellige(ereignis.currentTarget.checked)}
            />
          )}

          <table className={s.tabelle}>
            <caption className="nur-screenreader">{t("import.vorschau_titel")}</caption>
            <thead>
              <tr className={`${s.tabellenZeile} ${s.tabellenKopf}`}>
                <th scope="col">{t("import.spalte_zeile")}</th>
                <th scope="col">{t("import.spalte_person")}</th>
                <th scope="col">{t("import.spalte_ergebnis")}</th>
              </tr>
            </thead>
            <tbody>
              {sichtbareZeilen.map((zeile) => {
                // Der Server liefert Name und Verein so, wie er sie gelesen hat (auch bei
                // getrennten Spalten Vorname/Nachname); die eigene Auswertung ist nur Rückfall.
                const daten = zeilen.get(zeile.line);
                const name = zeile.name ?? daten?.name;
                const verein = zeile.club ?? daten?.verein;
                const meldung =
                  zeile.message ??
                  (zeile.status === "duplicate"
                    ? zeile.person_id
                      ? t("import.dublette_vorhanden")
                      : t("import.dublette_datei")
                    : null);
                return (
                  <tr key={zeile.line} className={s.tabellenZeile} data-status={zeile.status}>
                    <td className={`num ${s.zeileNr}`}>{zahl(zeile.line)}</td>
                    <td className={s.zeilePerson}>
                      <strong>{name || "—"}</strong>
                      {verein && <span className={s.zeileVerein}>{verein}</span>}
                    </td>
                    <td className={s.zeileErgebnis}>
                      <Chip ton={STATUS_TON[zeile.status]}>
                        {t(`import.status_${zeile.status}`)}
                      </Chip>
                      {meldung && <span className={s.zeileMeldung}>{meldung}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {importieren.isError &&
            (ablehnungsgrund(importieren.error) ? (
              <DateiFehlerHinweis fehler={importieren.error} onAndereDatei={andereDatei} />
            ) : (
              <Fehlerzustand
                fehler={importieren.error}
                onErneut={() => datei && importieren.mutate(datei.inhalt)}
              />
            ))}

          <div className={s.zeileAktionen}>
            {bericht.new > 0 ? (
              <Button
                size="md"
                leftSection={<Upload aria-hidden />}
                loading={importieren.isPending}
                onClick={() => datei && importieren.mutate(datei.inhalt)}
              >
                {t("import.importieren", { count: bericht.new, anzahl: zahl(bericht.new) })}
              </Button>
            ) : (
              <p className="gedaempft">{t("import.nichts_neu")}</p>
            )}
          </div>
        </>
      )}
    </section>
  );
}

/** Datei abgelehnt: Grund in Klartext, was zu tun ist, und der Weg zu einer anderen Datei. */
function DateiFehlerHinweis({
  fehler,
  onAndereDatei,
}: {
  fehler: unknown;
  onAndereDatei: () => void;
}) {
  const { t } = useTranslation("teilnehmer");
  const grund = ablehnungsgrund(fehler);
  if (!grund) return null;
  const { art, spalte, meldung } = grund;
  const nameInZweiSpalten =
    art === "spalte_unbekannt" && /vor-?name|nach-?name/i.test(spalte ?? "");
  const text =
    art === "sonstig"
      ? (meldung ?? t("datei_fehler.sonstig"))
      : t(`datei_fehler.${art}`, { spalte });
  const abhilfe = nameInZweiSpalten
    ? t("datei_fehler.name_geteilt_abhilfe")
    : t(`datei_fehler.${art}_abhilfe`);

  return (
    <div className={s.hinweisKrit} role="alert">
      <strong>{t("datei_fehler.titel")}</strong>
      <p>{text}</p>
      <p>
        <strong>{t("datei_fehler.abhilfe")}:</strong> {abhilfe}
      </p>
      <div className={s.hinweisAktionen}>
        <Button variant="default" leftSection={<FileUp aria-hidden />} onClick={onAndereDatei}>
          {t("datei_fehler.andere_datei")}
        </Button>
        <Button
          variant="subtle"
          leftSection={<Download aria-hidden />}
          onClick={() => dateiAnbieten("personen-beispiel.csv", beispielCsv())}
        >
          {t("import.beispiel")}
        </Button>
      </div>
    </div>
  );
}

function Zusammenfassung({ bericht }: { bericht: ImportBericht }) {
  const { t, i18n } = useTranslation("teilnehmer");
  const zahl = (wert: number) => formatZahl(wert, {}, i18n.language);
  return (
    <div className={s.zusammenfassung}>
      <Chip ton="gruen">
        {t("import.zusammenfassung_neu", { count: bericht.new, anzahl: zahl(bericht.new) })}
      </Chip>
      {bericht.duplicate > 0 && (
        <Chip ton="warn">
          {t("import.zusammenfassung_dublette", {
            count: bericht.duplicate,
            anzahl: zahl(bericht.duplicate),
          })}
        </Chip>
      )}
      {bericht.error > 0 && (
        <Chip ton="krit">
          {t("import.zusammenfassung_fehler", {
            count: bericht.error,
            anzahl: zahl(bericht.error),
          })}
        </Chip>
      )}
      {bericht.new_clubs.length > 0 && (
        <span className={s.neueVereine}>
          {t("import.neue_vereine", {
            count: bericht.new_clubs.length,
            namen: bericht.new_clubs.join(", "),
          })}
        </span>
      )}
    </div>
  );
}
