import { ActionIcon, Tooltip, useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { Moon, Sun } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { type EreignisZuordnung, useServerEreignisse } from "../api/ereignisse";
import { Chip } from "../components/Chip";
import { formatUhrzeit } from "../lib/format";
import s from "./AppShell.module.css";
import { useModule, useStationen } from "./modul";
import { useServerStatus } from "./serverStatus";

/** Rahmen jeder Seite: Kopfzeile mit Wortmarke, Stationen, Serverstatus, Farbschema und Uhr. */
export function AppShell() {
  const { t } = useTranslation("shell");
  const module = useModule();

  const ereignisse = useMemo<EreignisZuordnung>(() => {
    const gesamt: Record<string, EreignisZuordnung[string][number][]> = {};
    for (const modul of module) {
      for (const [name, keys] of Object.entries(modul.ereignisse ?? {})) {
        gesamt[name] = [...(gesamt[name] ?? []), ...keys];
      }
    }
    return gesamt;
  }, [module]);
  useServerEreignisse(ereignisse);

  return (
    <div className={s.rahmen}>
      <header className={s.leiste}>
        <Link to="/" className={s.marke} aria-label={t("marke.startseite")}>
          <img src="/icons/app-icon.svg" alt="" width={34} height={34} />
          <b>
            schiesshub<span>.app</span>
          </b>
        </Link>
        <Stationsnavigation />
        <div className={s.status}>
          <Statusanzeige />
          <FarbschemaUmschalter />
          <Uhr />
        </div>
      </header>
      <main className={s.inhalt}>
        <Outlet />
      </main>
    </div>
  );
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
