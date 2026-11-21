import {
  ActionIcon,
  Button,
  Checkbox,
  Menu,
  Modal,
  SegmentedControl,
  Select,
  Skeleton,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, MoreVertical, Pencil, Plus, Trash2 } from "lucide-react";
import { type FormEvent, type ReactNode, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { berechtigungenAbfrage, rollenAbfrage, schluessel } from "../../api/abfragen";
import { apiSenden } from "../../api/client";
import type { Rolle } from "../../api/typenSystem";
import { gewaehrt } from "../../app/berechtigungen";
import { Bestaetigung } from "../../components/Bestaetigung";
import { FehlerHinweis, useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { Fehlerzustand } from "../../components/Zustand";
import { formatZahl } from "../../lib/format";
import {
  type Berechtigungsgruppe,
  gleicheEintraege,
  gruppieren,
  textSchluessel,
  ueberMuster,
  umschalten,
} from "./rollenMatrix";
import s from "./system.module.css";

/** Verständlicher Name einer Berechtigung, Rückfall auf den technischen Namen. */
function useRechtName() {
  const { t } = useTranslation("system");
  return (name: string) => t(`berechtigungen.${textSchluessel(name)}`, { defaultValue: name });
}

export function RollenPanel() {
  const { t } = useTranslation("system");
  const queryClient = useQueryClient();
  const fehlerText = useFehlerText();
  const rollen = useQuery(rollenAbfrage());
  const berechtigungen = useQuery(berechtigungenAbfrage());
  const schmal = useMediaQuery("(max-width: 760px)");
  const [entwurf, setEntwurf] = useState<Record<string, string[]>>({});
  const [anlegen, setAnlegen] = useState(false);

  const gruppen = useMemo(() => gruppieren(berechtigungen.data ?? []), [berechtigungen.data]);
  const bekannte = useMemo(() => gruppen.flatMap((gruppe) => gruppe.berechtigungen), [gruppen]);

  const geaendert = (rollen.data ?? []).filter((rolle) => {
    const neu = entwurf[rolle.id];
    return neu !== undefined && !gleicheEintraege(neu, rolle.permissions);
  });

  const speichern = useMutation({
    mutationFn: async () => {
      for (const rolle of geaendert) {
        await apiSenden<Rolle>("PATCH", `/roles/${encodeURIComponent(rolle.id)}`, {
          permissions: entwurf[rolle.id],
        });
      }
    },
    onSuccess: () => {
      setEntwurf({});
      zeigeMeldung({ ton: "erfolg", titel: t("rollen.gespeichert") });
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.rollen });
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.status });
    },
  });

  const eintraegeVon = (rolle: Rolle) => entwurf[rolle.id] ?? rolle.permissions;
  const setzen = (rolle: Rolle, recht: string, an: boolean) =>
    setEntwurf((alt) => ({
      ...alt,
      [rolle.id]: umschalten(eintraegeVon(rolle), bekannte, recht, an),
    }));

  return (
    <section className="panel" aria-labelledby="rollen-titel">
      <div className={s.kopf}>
        <h2 className="h-section" id="rollen-titel">
          {t("rollen.titel")}
        </h2>
        <Button
          variant="default"
          leftSection={<Plus aria-hidden />}
          onClick={() => setAnlegen(true)}
          disabled={!rollen.data}
        >
          {t("rollen.anlegen")}
        </Button>
      </div>
      <p className={s.einleitung}>{t("rollen.einleitung")}</p>

      {rollen.isPending || berechtigungen.isPending ? (
        <Skeleton height={320} radius="md" />
      ) : rollen.isError || berechtigungen.isError ? (
        <Fehlerzustand
          fehler={rollen.error ?? berechtigungen.error}
          onErneut={() => {
            void rollen.refetch();
            void berechtigungen.refetch();
          }}
        />
      ) : gruppen.length === 0 ? (
        <p className={s.hinweis}>{t("rollen.leer")}</p>
      ) : schmal ? (
        <RollenListe
          rollen={rollen.data}
          gruppen={gruppen}
          eintraegeVon={eintraegeVon}
          setzen={setzen}
        />
      ) : (
        <RollenMatrix
          rollen={rollen.data}
          gruppen={gruppen}
          eintraegeVon={eintraegeVon}
          setzen={setzen}
          entwurf={entwurf}
        />
      )}

      {geaendert.length > 0 && (
        <div className={s.speicherleiste}>
          <span>
            {t("rollen.aenderungen", {
              count: geaendert.length,
              anzahl: formatZahl(geaendert.length),
            })}
          </span>
          <FehlerHinweis fehler={speichern.error} />
          <div className={s.aktionen}>
            <Button loading={speichern.isPending} onClick={() => speichern.mutate()}>
              {t("allgemein.speichern")}
            </Button>
            <Button variant="default" disabled={speichern.isPending} onClick={() => setEntwurf({})}>
              {t("allgemein.verwerfen")}
            </Button>
          </div>
        </div>
      )}
      {speichern.isError && geaendert.length === 0 && (
        <p className={s.laufFehler}>{fehlerText(speichern.error)}</p>
      )}

      {anlegen && rollen.data && (
        <RolleAnlegen rollen={rollen.data} onSchliessen={() => setAnlegen(false)} />
      )}
    </section>
  );
}

interface AnsichtProps {
  rollen: Rolle[];
  gruppen: Berechtigungsgruppe[];
  eintraegeVon: (rolle: Rolle) => string[];
  setzen: (rolle: Rolle, recht: string, an: boolean) => void;
}

function RechtZelle({
  rolle,
  recht,
  eintraege,
  setzen,
}: {
  rolle: Rolle;
  recht: string;
  eintraege: string[];
  setzen: AnsichtProps["setzen"];
}) {
  const { t } = useTranslation("system");
  const rechtName = useRechtName();
  const an = rolle.is_system || gewaehrt(eintraege, recht);
  const muster = rolle.is_system ? null : ueberMuster(eintraege, recht);
  const beschriftung = t(an ? "rollen.hat" : "rollen.hat_nicht", {
    rolle: rolle.name,
    recht: rechtName(recht),
  });
  const feld = (
    <span className={s.zelle}>
      <Checkbox
        size="md"
        checked={an}
        disabled={rolle.is_system}
        aria-label={beschriftung}
        onChange={(e) => setzen(rolle, recht, e.currentTarget.checked)}
      />
      {muster && <span className={`${s.muster} num`}>{muster}</span>}
    </span>
  );
  return muster ? <Tooltip label={t("rollen.ueber_muster", { muster })}>{feld}</Tooltip> : feld;
}

function RollenMatrix({
  rollen,
  gruppen,
  eintraegeVon,
  setzen,
  entwurf,
}: AnsichtProps & { entwurf: Record<string, string[]> }) {
  const { t } = useTranslation("system");
  const rechtName = useRechtName();
  return (
    <div className={s.matrixRahmen}>
      <table className={s.matrix}>
        <thead>
          <tr>
            <th scope="col">{t("rollen.berechtigung")}</th>
            {rollen.map((rolle) => (
              <th
                key={rolle.id}
                scope="col"
                className={
                  entwurf[rolle.id] && !gleicheEintraege(entwurf[rolle.id] ?? [], rolle.permissions)
                    ? s.geaendert
                    : undefined
                }
              >
                <RollenKopf rolle={rolle} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {gruppen.map((gruppe) => (
            <GruppeZeilen key={gruppe.modul} gruppe={gruppe} spalten={rollen.length + 1}>
              {gruppe.berechtigungen.map((recht) => (
                <tr key={recht}>
                  <th scope="row" className={s.rechtName}>
                    <span>{rechtName(recht)}</span>
                    <small>{recht}</small>
                  </th>
                  {rollen.map((rolle) => (
                    <td key={rolle.id}>
                      <RechtZelle
                        rolle={rolle}
                        recht={recht}
                        eintraege={eintraegeVon(rolle)}
                        setzen={setzen}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </GruppeZeilen>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GruppeZeilen({
  gruppe,
  spalten,
  children,
}: {
  gruppe: Berechtigungsgruppe;
  spalten: number;
  children: ReactNode;
}) {
  return (
    <>
      <tr className={s.gruppe}>
        <td colSpan={spalten} className={s.gruppeZelle}>
          {gruppe.titel}
        </td>
      </tr>
      {children}
    </>
  );
}

/** Schmale Bildschirme: eine Rolle wählen, ihre Rechte als Liste. */
function RollenListe({ rollen, gruppen, eintraegeVon, setzen }: AnsichtProps) {
  const { t } = useTranslation("system");
  const rechtName = useRechtName();
  const [gewaehlt, setGewaehlt] = useState(rollen[0]?.id ?? "");
  const rolle = rollen.find((eintrag) => eintrag.id === gewaehlt) ?? rollen[0];
  if (!rolle) return null;

  return (
    <div className={s.einstellungen}>
      {rollen.length <= 3 ? (
        <SegmentedControl
          fullWidth
          value={rolle.id}
          onChange={setGewaehlt}
          data={rollen.map((eintrag) => ({ value: eintrag.id, label: eintrag.name }))}
        />
      ) : (
        <Select
          size="md"
          label={t("rollen.rolle_waehlen")}
          value={rolle.id}
          allowDeselect={false}
          onChange={(wert) => wert && setGewaehlt(wert)}
          data={rollen.map((eintrag) => ({ value: eintrag.id, label: eintrag.name }))}
          comboboxProps={{ withinPortal: true }}
        />
      )}
      <RollenKopf rolle={rolle} />
      {gruppen.map((gruppe) => (
        <div key={gruppe.modul} className={s.einstellungen}>
          <span className="h-label">{gruppe.titel}</span>
          <ul className={s.rechteListe}>
            {gruppe.berechtigungen.map((recht) => (
              <li key={recht}>
                <span className={s.rechtName}>
                  <span>{rechtName(recht)}</span>
                  <small>{recht}</small>
                </span>
                <RechtZelle
                  rolle={rolle}
                  recht={recht}
                  eintraege={eintraegeVon(rolle)}
                  setzen={setzen}
                />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function RollenKopf({ rolle }: { rolle: Rolle }) {
  const { t } = useTranslation("system");
  const queryClient = useQueryClient();
  const fehlerText = useFehlerText();
  const [frage, setFrage] = useState<"umbenennen" | "loeschen" | null>(null);
  const [name, setName] = useState(rolle.name);

  const umbenennen = useMutation({
    mutationFn: () =>
      apiSenden<Rolle>("PATCH", `/roles/${encodeURIComponent(rolle.id)}`, { name: name.trim() }),
    onSuccess: () => {
      setFrage(null);
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.rollen });
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.status });
    },
  });
  const loeschen = useMutation({
    mutationFn: () => apiSenden("DELETE", `/roles/${encodeURIComponent(rolle.id)}`),
    onSuccess: () => {
      setFrage(null);
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.rollen });
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.geraete });
      zeigeMeldung({ ton: "info", titel: t("rollen.geloescht") });
    },
  });

  return (
    <span className={s.rollenKopf}>
      <span className={s.rollenName}>
        {rolle.is_system && (
          <Tooltip label={t("rollen.system")}>
            <Lock aria-label={t("rollen.system")} />
          </Tooltip>
        )}
        {rolle.name}
        {!rolle.is_system && (
          <Menu position="bottom-end" withinPortal>
            <Menu.Target>
              <ActionIcon
                variant="subtle"
                color="gray"
                size={36}
                aria-label={t("allgemein.aktionen", { name: rolle.name })}
              >
                <MoreVertical aria-hidden />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item
                leftSection={<Pencil aria-hidden />}
                onClick={() => {
                  setName(rolle.name);
                  umbenennen.reset();
                  setFrage("umbenennen");
                }}
              >
                {t("rollen.umbenennen")}
              </Menu.Item>
              <Menu.Item
                color="red"
                leftSection={<Trash2 aria-hidden />}
                onClick={() => {
                  loeschen.reset();
                  setFrage("loeschen");
                }}
              >
                {t("allgemein.loeschen")}
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        )}
      </span>
      <small className="num">
        {t("rollen.personen", { count: rolle.user_count, anzahl: formatZahl(rolle.user_count) })}
      </small>

      <Modal
        opened={frage === "umbenennen"}
        onClose={() => setFrage(null)}
        title={t("rollen.umbenennen_titel")}
        centered
      >
        <form
          className={s.formular}
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (name.trim()) umbenennen.mutate();
          }}
        >
          <TextInput
            size="md"
            label={t("rollen.name")}
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            maxLength={100}
            data-autofocus
          />
          <FehlerHinweis fehler={umbenennen.error} />
          <div className={s.aktionen}>
            <Button type="submit" loading={umbenennen.isPending} disabled={!name.trim()}>
              {t("allgemein.speichern")}
            </Button>
            <Button variant="default" onClick={() => setFrage(null)}>
              {t("allgemein.abbrechen")}
            </Button>
          </div>
        </form>
      </Modal>
      <Bestaetigung
        offen={frage === "loeschen"}
        titel={t("rollen.loeschen_titel", { name: rolle.name })}
        text={<p>{t("rollen.loeschen_text")}</p>}
        bestaetigen={t("allgemein.loeschen")}
        abbrechen={t("allgemein.abbrechen")}
        ton="gefahr"
        laedt={loeschen.isPending}
        fehler={loeschen.isError ? fehlerText(loeschen.error) : undefined}
        onSchliessen={() => setFrage(null)}
        onBestaetigen={() => loeschen.mutate()}
      />
    </span>
  );
}

function RolleAnlegen({ rollen, onSchliessen }: { rollen: Rolle[]; onSchliessen: () => void }) {
  const { t } = useTranslation("system");
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [vorlage, setVorlage] = useState<string>("");
  const anlegen = useMutation({
    mutationFn: () => {
      const quelle = rollen.find((rolle) => rolle.id === vorlage);
      const rechte = quelle ? (quelle.is_system ? ["*"] : quelle.permissions) : [];
      return apiSenden<Rolle>("POST", "/roles", { name: name.trim(), permissions: rechte });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.rollen });
      zeigeMeldung({ ton: "erfolg", titel: t("rollen.angelegt") });
      onSchliessen();
    },
  });

  return (
    <Modal opened onClose={onSchliessen} title={t("rollen.anlegen_titel")} centered>
      <form
        className={s.formular}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (name.trim()) anlegen.mutate();
        }}
      >
        <TextInput
          size="md"
          label={t("rollen.name")}
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          maxLength={100}
          data-autofocus
        />
        <Select
          size="md"
          label={t("rollen.vorlage")}
          value={vorlage}
          allowDeselect={false}
          onChange={(wert) => setVorlage(wert ?? "")}
          data={[
            { value: "", label: t("rollen.vorlage_keine") },
            ...rollen.map((rolle) => ({ value: rolle.id, label: rolle.name })),
          ]}
          comboboxProps={{ withinPortal: true }}
        />
        <FehlerHinweis fehler={anlegen.error} />
        <div className={s.aktionen}>
          <Button type="submit" loading={anlegen.isPending} disabled={!name.trim()}>
            {t("rollen.anlegen")}
          </Button>
          <Button variant="default" onClick={onSchliessen}>
            {t("allgemein.abbrechen")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
