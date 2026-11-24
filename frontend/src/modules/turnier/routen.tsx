import { createRoute, Link, useNavigate } from "@tanstack/react-router";
import { Trash2, Trophy } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { rootRoute } from "../../app/rootRoute";
import { Leerzustand } from "../../components/Zustand";
import { DRUCK_PFAD } from "./ausschreibung/Ausschreibung";
import { DruckSeite } from "./ausschreibung/DruckSeite";
import { EinrichtenSeite } from "./EinrichtenSeite";
import { useTurnierGeloescht } from "./geloescht";
import { EINRICHTEN_PFAD, type EinrichtenSuche, TURNIER_ID, TURNIER_PFAD } from "./pfade";
import { TurnierSeite } from "./TurnierSeite";
import s from "./turnier.module.css";
import { istBereich } from "./vollstaendigkeit";

const listeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: TURNIER_PFAD,
  component: () => <TurnierSeite station={TURNIER_ID} icon={Trophy} />,
});

const einrichtenRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: EINRICHTEN_PFAD,
  validateSearch: (suche: Record<string, unknown>): EinrichtenSuche => ({
    bereich: istBereich(suche.bereich) ? suche.bereich : undefined,
    wettbewerb: typeof suche.wettbewerb === "string" ? suche.wettbewerb : undefined,
  }),
  component: EinrichtenRouteSeite,
});

/**
 * Wurde das Turnier gelöscht (hier oder auf einem anderen Gerät), hängen sich seine Seiten ab und
 * fragen nichts mehr ab; stattdessen ein ruhiger Hinweis mit dem Weg zur Liste.
 */
function NichtGeloescht({ turnierId, children }: { turnierId: string; children: ReactNode }) {
  const { t } = useTranslation("turnier");
  if (!useTurnierGeloescht(turnierId)) return children;
  return (
    <div className="panel">
      <Leerzustand
        icon={Trash2}
        titel={t("einrichten.geloescht_titel")}
        text={t("einrichten.geloescht_text")}
      >
        <Link to={TURNIER_PFAD} className={s.textLink}>
          {t("einrichten.zur_liste")}
        </Link>
      </Leerzustand>
    </div>
  );
}

function EinrichtenRouteSeite() {
  const { turnierId } = einrichtenRoute.useParams();
  return (
    <NichtGeloescht turnierId={turnierId}>
      <EinrichtenRouteInhalt turnierId={turnierId} />
    </NichtGeloescht>
  );
}

function EinrichtenRouteInhalt({ turnierId }: { turnierId: string }) {
  const suche = einrichtenRoute.useSearch();
  const navigate = useNavigate();
  return (
    <EinrichtenSeite
      turnierId={turnierId}
      suche={suche}
      onSuche={(neu) =>
        void navigate({
          to: EINRICHTEN_PFAD,
          params: { turnierId },
          search: neu,
          replace: true,
        })
      }
    />
  );
}

const druckRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: DRUCK_PFAD,
  component: function DruckRouteSeite() {
    const { turnierId } = druckRoute.useParams();
    return (
      <NichtGeloescht turnierId={turnierId}>
        <DruckSeite turnierId={turnierId} />
      </NichtGeloescht>
    );
  },
});

export const turnierRouten = [listeRoute, einrichtenRoute, druckRoute];
