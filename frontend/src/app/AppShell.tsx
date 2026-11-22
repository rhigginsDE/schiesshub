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
import { anmeldeSeiteZuPfad, PflichtSeite } from "../modules/auth/routen";
import s from "./AppShell.module.css";
import { AnmeldungProvider, useAnmeldung } from "./anmeldung";
import { darfMit, useRechte } from "./berechtigungen";
import { INHALT_ID, springeZumInhalt, useFokusNachSeitenwechsel } from "./fokusNavigation";
import { useAlleModule, useStationen } from "./modul";
import { useSeitenbreite } from "./seitenbreite";
import { modulZuPfad, useSeitentitel } from "./seitentitel";
import { useServerStatus } from "./serverStatus";
import { bannerAktion, useSicherungsLage, WARNUNG_SCHLUESSEL } from "./sicherungsLage";

/** Ereignisse, auf die die Shell selbst hört: Anmelde-Zustand und Sicherung. */
const SHELL_EREIGNISSE: EreignisZuordnung = {
  [EREIGNIS_VERBUNDEN]: [schluessel.auth.status, schluessel.sicherung.alle],
  "auth.setup": [schluessel.auth.status],
  "device.updated": [schluessel.auth.status],
  "device.deleted": [schluessel.auth.status],
  "role.updated": [schluessel.auth.status],
  "role.deleted": [schluessel.auth.status],
  "user.updated": [schluessel.auth.status],
  "backup.status": [schluessel.sicherung.status, WARNUNG_SCHLUESSEL],
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
  const anmeldeArt = anmeldeSeiteZuPfad(pfad);
  const anmeldeSeite = anmeldeArt !== null;
  useSeitentitel(pfad, anmeldeArt ?? lage.pflicht);
  useFokusNachSeitenwechsel(pfad);

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
        <Sprunglink />
        <header className={s.leiste}>
          <Marke />
          <div className={s.status}>
            <Statusanzeige />
            <FarbschemaUmschalter />
            <Uhr />
          </div>
        </header>
        <main className={s.inhalt} id={INHALT_ID} tabIndex={-1}>
          {anmeldeSeite ? <Outlet /> : lage.pflicht && <PflichtSeite seite={lage.pflicht} />}
        </main>
      </div>
    );
  }

  return (
    <div className={s.rahmen}>
      <Sprunglink />
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
        {/* Nur der Bildschirm (`/anzeige/schirm…`) folgt „auf der Anzeige warnen“; die Verwaltung
            unter `/anzeige` ist eine Station wie jede andere. */}
        <SicherungsBanner istAnzeige={pfad.startsWith("/anzeige/schirm")} />
      </div>
      <main className={s.inhalt} id={INHALT_ID} tabIndex={-1}>
        <Seitenschutz pfad={pfad} />
      </main>
    </div>
  );
}

/** Erstes Fokusziel jeder Seite: springt über Kopfzeile und Hinweise direkt zum Inhalt. */
function Sprunglink() {
  const { t } = useTranslation("shell");
  return (
    <a
      href={`#${INHALT_ID}`}
      className={s.sprunglink}
      onClick={(ereignis) => {
        ereignis.preventDefault();
        springeZumInhalt();
      }}
    >
      {t("sprunglink")}
    </a>
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

export { modulZuPfad } from "./seitentitel";

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
          ueberschrift="h1"
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
      verbunden: "neutral",
      eingeschraenkt: "warn",
      gestoert: "krit",
      getrennt: "krit",
    } as const
  )[verbindung];
  const hinweis = t(`status.hinweis_${verbindung}`, { version: health?.version ?? "?" });

  return (
    <Tooltip label={hinweis} multiline maw={260}>
      <Chip
        ton={ton}
        punkt
        role="status"
        className={[s.statusChip, ton === "neutral" && s.ruhig].filter(Boolean).join(" ")}
        data-verbindung={verbindung}
      >
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
  // Im Normalfall ruhig (gedämpfter Text); Farbe erst bei einer Warnung. Grün gehört der
  // Hauptaktion der Ansicht.
  const ton = warnung ? "krit" : "neutral";

  return (
    <Tooltip label={warnung?.message_de ?? t("sicherung.chip_hinweis")} multiline maw={280}>
      <Link to="/system/sicherung" className={s.chipLink}>
        <Chip ton={ton} icon={Usb} className={warnung ? undefined : s.ruhig}>
          <span className={s.chipText}>{text}</span>
        </Chip>
      </Link>
    </Tooltip>
  );
}

/**
 * Banner direkt unter der Kopfzeile, wenn die Sicherung eine Warnung meldet: was los ist, was zu tun
 * ist, und genau die Aktion, die hilft. „Erneut prüfen“ nur, wo Prüfen etwas ändern kann (Stick).
 */
function SicherungsBanner({ istAnzeige }: { istAnzeige: boolean }) {
  const { t, i18n } = useTranslation("shell");
  const fehlerText = useFehlerText();
  const { warnung, darfVerwalten, pruefen, ausblenden } = useSicherungsLage(istAnzeige);
  if (!warnung) return null;
  const seit = new Date(warnung.since);
  const aktion = bannerAktion(warnung.code);
  // Passwort und Einstellungen kann nur ändern, wer die Sicherung verwalten darf.
  const nurBescheid = aktion !== "pruefen" && !darfVerwalten;
  const wasTun = nurBescheid
    ? t("sicherung.was_tun_ohne_recht")
    : t(`sicherung.was_tun_${warnung.code}`, { defaultValue: t("sicherung.was_tun_unbekannt") });

  return (
    <div className={s.banner} role="alert">
      <TriangleAlert className={s.bannerSymbol} aria-hidden />
      <div className={s.bannerText}>
        <strong className={s.bannerTitel}>{warnung.message_de}</strong>
        <span className={s.bannerWasTun}>
          <b>{t("sicherung.was_tun")}</b> {wasTun}
        </span>
        <span className={s.bannerZeile}>
          {t("sicherung.banner_seit")}{" "}
          <span className="num">{formatUhrzeit(seit, i18n.language)}</span>
        </span>
        {pruefen.isError && <span className={s.bannerFehler}>{fehlerText(pruefen.error)}</span>}
      </div>
      <div className={s.bannerAktionen}>
        {aktion === "pruefen" && (
          <Button
            variant="default"
            leftSection={<RefreshCw aria-hidden />}
            loading={pruefen.isPending}
            onClick={() => pruefen.mutate()}
          >
            {t("sicherung.erneut_pruefen")}
          </Button>
        )}
        {!nurBescheid && aktion !== "pruefen" && (
          <Button
            component={Link}
            to="/system/sicherung"
            variant="default"
            leftSection={aktion === "passwort" ? <KeyRound aria-hidden /> : <Usb aria-hidden />}
          >
            {aktion === "passwort"
              ? t("sicherung.passwort_festlegen")
              : t("sicherung.zur_sicherung")}
          </Button>
        )}
        <Button
          variant="subtle"
          color="gray"
          onClick={ausblenden}
          aria-label={t("sicherung.ausblenden")}
        >
          <span className={s.lang}>{t("sicherung.ausblenden")}</span>
          <span className={s.kurz} aria-hidden>
            {t("sicherung.ausblenden_kurz")}
          </span>
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

  // Offener Betrieb: Koppeln und Einloggen sind freiwillig, deshalb nur ein leiser Textknopf.
  // Ist Einloggen Pflicht, übernimmt ohnehin die Pflichtseite.
  if (lage.ausstehend === "koppeln" || !status.role) {
    const koppeln = lage.ausstehend === "koppeln";
    const text = koppeln ? t("anmeldung.koppeln") : t("anmeldung.anmelden");
    return (
      <Tooltip
        label={koppeln ? t("anmeldung.koppeln_hinweis") : t("anmeldung.anmelden_hinweis")}
        multiline
        maw={280}
      >
        <Button
          component={Link}
          to={koppeln ? "/pair" : "/anmelden"}
          variant="subtle"
          color="gray"
          className={s.leise}
          aria-label={text}
          leftSection={koppeln ? <MonitorSmartphone aria-hidden /> : <LogIn aria-hidden />}
        >
          <span className={s.leiseText}>{text}</span>
        </Button>
      </Tooltip>
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
        size={44}
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
        size={44}
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
