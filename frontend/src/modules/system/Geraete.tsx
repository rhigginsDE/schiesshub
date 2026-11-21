import { ActionIcon, Button, Menu, Modal, Select, Skeleton, TextInput } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  MonitorSmartphone,
  MoreVertical,
  Pencil,
  QrCode as QrSymbol,
  Trash2,
  Unlock,
} from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { geraeteAbfrage, rollenAbfrage, schluessel } from "../../api/abfragen";
import { apiSenden } from "../../api/client";
import type { Geraet, Kopplungscode, Rolle } from "../../api/typenSystem";
import { useDarf } from "../../app/berechtigungen";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { FehlerHinweis, useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { QrCode } from "../../components/QrCode";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { codeGruppiert, formatRestzeit } from "../auth/eingaben";
import { formatWann, formatZeitpunkt } from "./format";
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

function rollenAuswahl(rollen: Rolle[] | undefined, ohne: string) {
  return [
    { value: OHNE_ROLLE, label: ohne },
    ...(rollen ?? []).map((rolle) => ({ value: rolle.id, label: rolle.name })),
  ];
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
      if (!frage) zeigeMeldung({ ton: "krit", titel: geraet.name, text: fehlerText(fehler) });
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
        aria-label={t("geraete.rolle")}
        data={rollenAuswahl(rollen, t("geraete.rolle_keine"))}
        value={geraet.default_role_id ?? OHNE_ROLLE}
        placeholder={rolleBekannt ? undefined : t("geraete.rolle_unbekannt")}
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

      <Modal
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
      </Modal>
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

  const erzeugen = useMutation({
    mutationFn: () =>
      apiSenden<Kopplungscode>("POST", "/devices/pairing-codes", {
        name: name.trim() || null,
        default_role_id: rolle === OHNE_ROLLE ? null : rolle,
      }),
    onSuccess: () => {
      setJetzt(Date.now());
      void queryClient.invalidateQueries({ queryKey: ["auth", "protokoll"] });
    },
  });
  const code = erzeugen.data;

  useEffect(() => {
    if (!code) return;
    const timer = setInterval(() => setJetzt(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [code]);

  const rest = code ? (new Date(code.expires_at).getTime() - jetzt) / 1000 : 0;
  const adresse = code ? kopplungsAdresse(code.pair_path) : "";

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    erzeugen.mutate();
  };

  return (
    <Modal opened onClose={onSchliessen} title={t("geraete.code_titel")} centered size="lg">
      {!code ? (
        <form className={s.formular} onSubmit={absenden}>
          <p className={s.einleitung}>{t("geraete.code_einleitung")}</p>
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
            data={rollenAuswahl(rollen, t("geraete.rolle_keine"))}
            value={rolle}
            allowDeselect={false}
            disabled={!rollen}
            onChange={(wert) => setRolle(wert ?? OHNE_ROLLE)}
            comboboxProps={{ withinPortal: true }}
          />
          <FehlerHinweis fehler={erzeugen.error} />
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
        <div className={s.code}>
          <p className={s.einleitung}>{t("geraete.code_anleitung")}</p>
          {rest > 0 ? (
            <>
              <QrCode
                text={adresse}
                groesse={240}
                beschriftung={t("geraete.code_qr", { adresse })}
              />
              <output className={`${s.codeText} num`} aria-label={t("auth:koppeln.code")}>
                {codeGruppiert(code.code)}
              </output>
              <span className="num gedaempft">
                {t("geraete.code_gueltig", {
                  zeit: formatZeitpunkt(code.expires_at, i18n.language),
                  rest: formatRestzeit(rest),
                })}
              </span>
              <span className={`${s.adresse} num`}>
                {t("geraete.code_adresse")}: {adresse}
              </span>
            </>
          ) : (
            <p className={s.schlecht}>{t("geraete.code_abgelaufen")}</p>
          )}
          <div className={s.aktionen}>
            <Button
              variant="default"
              onClick={() => erzeugen.mutate()}
              loading={erzeugen.isPending}
            >
              {t("geraete.code_neu")}
            </Button>
            <Button onClick={onSchliessen}>{t("geraete.code_fertig")}</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
