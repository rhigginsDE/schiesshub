import { ActionIcon, Button, Menu, Select, Skeleton, TextInput } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  CircleCheck,
  MonitorSmartphone,
  MoreVertical,
  Pencil,
  QrCode as QrSymbol,
  Trash2,
  TriangleAlert,
  Unlock,
} from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { geraeteAbfrage, rollenAbfrage, schluessel } from "../../api/abfragen";
import { ApiFehler, apiSenden } from "../../api/client";
import type { Geraet, Kopplungscode, Rolle } from "../../api/typenSystem";
import { useDarf } from "../../app/berechtigungen";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { Dialog } from "../../components/Dialog";
import { FehlerHinweis, useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { QrCode } from "../../components/QrCode";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { codeGruppiert, formatRestzeit } from "../auth/eingaben";
import { formatWann, formatZeitpunkt } from "./format";
import { taugtAlsStandardrolle } from "./rollenMatrix";
import s from "./system.module.css";

const OHNE_ROLLE = "";

export function GeraeteBereich() {
  const { t } = useTranslation("system");
  const geraete = useQuery(geraeteAbfrage());
  const darfRollen = useDarf("role.manage");
  const rollen = useQuery({ ...rollenAbfrage(), enabled: darfRollen });
  const [koppeln, setKoppeln] = useState(false);

  return (
    <section className="panel" aria-labelledby="geraete-titel">
      <div className={s.kopf}>
        <h2 className="h-section" id="geraete-titel">
          {t("geraete.titel")}
        </h2>
        <Button leftSection={<QrSymbol aria-hidden />} onClick={() => setKoppeln(true)}>
          {t("geraete.koppeln")}
        </Button>
      </div>
      <p className={s.einleitung}>{t("geraete.einleitung")}</p>

      {geraete.isPending ? (
        <Skeleton height={240} radius="md" />
      ) : geraete.isError ? (
        <Fehlerzustand fehler={geraete.error} onErneut={() => void geraete.refetch()} />
      ) : geraete.data.length === 0 ? (
        <Leerzustand
          icon={MonitorSmartphone}
          titel={t("geraete.leer_titel")}
          text={t("geraete.leer_text")}
        />
      ) : (
        <ul className={s.liste}>
          {geraete.data.map((geraet) => (
            <GeraetZeile key={geraet.id} geraet={geraet} rollen={rollen.data} />
          ))}
        </ul>
      )}

      {koppeln && <KoppelDialog rollen={rollen.data} onSchliessen={() => setKoppeln(false)} />}
    </section>
  );
}

/**
 * Rollen zur Wahl als Standardrolle. Eine Rolle mit Verwaltungsrechten (Administrator, Rollen,
 * Personen, Geräte, System, Sicherung) gibt es ohne PIN nicht: sichtbar, aber nicht wählbar. Die
 * gerade eingestellte bleibt wählbar, damit nichts still verschwindet.
 */
function rollenAuswahl(
  rollen: Rolle[] | undefined,
  ohne: string,
  nurMitPin: string,
  aktuell?: string | null,
) {
  return [
    { value: OHNE_ROLLE, label: ohne },
    ...(rollen ?? []).map((rolle) => {
      const gesperrt = !taugtAlsStandardrolle(rolle) && rolle.id !== aktuell;
      return {
        value: rolle.id,
        label: gesperrt ? `${rolle.name} (${nurMitPin})` : rolle.name,
        disabled: gesperrt,
      };
    }),
  ];
}

/**
 * Meldung des Servers zur Standardrolle (422 mit Feld `default_role_id`, z. B. eine Rolle mit
 * Verwaltungsrechten), damit sie am Auswahlfeld steht statt irgendwo darüber.
 */
export function rollenFeldFehler(fehler: unknown): string | undefined {
  if (!(fehler instanceof ApiFehler)) return undefined;
  return fehler.felder.find((eintrag) => eintrag.feld === "default_role_id")?.meldung;
}

function GeraetZeile({ geraet, rollen }: { geraet: Geraet; rollen: Rolle[] | undefined }) {
  const { t, i18n } = useTranslation("system");
  const queryClient = useQueryClient();
  const fehlerText = useFehlerText();
  const [frage, setFrage] = useState<"umbenennen" | "sperren" | "loeschen" | null>(null);
  const [name, setName] = useState(geraet.name);
  const sprache = i18n.language;

  const aendern = useMutation({
    mutationFn: (inhalt: { name?: string; default_role_id?: string | null; blocked?: boolean }) =>
      apiSenden<Geraet>("PATCH", `/devices/${encodeURIComponent(geraet.id)}`, inhalt),
    onSuccess: () => {
      setFrage(null);
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.geraete });
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.status });
      zeigeMeldung({ ton: "erfolg", titel: t("geraete.geaendert") });
    },
    onError: (fehler) => {
      // Ein Fehler zur Rolle steht am Auswahlfeld; alles andere als Meldung.
      if (!frage && !rollenFeldFehler(fehler)) {
        zeigeMeldung({ ton: "krit", titel: geraet.name, text: fehlerText(fehler) });
      }
    },
  });
  const loeschen = useMutation({
    mutationFn: () => apiSenden("DELETE", `/devices/${encodeURIComponent(geraet.id)}`),
    onSuccess: () => {
      setFrage(null);
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.geraete });
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.status });
      zeigeMeldung({ ton: "info", titel: t("geraete.geloescht") });
    },
  });

  const rolleBekannt =
    !geraet.default_role_id || rollen?.some((r) => r.id === geraet.default_role_id);
  const oeffnen = (art: NonNullable<typeof frage>) => {
    aendern.reset();
    loeschen.reset();
    setName(geraet.name);
    setFrage(art);
  };

  const umbenennen = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    if (name.trim()) aendern.mutate({ name: name.trim() });
  };

  return (
    <li>
      <span className={s.eintrag}>
        <strong>
          {geraet.name}
          {"  "}
          <span className={s.marken}>
            {geraet.is_current && <Chip ton="info">{t("geraete.dieses")}</Chip>}
            {geraet.blocked && <Chip ton="krit">{t("geraete.gesperrt")}</Chip>}
          </span>
        </strong>
        <span>
          <span className="num">
            {t("geraete.gekoppelt_am", { zeit: formatZeitpunkt(geraet.paired_at, sprache) })}
          </span>
          {" · "}
          <span className="num">
            {geraet.last_seen_at
              ? t("geraete.zuletzt", { zeit: formatWann(geraet.last_seen_at, new Date(), sprache) })
              : t("geraete.nie")}
          </span>
        </span>
      </span>
      <Select
        className={s.auswahl}
        size="md"
        label={t("geraete.rolle")}
        data={rollenAuswahl(
          rollen,
          t("geraete.rolle_keine"),
          t("geraete.rolle_nur_mit_pin"),
          geraet.default_role_id,
        )}
        value={geraet.default_role_id ?? OHNE_ROLLE}
        placeholder={rolleBekannt ? undefined : t("geraete.rolle_unbekannt")}
        error={frage ? undefined : rollenFeldFehler(aendern.error)}
        disabled={!rollen || aendern.isPending}
        allowDeselect={false}
        onChange={(wert) => {
          if (wert === null) return;
          aendern.mutate({ default_role_id: wert === OHNE_ROLLE ? null : wert });
        }}
      />
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <ActionIcon
            variant="default"
            size={44}
            aria-label={t("allgemein.aktionen", { name: geraet.name })}
          >
            <MoreVertical aria-hidden />
          </ActionIcon>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item leftSection={<Pencil aria-hidden />} onClick={() => oeffnen("umbenennen")}>
            {t("geraete.umbenennen")}
          </Menu.Item>
          {geraet.blocked ? (
            <Menu.Item
              leftSection={<Unlock aria-hidden />}
              onClick={() => aendern.mutate({ blocked: false })}
            >
              {t("geraete.entsperren")}
            </Menu.Item>
          ) : (
            <Menu.Item leftSection={<Ban aria-hidden />} onClick={() => oeffnen("sperren")}>
              {t("geraete.sperren")}
            </Menu.Item>
          )}
          <Menu.Item
            color="red"
            leftSection={<Trash2 aria-hidden />}
            onClick={() => oeffnen("loeschen")}
          >
            {t("allgemein.loeschen")}
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>

      <Dialog
        opened={frage === "umbenennen"}
        onClose={() => setFrage(null)}
        title={t("geraete.umbenennen_titel")}
        centered
      >
        <form className={s.formular} onSubmit={umbenennen}>
          <TextInput
            size="md"
            label={t("geraete.name")}
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            maxLength={100}
            data-autofocus
          />
          <FehlerHinweis fehler={aendern.error} />
          <div className={s.aktionen}>
            <Button type="submit" loading={aendern.isPending} disabled={!name.trim()}>
              {t("allgemein.speichern")}
            </Button>
            <Button variant="default" onClick={() => setFrage(null)}>
              {t("allgemein.abbrechen")}
            </Button>
          </div>
        </form>
      </Dialog>
      <Bestaetigung
        offen={frage === "sperren"}
        titel={t("geraete.sperren_titel", { name: geraet.name })}
        text={
          <>
            <p>{t("geraete.sperren_text")}</p>
            {geraet.is_current && <p className={s.schlecht}>{t("geraete.sperren_dieses")}</p>}
          </>
        }
        bestaetigen={t("geraete.sperren")}
        abbrechen={t("allgemein.abbrechen")}
        ton="gefahr"
        laedt={aendern.isPending}
        fehler={aendern.isError ? fehlerText(aendern.error) : undefined}
        onSchliessen={() => setFrage(null)}
        onBestaetigen={() => aendern.mutate({ blocked: true })}
      />
      <Bestaetigung
        offen={frage === "loeschen"}
        titel={t("geraete.loeschen_titel", { name: geraet.name })}
        text={
          <>
            <p>{t("geraete.loeschen_text")}</p>
            {geraet.is_current && <p className={s.schlecht}>{t("geraete.sperren_dieses")}</p>}
          </>
        }
        bestaetigen={t("allgemein.loeschen")}
        abbrechen={t("allgemein.abbrechen")}
        ton="gefahr"
        laedt={loeschen.isPending}
        fehler={loeschen.isError ? fehlerText(loeschen.error) : undefined}
        onSchliessen={() => setFrage(null)}
        onBestaetigen={() => loeschen.mutate()}
      />
    </li>
  );
}

// --- Kopplungscode -----------------------------------------------------------------

/** Adresse für den QR-Code: Herkunft dieses Browsers plus der Pfad vom Server. */
export function kopplungsAdresse(
  pairPath: string,
  herkunft: string = window.location.origin,
): string {
  return `${herkunft}${pairPath.startsWith("/") ? "" : "/"}${pairPath}`;
}

/**
 * Zeigt die Adresse nur auf dieses Gerät selbst (localhost, 127.x, ::1)? Dann kann ein anderes
 * Gerät den QR-Code nicht nutzen: Es würde sich selbst statt den Server aufrufen.
 */
export function istNurDiesesGeraet(herkunft: string = window.location.origin): boolean {
  let host: string;
  try {
    host = new URL(herkunft).hostname.toLowerCase();
  } catch {
    return false;
  }
  return (
    host === "localhost" ||
    host.endsWith(".localhost") ||
    /^127(\.\d{1,3}){3}$/.test(host) ||
    host === "[::1]" ||
    host === "::1" ||
    host === "0.0.0.0"
  );
}

/**
 * Adressen des Servers aus der Antwort (`server_urls`), die auch andere Geräte erreichen; ohne
 * localhost, 127.x und Co. Die erste kommt in den QR-Code, die übrigen stehen als Text darunter.
 */
export function brauchbareAdressen(serverUrls: readonly string[] | undefined): string[] {
  return (serverUrls ?? []).filter((url) => url.trim() !== "" && !istNurDiesesGeraet(url));
}

function LokaleAdresseWarnung() {
  const { t } = useTranslation("system");
  if (!istNurDiesesGeraet()) return null;
  return (
    <div className={s.warnkasten} role="alert">
      <TriangleAlert className={s.warnSymbol} aria-hidden />
      <div>
        <strong>{t("geraete.lokal_titel", { adresse: window.location.host })}</strong>
        <p>{t("geraete.lokal_text")}</p>
      </div>
    </div>
  );
}

function KoppelDialog({
  rollen,
  onSchliessen,
}: {
  rollen: Rolle[] | undefined;
  onSchliessen: () => void;
}) {
  const { t, i18n } = useTranslation("system");
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [rolle, setRolle] = useState<string>(OHNE_ROLLE);
  const [jetzt, setJetzt] = useState(() => Date.now());
  // Geräte, die es schon vor dem Code gab; ein neues in der Liste heißt: gekoppelt.
  const [vorher, setVorher] = useState<ReadonlySet<string> | null>(null);

  const erzeugen = useMutation({
    mutationFn: async () => {
      const bekannte = await queryClient.ensureQueryData(geraeteAbfrage());
      const code = await apiSenden<Kopplungscode>("POST", "/devices/pairing-codes", {
        name: name.trim() || null,
        default_role_id: rolle === OHNE_ROLLE ? null : rolle,
      });
      return { code, bekannte };
    },
    onSuccess: ({ bekannte }) => {
      setJetzt(Date.now());
      setVorher((alt) => alt ?? new Set(bekannte.map((geraet) => geraet.id)));
      void queryClient.invalidateQueries({ queryKey: ["auth", "protokoll"] });
    },
  });
  const code = erzeugen.data?.code;
  // Das Ereignis „device.paired“ lädt die Liste neu; zur Sicherheit auch selbst nachsehen.
  const geraete = useQuery({
    ...geraeteAbfrage(),
    enabled: vorher !== null,
    refetchInterval: (abfrage) =>
      vorher && !abfrage.state.data?.some((geraet) => !vorher.has(geraet.id)) ? 3000 : false,
  });
  const neuesGeraet = vorher ? geraete.data?.find((geraet) => !vorher.has(geraet.id)) : undefined;

  useEffect(() => {
    if (!code) return;
    const timer = setInterval(() => setJetzt(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [code]);

  const rest = code ? (new Date(code.expires_at).getTime() - jetzt) / 1000 : 0;
  // Der Server nennt seine Adressen im Netz; sonst gilt die Adresse dieses Browsers.
  const brauchbar = brauchbareAdressen(code?.server_urls);
  const adresse = code ? kopplungsAdresse(code.pair_path, brauchbar[0]) : "";
  const weitere = code
    ? brauchbar.slice(1).map((url) => kopplungsAdresse(code.pair_path, url))
    : [];

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    erzeugen.mutate();
  };

  return (
    <Dialog opened onClose={onSchliessen} title={t("geraete.code_titel")} centered size="lg">
      {!code ? (
        <form className={s.formular} onSubmit={absenden}>
          <p className={s.einleitung}>{t("geraete.code_einleitung")}</p>
          <LokaleAdresseWarnung />
          <TextInput
            size="md"
            label={t("geraete.code_name")}
            placeholder={t("geraete.code_name_platzhalter")}
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            maxLength={100}
            data-autofocus
          />
          <Select
            size="md"
            label={t("geraete.code_rolle")}
            description={t("geraete.rolle_hinweis")}
            inputWrapperOrder={["label", "input", "description", "error"]}
            data={rollenAuswahl(rollen, t("geraete.rolle_keine"), t("geraete.rolle_nur_mit_pin"))}
            value={rolle}
            allowDeselect={false}
            disabled={!rollen}
            error={rollenFeldFehler(erzeugen.error)}
            onChange={(wert) => {
              setRolle(wert ?? OHNE_ROLLE);
              if (erzeugen.isError) erzeugen.reset();
            }}
            comboboxProps={{ withinPortal: true }}
          />
          {!rollenFeldFehler(erzeugen.error) && <FehlerHinweis fehler={erzeugen.error} />}
          <div className={s.aktionen}>
            <Button
              type="submit"
              loading={erzeugen.isPending}
              leftSection={<QrSymbol aria-hidden />}
            >
              {t("geraete.code_erzeugen")}
            </Button>
            <Button variant="default" onClick={onSchliessen}>
              {t("allgemein.abbrechen")}
            </Button>
          </div>
        </form>
      ) : (
        <div className={s.koppelSchritte}>
          {brauchbar.length === 0 && <LokaleAdresseWarnung />}
          <h3 className={s.aufgabenTitel}>{t("geraete.schritte")}</h3>
          <ol className={s.schritte}>
            <li className={s.schritt}>
              <span className={`${s.schrittNr} num`} aria-hidden>
                1
              </span>
              <div className={s.schrittInhalt}>
                <p>{t("geraete.schritt_1")}</p>
                {rest > 0 && !neuesGeraet ? (
                  <div className={s.code}>
                    <QrCode
                      text={adresse}
                      groesse={220}
                      beschriftung={t("geraete.code_qr", { adresse })}
                    />
                    <span className={`${s.adresse} num`}>
                      {t("geraete.code_adresse")}: {adresse}
                    </span>
                    {weitere.length > 0 && (
                      <span className={`${s.adresse} num`}>
                        {t("geraete.code_weitere", { count: weitere.length })}:{" "}
                        {weitere.join(" · ")}
                      </span>
                    )}
                  </div>
                ) : (
                  !neuesGeraet && <p className={s.schlecht}>{t("geraete.code_abgelaufen")}</p>
                )}
              </div>
            </li>
            <li className={s.schritt}>
              <span className={`${s.schrittNr} num`} aria-hidden>
                2
              </span>
              <div className={s.schrittInhalt}>
                <p>{t("geraete.schritt_2")}</p>
                {rest > 0 && !neuesGeraet && (
                  <>
                    <output className={`${s.codeText} num`} aria-label={t("auth:koppeln.code")}>
                      {codeGruppiert(code.code)}
                    </output>
                    <span className="num gedaempft">
                      {t("geraete.code_gueltig", {
                        zeit: formatZeitpunkt(code.expires_at, i18n.language),
                        rest: formatRestzeit(rest),
                      })}
                    </span>
                  </>
                )}
              </div>
            </li>
            <li className={s.schritt} data-erledigt={neuesGeraet ? "ja" : undefined}>
              <span className={`${s.schrittNr} num`} aria-hidden>
                {neuesGeraet ? <CircleCheck aria-hidden /> : "3"}
              </span>
              <div className={s.schrittInhalt}>
                <p>{t("geraete.schritt_3")}</p>
                <p role="status" className={neuesGeraet ? s.gut : "gedaempft"}>
                  {neuesGeraet
                    ? t("geraete.gekoppelt", { name: neuesGeraet.name })
                    : rest > 0
                      ? t("geraete.schritt_3_warten")
                      : null}
                </p>
              </div>
            </li>
          </ol>
          <div className={s.dialogKnoepfe}>
            {!neuesGeraet && (
              <Button
                variant="default"
                onClick={() => erzeugen.mutate()}
                loading={erzeugen.isPending}
              >
                {t("geraete.code_neu")}
              </Button>
            )}
            <Button onClick={onSchliessen}>{t("geraete.code_fertig")}</Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
