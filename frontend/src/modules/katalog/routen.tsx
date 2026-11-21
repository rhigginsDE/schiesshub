import { createRoute, useNavigate, useParams } from "@tanstack/react-router";
import { rootRoute } from "../../app/rootRoute";
import { Aushang } from "./Aushang";
import { DisziplinDetail, KeineAuswahl } from "./DisziplinDetail";
import { KatalogSeite } from "./KatalogSeite";
import {
  AUSHANG_PFAD,
  DISZIPLIN_PFAD,
  KATALOG_PFAD,
  type KatalogAuswahl,
  type KatalogSuche,
} from "./pfade";

// Der Router liest `?q=1001` als Zahl; Kennziffern und Suchtexte sind aber immer Text.
function alsText(wert: unknown): string | undefined {
  if (typeof wert === "number") return String(wert);
  return typeof wert === "string" && wert !== "" ? wert : undefined;
}

const katalogRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: KATALOG_PFAD,
  validateSearch: (suche: Record<string, unknown>): KatalogSuche => ({
    verband: alsText(suche.verband),
    gruppe: alsText(suche.gruppe),
    q: alsText(suche.q),
  }),
  component: KatalogRouteSeite,
});

const keineAuswahlRoute = createRoute({
  getParentRoute: () => katalogRoute,
  path: "/",
  component: KeineAuswahl,
});

const disziplinRoute = createRoute({
  getParentRoute: () => katalogRoute,
  path: "$verband/$kennziffer",
  component: DisziplinRouteSeite,
});

/** Druckansicht ohne Katalogliste; eigene Route, damit nur das Blatt erscheint. */
const aushangRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: AUSHANG_PFAD,
  validateSearch: (suche: Record<string, unknown>): { variante?: string } => ({
    variante: alsText(suche.variante),
  }),
  component: AushangRouteSeite,
});

function AushangRouteSeite() {
  const { verband, kennziffer } = aushangRoute.useParams();
  const { variante } = aushangRoute.useSearch();
  const navigate = useNavigate();
  return (
    <Aushang
      verband={verband}
      kennziffer={kennziffer}
      variante={variante}
      onVarianteAendern={(neu) =>
        void navigate({
          to: AUSHANG_PFAD,
          params: { verband, kennziffer },
          search: { variante: neu },
          replace: true,
        })
      }
    />
  );
}

function KatalogRouteSeite() {
  const suche = katalogRoute.useSearch();
  const navigate = useNavigate();
  const { verband, kennziffer } = useParams({ strict: false }) as Partial<KatalogAuswahl>;
  const auswahl = verband && kennziffer ? { verband, kennziffer } : null;

  const sucheAendern = (neu: KatalogSuche, auswahlBehalten = true) => {
    if (auswahl && auswahlBehalten) {
      void navigate({ to: DISZIPLIN_PFAD, params: auswahl, search: neu, replace: true });
    } else {
      void navigate({ to: KATALOG_PFAD, search: neu, replace: true });
    }
  };

  return <KatalogSeite suche={suche} auswahl={auswahl} onSucheAendern={sucheAendern} />;
}

function DisziplinRouteSeite() {
  const { verband, kennziffer } = disziplinRoute.useParams();
  const suche = katalogRoute.useSearch();
  return <DisziplinDetail verband={verband} kennziffer={kennziffer} suche={suche} />;
}

export const katalogRouten = [
  katalogRoute.addChildren([keineAuswahlRoute, disziplinRoute]),
  aushangRoute,
];
