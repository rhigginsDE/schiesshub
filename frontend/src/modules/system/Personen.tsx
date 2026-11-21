import {
  ActionIcon,
  Button,
  Menu,
  Modal,
  PasswordInput,
  Select,
  Skeleton,
  TextInput,
} from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { TFunction } from "i18next";
import { KeyRound, MoreVertical, UserCheck, UserPlus, UserX } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { personenAbfrage, rollenAbfrage, schluessel } from "../../api/abfragen";
import { apiSenden } from "../../api/client";
import type { Person, Rolle } from "../../api/typenSystem";
import { useAnmeldung } from "../../app/anmeldung";
import { useDarf } from "../../app/berechtigungen";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { FehlerHinweis, useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { PIN_MAX_LAENGE, PIN_MIN_LAENGE, pinGueltig } from "../auth/eingaben";
import { formatWann } from "./format";
import { RollenPanel } from "./Rollen";
import s from "./system.module.css";

export function PersonenBereich() {
  const darfPersonen = useDarf("user.manage");
  const darfRollen = useDarf("role.manage");
  return (
    <>
      {darfPersonen && <PersonenPanel />}
      {darfRollen && <RollenPanel />}
    </>
  );
}

function invalidieren(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: schluessel.auth.personen });
  void queryClient.invalidateQueries({ queryKey: schluessel.auth.rollen });
  void queryClient.invalidateQueries({ queryKey: schluessel.auth.anmeldePersonen });
}

function PersonenPanel() {
  const { t } = useTranslation("system");
  const personen = useQuery(personenAbfrage());
  const darfRollen = useDarf("role.manage");
  const rollen = useQuery({ ...rollenAbfrage(), enabled: darfRollen });
  const [anlegen, setAnlegen] = useState(false);

  return (
    <section className="panel" aria-labelledby="personen-titel">
      <div className={s.kopf}>
        <h2 className="h-section" id="personen-titel">
          {t("personen.titel")}
        </h2>
        <Button
          leftSection={<UserPlus aria-hidden />}
          onClick={() => setAnlegen(true)}
          disabled={!rollen.data}
        >
          {t("personen.anlegen")}
        </Button>
      </div>
      <p className={s.einleitung}>{t("personen.einleitung")}</p>
      {personen.isPending ? (
        <Skeleton height={200} radius="md" />
      ) : personen.isError ? (
        <Fehlerzustand fehler={personen.error} onErneut={() => void personen.refetch()} />
      ) : personen.data.length === 0 ? (
        <Leerzustand
          icon={UserPlus}
          titel={t("personen.leer_titel")}
          text={t("personen.leer_text")}
        />
      ) : (
        <ul className={s.liste}>
          {personen.data.map((person) => (
            <PersonZeile key={person.id} person={person} rollen={rollen.data} />
          ))}
        </ul>
      )}
      {anlegen && rollen.data && (
        <PersonAnlegen rollen={rollen.data} onSchliessen={() => setAnlegen(false)} />
      )}
    </section>
  );
}

function PersonZeile({ person, rollen }: { person: Person; rollen: Rolle[] | undefined }) {
  const { t, i18n } = useTranslation("system");
  const queryClient = useQueryClient();
  const fehlerText = useFehlerText();
  const { status } = useAnmeldung();
  const [frage, setFrage] = useState<"pin" | "deaktivieren" | null>(null);

  const aendern = useMutation({
    mutationFn: (inhalt: { role_id?: string; active?: boolean }) =>
      apiSenden<Person>("PATCH", `/users/${encodeURIComponent(person.id)}`, inhalt),
    onSuccess: () => {
      setFrage(null);
      invalidieren(queryClient);
      if (status?.user?.id === person.id)
        void queryClient.invalidateQueries({ queryKey: schluessel.auth.status });
      zeigeMeldung({ ton: "erfolg", titel: t("personen.geaendert") });
    },
    onError: (fehler) => {
      if (!frage) zeigeMeldung({ ton: "krit", titel: person.name, text: fehlerText(fehler) });
    },
  });

  const gesperrt = person.locked_until && new Date(person.locked_until).getTime() > Date.now();

  return (
    <li>
      <span className={s.eintrag}>
        <strong>
          {person.name}{" "}
          <span className={s.marken}>
            {!person.active && <Chip ton="neutral">{t("personen.inaktiv")}</Chip>}
            {gesperrt && person.locked_until && (
              <Chip ton="warn">
                {t("personen.gesperrt_bis", {
                  zeit: formatWann(person.locked_until, new Date(), i18n.language),
                })}
              </Chip>
            )}
          </span>
        </strong>
      </span>
      <Select
        className={s.auswahl}
        size="md"
        aria-label={t("personen.rolle")}
        data={(rollen ?? []).map((rolle) => ({ value: rolle.id, label: rolle.name }))}
        value={person.role_id}
        placeholder={t("geraete.rolle_unbekannt")}
        disabled={!rollen || aendern.isPending}
        allowDeselect={false}
        onChange={(wert) => {
          if (wert && wert !== person.role_id) aendern.mutate({ role_id: wert });
        }}
      />
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <ActionIcon
            variant="default"
            size={44}
            aria-label={t("allgemein.aktionen", { name: person.name })}
          >
            <MoreVertical aria-hidden />
          </ActionIcon>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item leftSection={<KeyRound aria-hidden />} onClick={() => setFrage("pin")}>
            {t("personen.pin_zuruecksetzen")}
          </Menu.Item>
          {person.active ? (
            <Menu.Item
              color="red"
              leftSection={<UserX aria-hidden />}
              onClick={() => {
                aendern.reset();
                setFrage("deaktivieren");
              }}
            >
              {t("personen.deaktivieren")}
            </Menu.Item>
          ) : (
            <Menu.Item
              leftSection={<UserCheck aria-hidden />}
              onClick={() => aendern.mutate({ active: true })}
            >
              {t("personen.aktivieren")}
            </Menu.Item>
          )}
        </Menu.Dropdown>
      </Menu>

      {frage === "pin" && <PinZuruecksetzen person={person} onSchliessen={() => setFrage(null)} />}
      <Bestaetigung
        offen={frage === "deaktivieren"}
        titel={t("personen.deaktivieren_titel", { name: person.name })}
        text={<p>{t("personen.deaktivieren_text")}</p>}
        bestaetigen={t("personen.deaktivieren")}
        abbrechen={t("allgemein.abbrechen")}
        ton="gefahr"
        laedt={aendern.isPending}
        fehler={aendern.isError ? fehlerText(aendern.error) : undefined}
        onSchliessen={() => setFrage(null)}
        onBestaetigen={() => aendern.mutate({ active: false })}
      />
    </li>
  );
}

interface PinFelderProps {
  pin: string;
  pin2: string;
  onPin: (wert: string) => void;
  onPin2: (wert: string) => void;
  fehler: { pin?: string; pin2?: string };
}

function PinFelder({ pin, pin2, onPin, onPin2, fehler }: PinFelderProps) {
  const { t } = useTranslation("system");
  return (
    <>
      <PasswordInput
        visibilityToggleButtonProps={{ "aria-label": t("shell:sichtbar_umschalten") }}
        size="md"
        label={t("personen.pin")}
        description={t("personen.pin_hinweis", { anzahl: PIN_MIN_LAENGE })}
        value={pin}
        onChange={(e) => onPin(e.currentTarget.value.replace(/\D/g, ""))}
        error={fehler.pin}
        inputMode="numeric"
        autoComplete="new-password"
        maxLength={PIN_MAX_LAENGE}
        classNames={{ innerInput: "num" }}
      />
      <PasswordInput
        visibilityToggleButtonProps={{ "aria-label": t("shell:sichtbar_umschalten") }}
        size="md"
        label={t("personen.pin_wiederholen")}
        value={pin2}
        onChange={(e) => onPin2(e.currentTarget.value.replace(/\D/g, ""))}
        error={fehler.pin2}
        inputMode="numeric"
        autoComplete="new-password"
        maxLength={PIN_MAX_LAENGE}
        classNames={{ innerInput: "num" }}
      />
    </>
  );
}

function pinFehler(pin: string, pin2: string, t: TFunction<"system">) {
  const fehler: { pin?: string; pin2?: string } = {};
  if (!pinGueltig(pin)) fehler.pin = t("personen.fehler_pin", { anzahl: PIN_MIN_LAENGE });
  else if (pin !== pin2) fehler.pin2 = t("personen.fehler_pin_gleich");
  return fehler;
}

function PersonAnlegen({ rollen, onSchliessen }: { rollen: Rolle[]; onSchliessen: () => void }) {
  const { t } = useTranslation("system");
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [pin2, setPin2] = useState("");
  const [rolle, setRolle] = useState<string | null>(null);
  const [fehler, setFehler] = useState<{
    name?: string;
    pin?: string;
    pin2?: string;
    rolle?: string;
  }>({});

  const anlegen = useMutation({
    mutationFn: () =>
      apiSenden<Person>("POST", "/users", { name: name.trim(), pin, role_id: rolle }),
    onSuccess: () => {
      invalidieren(queryClient);
      zeigeMeldung({ ton: "erfolg", titel: t("personen.angelegt") });
      onSchliessen();
    },
  });

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    const neu = { ...pinFehler(pin, pin2, t) } as typeof fehler;
    if (!name.trim()) neu.name = t("personen.fehler_name");
    if (!rolle) neu.rolle = t("personen.fehler_rolle");
    setFehler(neu);
    if (Object.keys(neu).length === 0) anlegen.mutate();
  };

  return (
    <Modal opened onClose={onSchliessen} title={t("personen.anlegen_titel")} centered>
      <form className={s.formular} onSubmit={absenden} noValidate>
        <TextInput
          size="md"
          label={t("personen.name")}
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          error={fehler.name}
          maxLength={100}
          data-autofocus
        />
        <Select
          size="md"
          label={t("personen.rolle")}
          data={rollen.map((eintrag) => ({ value: eintrag.id, label: eintrag.name }))}
          value={rolle}
          onChange={setRolle}
          error={fehler.rolle}
          comboboxProps={{ withinPortal: true }}
        />
        <PinFelder pin={pin} pin2={pin2} onPin={setPin} onPin2={setPin2} fehler={fehler} />
        <FehlerHinweis fehler={anlegen.error} />
        <div className={s.aktionen}>
          <Button type="submit" loading={anlegen.isPending}>
            {t("personen.anlegen")}
          </Button>
          <Button variant="default" onClick={onSchliessen}>
            {t("allgemein.abbrechen")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function PinZuruecksetzen({ person, onSchliessen }: { person: Person; onSchliessen: () => void }) {
  const { t } = useTranslation("system");
  const queryClient = useQueryClient();
  const [pin, setPin] = useState("");
  const [pin2, setPin2] = useState("");
  const [fehler, setFehler] = useState<{ pin?: string; pin2?: string }>({});

  const speichern = useMutation({
    mutationFn: () =>
      apiSenden<Person>("POST", `/users/${encodeURIComponent(person.id)}/pin`, { pin }),
    onSuccess: () => {
      invalidieren(queryClient);
      zeigeMeldung({ ton: "erfolg", titel: t("personen.pin_gespeichert") });
      onSchliessen();
    },
  });

  const absenden = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    const neu = pinFehler(pin, pin2, t);
    setFehler(neu);
    if (Object.keys(neu).length === 0) speichern.mutate();
  };

  return (
    <Modal
      opened
      onClose={onSchliessen}
      title={t("personen.pin_titel", { name: person.name })}
      centered
    >
      <form className={s.formular} onSubmit={absenden} noValidate>
        <p className={s.einleitung}>{t("personen.pin_text")}</p>
        <PinFelder pin={pin} pin2={pin2} onPin={setPin} onPin2={setPin2} fehler={fehler} />
        <FehlerHinweis fehler={speichern.error} />
        <div className={s.aktionen}>
          <Button type="submit" loading={speichern.isPending}>
            {t("personen.pin_zuruecksetzen")}
          </Button>
          <Button variant="default" onClick={onSchliessen}>
            {t("allgemein.abbrechen")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
