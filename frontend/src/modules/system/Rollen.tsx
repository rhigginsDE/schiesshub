import {
  ActionIcon,
  Button,
  Checkbox,
  Menu,
  SegmentedControl,
  Select,
  Skeleton,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, MoreVertical, Pencil, Plus, Trash2, TriangleAlert } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { berechtigungenAbfrage, rollenAbfrage, schluessel } from "../../api/abfragen";
import { apiSenden } from "../../api/client";
import type { Rolle } from "../../api/typenSystem";
import { gewaehrt } from "../../app/berechtigungen";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Dialog } from "../../components/Dialog";
import { EntwurfSchutz } from "../../components/EntwurfSchutz";
import { FehlerHinweis, useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { EntwurfRegister } from "../../components/useEntwurf";
import { Fehlerzustand } from "../../components/Zustand";
import { formatZahl } from "../../lib/format";
import r from "./Rollen.module.css";
import {
  type Berechtigungsgruppe,
  fehlendeVoraussetzungen,
  gleicheEintraege,
  gruppieren,
  hinzufuegen,
  luecke,
  rechtTaetigkeit,
  textSchluessel,
  ueberMuster,
  umschalten,
  voraussetzungen,
} from "./rollenMatrix";
import s from "./system.module.css";

/**
 * Verständlicher Name einer Berechtigung. Kennt die Sprachdatei sie nicht (neues Modul), entsteht
 * der Name aus Bereich und Tätigkeit („Anzeige: steuern“) statt aus dem technischen Namen.
 */
function useRechtName() {
  const { t } = useTranslation("system");
  const berechtigungen = useQuery(berechtigungenAbfrage());
  return (name: string) => {
    const bekannt = t(`berechtigungen.${textSchluessel(name)}`, { defaultValue: "" });
    if (bekannt) return bekannt;
    const eintrag = berechtigungen.data?.find((b) => b.permission === name);
    const bereich = eintrag?.module_title ?? t("rollen.rueckfall_bereich");
    const taetigkeit = rechtTaetigkeit(name);
    const verb = taetigkeit ? t(`rollen.taetigkeit.${taetigkeit}`, { defaultValue: "" }) : "";
    return verb
      ? t("rollen.rueckfall", { bereich, taetigkeit: verb })
      : t("rollen.rueckfall_weiteres", { bereich });
  };
}

/** „Turnier ansehen“ und „Starts ansehen“: Namen in Anführungszeichen, als Aufzählung. */
function useRechteListe() {
  const { i18n } = useTranslation();
  const rechtName = useRechtName();
  return (rechte: readonly string[]) =>
    new Intl.ListFormat(i18n.language, { type: "conjunction" }).format(
      rechte.map((recht) => `„${rechtName(recht)}“`),
    );
}

/** Voraussetzungen aller Berechtigungen, wie der Server sie meldet. */
function useVoraussetzungen() {
  const berechtigungen = useQuery(berechtigungenAbfrage());
  return useMemo(() => voraussetzungen(berechtigungen.data ?? []), [berechtigungen.data]);
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
  const braucht = useVoraussetzungen();

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
  const ergaenzen = (rolle: Rolle, rechte: readonly string[]) =>
    setEntwurf((alt) => ({
      ...alt,
      [rolle.id]: hinzufuegen(eintraegeVon(rolle), bekannte, rechte),
    }));

  // Beim Verlassen der Seite mit ungesetzten Häkchen nachfragen, wie im Turnier-Editor.
  const [register] = useState(() => new EntwurfRegister());
  const meldungId = useId();
  const ungespeichert = geaendert.length > 0;
  const meldung = useRef({
    geaendert: ungespeichert,
    verwerfen: () => setEntwurf({}),
    speichern: async () => false,
  });
  useEffect(() => {
    meldung.current = {
      geaendert: ungespeichert,
      verwerfen: () => setEntwurf({}),
      speichern: async () => {
        try {
          await speichern.mutateAsync();
          return true;
        } catch {
          return false;
        }
      },
    };
  });
  useEffect(() => {
    register.setze(meldungId, meldung);
    return () => register.entferne(meldungId);
  }, [register, meldungId]);
  useEffect(() => {
    meldung.current = { ...meldung.current, geaendert: ungespeichert };
    register.melde();
  }, [register, ungespeichert]);

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
          braucht={braucht}
        />
      ) : (
        <RollenMatrix
          rollen={rollen.data}
          gruppen={gruppen}
          eintraegeVon={eintraegeVon}
          setzen={setzen}
          braucht={braucht}
          entwurf={entwurf}
        />
      )}

      {rollen.data && (
        <Luecken
          rollen={rollen.data}
          bekannte={bekannte}
          braucht={braucht}
          eintraegeVon={eintraegeVon}
          ergaenzen={ergaenzen}
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
      <EntwurfSchutz register={register} ort={t("rollen.ort")} />
    </section>
  );
}

interface AnsichtProps {
  rollen: Rolle[];
  gruppen: Berechtigungsgruppe[];
  eintraegeVon: (rolle: Rolle) => string[];
  setzen: (rolle: Rolle, recht: string, an: boolean) => void;
  braucht: ReadonlyMap<string, readonly string[]>;
}

/**
 * Rollen, denen für ein gesetztes Recht ein anderes fehlt, ohne das es an der Station nichts nützt
 * (z. B. „Starts aufrufen“ ohne „Turnier ansehen“). Nur ein Hinweis mit Knopf; gesetzt wird nichts
 * von selbst.
 */
function Luecken({
  rollen,
  bekannte,
  braucht,
  eintraegeVon,
  ergaenzen,
}: {
  rollen: Rolle[];
  bekannte: readonly string[];
  braucht: ReadonlyMap<string, readonly string[]>;
  eintraegeVon: (rolle: Rolle) => string[];
  ergaenzen: (rolle: Rolle, rechte: readonly string[]) => void;
}) {
  const { t } = useTranslation("system");
  const liste = useRechteListe();
  const eintraege = rollen.flatMap((rolle) => {
    if (rolle.is_system) return [];
    const offen = luecke(eintraegeVon(rolle), bekannte, braucht);
    return offen ? [{ rolle, ...offen }] : [];
  });
  if (eintraege.length === 0) return null;
  return (
    <ul className={r.luecken} aria-label={t("rollen.luecken")}>
      {eintraege.map(({ rolle, rechte, fehlt }) => (
        <li key={rolle.id} className={r.luecke}>
          <TriangleAlert className={r.symbol} aria-hidden />
          <span className={r.lueckeText}>
            {t("rollen.luecke", {
              count: rechte.length,
              rolle: rolle.name,
              rechte: liste(rechte),
              fehlt: liste(fehlt),
            })}
          </span>
          <Button
            variant="default"
            size="sm"
            onClick={() => ergaenzen(rolle, fehlt)}
            aria-label={t("rollen.braucht_setzen_hinweis", {
              rolle: rolle.name,
              rechte: liste(fehlt),
            })}
          >
            {t("rollen.braucht_setzen")}
          </Button>
        </li>
      ))}
    </ul>
  );
}

/** Unter dem Namen einer Berechtigung: was sie außerdem braucht. */
function BrauchtZeile({ recht, braucht }: { recht: string; braucht: AnsichtProps["braucht"] }) {
  const { t } = useTranslation("system");
  const liste = useRechteListe();
  const noetig = braucht.get(recht);
  if (!noetig?.length) return null;
  return <span className={r.braucht}>{t("rollen.braucht", { rechte: liste(noetig) })}</span>;
}

function RechtZelle({
  rolle,
  recht,
  eintraege,
  setzen,
  braucht,
}: {
  rolle: Rolle;
  recht: string;
  eintraege: string[];
  setzen: AnsichtProps["setzen"];
  braucht: AnsichtProps["braucht"];
}) {
  const { t } = useTranslation("system");
  const rechtName = useRechtName();
  const liste = useRechteListe();
  const fehlt = rolle.is_system ? [] : fehlendeVoraussetzungen(eintraege, recht, braucht);
  const berechtigungen = useQuery(berechtigungenAbfrage());
  const an = rolle.is_system || gewaehrt(eintraege, recht);
  const muster = rolle.is_system ? null : ueberMuster(eintraege, recht);
  const beschriftung = t(an ? "rollen.hat" : "rollen.hat_nicht", {
    rolle: rolle.name,
    recht: rechtName(recht),
  });
  // Muster wie `start.*` in Klartext: „alle Rechte im Bereich Anmeldung und Starts“.
  const musterKurz = muster === "*" ? t("rollen.muster_alles_kurz") : t("rollen.muster_kurz");
  const musterLang =
    muster === "*"
      ? t("rollen.muster_alles")
      : t("rollen.muster_bereich", {
          bereich:
            berechtigungen.data?.find((b) => b.permission === recht)?.module_title ??
            t("rollen.rueckfall_bereich"),
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
      {muster && <span className={s.muster}>{musterKurz}</span>}
      {fehlt.length > 0 && (
        <Tooltip label={t("rollen.braucht_fehlt", { rechte: liste(fehlt) })} multiline maw={280}>
          <span className={r.fehlt}>
            <TriangleAlert aria-hidden />
            <span className="nur-screenreader">
              {t("rollen.braucht_fehlt", { rechte: liste(fehlt) })}
            </span>
          </span>
        </Tooltip>
      )}
    </span>
  );
  return muster ? (
    <Tooltip label={t("rollen.ueber_muster", { muster: musterLang })}>{feld}</Tooltip>
  ) : (
    feld
  );
}

function RollenMatrix({
  rollen,
  gruppen,
  eintraegeVon,
  setzen,
  braucht,
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
                  <th scope="row" className={s.rechtName} title={recht}>
                    <span>{rechtName(recht)}</span>
                    <BrauchtZeile recht={recht} braucht={braucht} />
                  </th>
                  {rollen.map((rolle) => (
                    <td key={rolle.id}>
                      <RechtZelle
                        rolle={rolle}
                        recht={recht}
                        eintraege={eintraegeVon(rolle)}
                        setzen={setzen}
                        braucht={braucht}
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
function RollenListe({ rollen, gruppen, eintraegeVon, setzen, braucht }: AnsichtProps) {
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
                <span className={s.rechtName} title={recht}>
                  <span>{rechtName(recht)}</span>
                  <BrauchtZeile recht={recht} braucht={braucht} />
                </span>
                <RechtZelle
                  rolle={rolle}
                  recht={recht}
                  eintraege={eintraegeVon(rolle)}
                  setzen={setzen}
                  braucht={braucht}
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
      zeigeMeldung({ ton: "erfolg", titel: t("rollen.umbenannt") });
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

      <Dialog
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
      </Dialog>
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
    <Dialog opened onClose={onSchliessen} title={t("rollen.anlegen_titel")} centered>
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
    </Dialog>
  );
}
