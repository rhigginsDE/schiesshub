import { Link, Navigate, Outlet, useRouterState } from "@tanstack/react-router";
import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { darfMit, useRechte } from "../../app/berechtigungen";
import { Leerzustand } from "../../components/Zustand";
import { BEREICHE, bereichZuPfad } from "./bereiche";
import s from "./system.module.css";

/** Station System: Bereichsnavigation links, Inhalt rechts (Fenster-Layout). */
export function SystemSeite() {
  const { t } = useTranslation("system");
  const rechte = useRechte();
  const pfad = useRouterState({ select: (zustand) => zustand.location.pathname });
  const aktiv = bereichZuPfad(pfad);
  const erlaubt = BEREICHE.filter((bereich) => darfMit(rechte, bereich.berechtigung));

  return (
    <div className={s.seite} data-layout="fenster">
      <div className={s.spalten}>
        <nav className={`panel ${s.navigation}`} aria-label={t("navigation.beschriftung")}>
          <h1 className={`h-section ${s.titel}`}>{t("titel")}</h1>
          <ul className={s.bereiche}>
            {erlaubt.map((bereich) => {
              const Icon = bereich.icon;
              return (
                <li key={bereich.id}>
                  <Link
                    to={bereich.pfad}
                    className={s.bereich}
                    aria-current={aktiv?.id === bereich.id ? "page" : undefined}
                  >
                    <Icon aria-hidden />
                    <span className={s.bereichText}>
                      <strong>{t(`navigation.${bereich.id}`)}</strong>
                      <span>{t(`navigation.${bereich.id}_text`)}</span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className={s.inhalt}>
          {!aktiv ? (
            erlaubt[0] ? (
              <Navigate to={erlaubt[0].pfad} replace />
            ) : (
              <div className="panel">
                <Leerzustand
                  icon={ShieldAlert}
                  titel={t("kein_bereich.titel")}
                  text={t("kein_bereich.text")}
                />
              </div>
            )
          ) : darfMit(rechte, aktiv.berechtigung) ? (
            <Outlet />
          ) : (
            <div className="panel">
              <Leerzustand
                icon={ShieldAlert}
                titel={t("shell:berechtigung.seite_titel", {
                  titel: t(`navigation.${aktiv.id}`),
                })}
                text={t("shell:berechtigung.seite_text")}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
