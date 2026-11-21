import {
  ActionIcon,
  Button,
  Loader,
  Menu,
  Tooltip,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { Link, Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  ChevronDown,
  KeyRound,
  LogIn,
  LogOut,
  Maximize2,
  Minimize2,
  MonitorSmartphone,
  Moon,
  RefreshCw,
  ShieldAlert,
  Sun,
  TriangleAlert,
  Usb,
  UserRound,
  UsersRound,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { schluessel } from "../api/abfragen";
import { EREIGNIS_VERBUNDEN, type EreignisZuordnung, useServerEreignisse } from "../api/ereignisse";
import { Chip } from "../components/Chip";
import { useFehlerText } from "../components/FehlerHinweis";
import { Meldungen, zeigeMeldung } from "../components/Meldungen";
import { Leerzustand } from "../components/Zustand";
import { formatUhrzeit } from "../lib/format";
import { istAnmeldePfad, PflichtSeite } from "../modules/auth/routen";
import s from "./AppShell.module.css";
import { AnmeldungProvider, useAnmeldung } from "./anmeldung";
import { darfMit, useRechte } from "./berechtigungen";
import { type ModulManifest, useAlleModule, useStationen } from "./modul";
import { useSeitenbreite } from "./seitenbreite";
import { useServerStatus } from "./serverStatus";
import { useSicherungsLage } from "./sicherungsLage";

/** Ereignisse, auf die die Shell selbst hört: Anmelde-Zustand und Sicherung. */
const SHELL_EREIGNISSE: EreignisZuordnung = {
  [EREIGNIS_VERBUNDEN]: [schluessel.auth.status, schluessel.sicherung.alle],
  "auth.setup": [schluessel.auth.status],
  "device.updated": [schluessel.auth.status],
  "device.deleted": [schluessel.auth.status],
  "role.updated": [schluessel.auth.status],
  "role.deleted": [schluessel.auth.status],
  "user.updated": [schluessel.auth.status],
  "backup.status": [schluessel.sicherung.status],
  "backup.completed": [schluessel.sicherung.alle],
  "backup.failed": [schluessel.sicherung.alle],
};

/** Rahmen jeder Seite: Kopfzeile mit Wortmarke, Stationen, Status, Anmeldung, Farbschema und Uhr. */
export function AppShell() {
  return (
    <AnmeldungProvider>
      <Rahmen />
      <Meldungen />
    </AnmeldungProvider>
  );
}

function useShellEreignisse() {
  const module = useAlleModule();
  const ereignisse = useMemo<EreignisZuordnung>(() => {
    const gesamt: Record<string, EreignisZuordnung[string][number][]> = {};
    for (const quelle of [SHELL_EREIGNISSE, ...module.map((modul) => modul.ereignisse ?? {})]) {
      for (const [name, keys] of Object.entries(quelle)) {
        gesamt[name] = [...(gesamt[name] ?? []), ...keys];
      }
    }
    return gesamt;
  }, [module]);
  useServerEreignisse(ereignisse);
}

function Rahmen() {
  useShellEreignisse();
  const { lage } = useAnmeldung();
  const pfad = useRouterState({ select: (zustand) => zustand.location.pathname });
  const anmeldeSeite = istAnmeldePfad(pfad);

  if (lage.pruefe) {
    return (
      <div className={s.rahmen}>
        <div className={s.laedt} aria-busy="true">
          <Loader color="gruen" />
        </div>
      </div>
    );
  }

  // Anmelde-Seiten und Sperre: schlanke Kopfzeile ohne Stationen.
  if (anmeldeSeite || lage.pflicht) {
    return (
      <div className={s.rahmen}>
        <header className={s.leiste}>
          <Marke />
          <div className={s.status}>
            <Statusanzeige />
            <FarbschemaUmschalter />
            <Uhr />
          </div>
        </header>
        <main className={s.inhalt}>
          {anmeldeSeite ? <Outlet /> : lage.pflicht && <PflichtSeite seite={lage.pflicht} />}
        </main>
      </div>
    );
  }

  return (
    <div className={s.rahmen}>
      <div className={s.oben}>
        <header className={s.leiste}>
          <Marke />
          <Stationsnavigation />
          <div className={s.status}>
            <Statusanzeige />
            <SicherungsChip />
            <AnmeldeAnzeige />
            <BreitenUmschalter />
            <FarbschemaUmschalter />
            <Uhr />
          </div>
        </header>
        <SicherungsBanner istAnzeige={pfad === "/anzeige" || pfad.startsWith("/anzeige/")} />
      </div>
      <main className={s.inhalt}>
        <Seitenschutz pfad={pfad} />
      </main>
    </div>
  );
}

function Marke() {
  const { t } = useTranslation("shell");
  return (
    <Link to="/" className={s.marke} aria-label={t("marke.startseite")}>
      <img src="/icons/app-icon.svg" alt="" width={34} height={34} />
      <b>
        schiesshub<span>.app</span>
      </b>
    </Link>
  );
}

/** Modul zur Adresse: das mit dem längsten passenden Pfad. */
export function modulZuPfad(module: ModulManifest[], pfad: string): ModulManifest | undefined {
  let treffer: ModulManifest | undefined;
  for (const modul of module) {
    const ziel = modul.navigation.pfad;
    if (pfad !== ziel && !pfad.startsWith(`${ziel}/`)) continue;
    if (!treffer || ziel.length > treffer.navigation.pfad.length) treffer = modul;
  }
  return treffer;
}

/** Ohne die Berechtigung des Moduls erscheint statt der Seite ein klarer Hinweis. */
function Seitenschutz({ pfad }: { pfad: string }) {
  const { t } = useTranslation();
  const rechte = useRechte();
  const modul = modulZuPfad(useAlleModule(), pfad);
  if (modul && !darfMit(rechte, modul.berechtigung)) {
    return (
      <div className="panel">
        <Leerzustand
          icon={ShieldAlert}
          titel={t("shell:berechtigung.seite_titel", { titel: t(`${modul.namensraum}:titel`) })}
          text={t("shell:berechtigung.seite_text")}
        >
          <Button component={Link} to="/" variant="default">
            {t("aktion.zur_startseite")}
          </Button>
          <Button component={Link} to="/anmelden" variant="default">
            {t("shell:anmeldung.person_wechseln")}
          </Button>
        </Leerzustand>
      </div>
    );
  }
  return <Outlet />;
}

function Stationsnavigation() {
  const { t } = useTranslation();
  const stationen = useStationen();
  const pfad = useRouterState({ select: (zustand) => zustand.location.pathname });

  return (
    <nav className={s.stationen} aria-label={t("shell:navigation.stationen")}>
      {stationen.map((modul) => {
        const Icon = modul.navigation.icon;
        const ziel = modul.navigation.pfad;
        const aktiv = pfad === ziel || pfad.startsWith(`${ziel}/`);
        return (
          <Link
            key={modul.id}
            to={ziel}
            className={s.station}
            aria-current={aktiv ? "page" : undefined}
          >
            <Icon aria-hidden />
            <span>{t(`${modul.namensraum}:titel`)}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function Statusanzeige() {
  const { t } = useTranslation("shell");
  const { verbindung, health } = useServerStatus();
  const ton = (
    {
      pruefe: "neutral",
      verbunden: "gruen",
      eingeschraenkt: "warn",
      gestoert: "krit",
      getrennt: "krit",
    } as const
  )[verbindung];
  const hinweis = t(`status.hinweis_${verbindung}`, { version: health?.version ?? "?" });

  return (
    <Tooltip label={hinweis} multiline maw={260}>
      <Chip ton={ton} punkt role="status">
        <span className={s.lang}>{t(`status.${verbindung}`)}</span>
        <span className={s.kurz} aria-hidden>
          {t(`status.${verbindung}_kurz`)}
        </span>
      </Chip>
    </Tooltip>
  );
}

/** Sicherungszustand in der Kopfzeile; nur mit `backup.read`. */
function SicherungsChip() {
  const { t, i18n } = useTranslation("shell");
  const { status } = useSicherungsLage(false);
  if (!status) return null;

  const warnung = status.warning;
  const letzte = status.last_snapshot?.ok ? new Date(status.last_snapshot.finished_at) : null;
  const text = warnung
    ? t(`sicherung.chip_${warnung.code}`, { defaultValue: t("sicherung.chip_warnung") })
    : letzte
      ? t("sicherung.chip_ok", { zeit: formatUhrzeit(letzte, i18n.language) })
      : t("sicherung.chip_keine");
  const ton = warnung ? "krit" : letzte ? "gruen" : "neutral";

  return (
    <Tooltip label={warnung?.message_de ?? t("sicherung.chip_hinweis")} multiline maw={280}>
      <Link to="/system/sicherung" className={s.chipLink}>
        <Chip ton={ton} icon={Usb}>
          <span className={s.chipText}>{text}</span>
        </Chip>
      </Link>
    </Tooltip>
  );
}

/** Banner direkt unter der Kopfzeile, wenn die Sicherung eine Warnung meldet. */
function SicherungsBanner({ istAnzeige }: { istAnzeige: boolean }) {
  const { t, i18n } = useTranslation("shell");
  const fehlerText = useFehlerText();
  const { warnung, pruefen, ausblenden } = useSicherungsLage(istAnzeige);
  if (!warnung) return null;
  const seit = new Date(warnung.since);

  return (
    <div className={s.banner} role="alert">
      <TriangleAlert className={s.bannerSymbol} aria-hidden />
      <div className={s.bannerText}>
        <strong>{warnung.message_de}</strong>
        <span className={s.bannerZeile}>
          {t("sicherung.banner_seit")}{" "}
          <span className="num">{formatUhrzeit(seit, i18n.language)}</span>
          {" · "}
          {t("sicherung.banner_hinweis")}
        </span>
        {pruefen.isError && <span className={s.bannerFehler}>{fehlerText(pruefen.error)}</span>}
      </div>
      <div className={s.bannerAktionen}>
        <Button
          variant="default"
          leftSection={<RefreshCw aria-hidden />}
          loading={pruefen.isPending}
          onClick={() => pruefen.mutate()}
        >
          {t("sicherung.erneut_pruefen")}
        </Button>
        <Button variant="subtle" color="gray" onClick={ausblenden}>
          {t("sicherung.ausblenden")}
        </Button>
      </div>
    </div>
  );
}

/** Wer angemeldet ist, mit Abmelden und „Person wechseln“; im offenen Betrieb ein Hinweis. */
function AnmeldeAnzeige() {
  const { t } = useTranslation("shell");
  const navigate = useNavigate();
  const { status, lage, abmelden } = useAnmeldung();
  const fehlerText = useFehlerText();
  const [laeuft, setLaeuft] = useState(false);

  if (!status) return null;

  if (lage.ausstehend === "einrichtung") {
    return (
      <Tooltip label={t("anmeldung.einrichtung_hinweis")} multiline maw={260}>
        <Link to="/einrichtung" className={s.chipLink}>
          <Chip ton="warn" icon={KeyRound}>
            <span className={s.chipText}>{t("anmeldung.einrichtung_ausstehend")}</span>
          </Chip>
        </Link>
      </Tooltip>
    );
  }

  if (lage.ausstehend === "koppeln") {
    return (
      <Button
        component={Link}
        to="/pair"
        variant="default"
        leftSection={<MonitorSmartphone aria-hidden />}
      >
        <span className={s.chipText}>{t("anmeldung.koppeln")}</span>
      </Button>
    );
  }

  if (!status.role) {
    return (
      <Button component={Link} to="/anmelden" variant="default" leftSection={<LogIn aria-hidden />}>
        {t("anmeldung.anmelden")}
      </Button>
    );
  }

  const wer = status.user?.name ?? status.device?.name ?? "";
  const abmeldenKlick = async () => {
    setLaeuft(true);
    try {
      await abmelden();
      zeigeMeldung({ ton: "info", titel: t("anmeldung.abgemeldet") });
    } catch (fehler) {
      zeigeMeldung({
        ton: "krit",
        titel: t("anmeldung.abmelden_fehler"),
        text: fehlerText(fehler),
      });
    } finally {
      setLaeuft(false);
    }
  };

  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <button type="button" className={s.person} aria-label={t("anmeldung.menue", { wer })}>
          {status.user ? <UserRound aria-hidden /> : <MonitorSmartphone aria-hidden />}
          <span className={s.personText}>
            <span className={s.personName}>{wer}</span>
            <span className={s.personRolle}> · {status.role.name}</span>
          </span>
          <ChevronDown className={s.personPfeil} aria-hidden />
        </button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>
          {status.user
            ? t("anmeldung.angemeldet_als", { name: status.user.name, rolle: status.role.name })
            : t("anmeldung.geraet_rolle", { name: wer, rolle: status.role.name })}
        </Menu.Label>
        <Menu.Item
          leftSection={<UsersRound aria-hidden />}
          onClick={() => void navigate({ to: "/anmelden" })}
        >
          {status.user ? t("anmeldung.person_wechseln") : t("anmeldung.anmelden")}
        </Menu.Item>
        {status.user && (
          <Menu.Item
            leftSection={<LogOut aria-hidden />}
            disabled={laeuft}
            onClick={() => void abmeldenKlick()}
          >
            {t("anmeldung.abmelden")}
          </Menu.Item>
        )}
      </Menu.Dropdown>
    </Menu>
  );
}

function BreitenUmschalter() {
  const { t } = useTranslation("shell");
  const [breite, setBreite] = useSeitenbreite();
  const beschriftung = breite === "voll" ? t("breite.zu_zentriert") : t("breite.zu_voll");

  return (
    <Tooltip label={beschriftung}>
      <ActionIcon
        variant="default"
        size={40}
        className={s.breitenUmschalter}
        aria-label={beschriftung}
        onClick={() => setBreite(breite === "voll" ? "zentriert" : "voll")}
      >
        {breite === "voll" ? <Minimize2 aria-hidden /> : <Maximize2 aria-hidden />}
      </ActionIcon>
    </Tooltip>
  );
}

function FarbschemaUmschalter() {
  const { t } = useTranslation("shell");
  const { setColorScheme } = useMantineColorScheme();
  const aktuell = useComputedColorScheme("dark");
  const beschriftung = aktuell === "dark" ? t("farbschema.zu_hell") : t("farbschema.zu_dunkel");

  return (
    <Tooltip label={beschriftung}>
      <ActionIcon
        variant="default"
        size={40}
        aria-label={beschriftung}
        onClick={() => setColorScheme(aktuell === "dark" ? "light" : "dark")}
      >
        {aktuell === "dark" ? <Sun aria-hidden /> : <Moon aria-hidden />}
      </ActionIcon>
    </Tooltip>
  );
}

function Uhr() {
  const { i18n } = useTranslation();
  const [jetzt, setJetzt] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setJetzt(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <time className={`${s.uhr} num`} dateTime={jetzt.toISOString().slice(0, 16)}>
      {formatUhrzeit(jetzt, i18n.language)}
    </time>
  );
}
