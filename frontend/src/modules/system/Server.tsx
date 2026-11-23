import { Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { healthAbfrage } from "../../api/abfragen";
import { useAnmeldung } from "../../app/anmeldung";
import { Fehlerzustand } from "../../components/Zustand";
import { formatZahl } from "../../lib/format";
import { formatZeitpunkt } from "./format";
import { PruefungBereich } from "./Pruefung";
import s from "./system.module.css";

export function ServerBereich() {
  const { t, i18n } = useTranslation("system");
  const health = useQuery({ ...healthAbfrage(), refetchInterval: false });
  const { status } = useAnmeldung();
  const sprache = i18n.language;
  const zahl = (wert: number) => formatZahl(wert, {}, sprache);

  return (
    <>
      <section className="panel" aria-labelledby="server-titel">
        <h2 className="h-section" id="server-titel">
          {t("server.titel")}
        </h2>
        {health.isPending ? (
          <Skeleton height={220} radius="md" />
        ) : health.isError ? (
          <Fehlerzustand fehler={health.error} onErneut={() => void health.refetch()} />
        ) : (
          <dl className={`inset ${s.zeilen}`}>
            <div>
              <dt>{t("server.version")}</dt>
              <dd className="num">{health.data.version}</dd>
            </div>
            <div>
              <dt>{t("server.datenbank")}</dt>
              <dd className={health.data.db === "ok" ? s.gut : s.schlecht}>
                {health.data.db === "ok" ? t("server.datenbank_ok") : t("server.datenbank_fehler")}
              </dd>
            </div>
            <div>
              <dt>{t("server.katalog")}</dt>
              <dd className="num">
                {health.data.katalog
                  ? t("server.katalog_umfang", {
                      verbaende: zahl(health.data.katalog.verbaende),
                      gruppen: zahl(health.data.katalog.gruppen),
                      disziplinen: zahl(health.data.katalog.disziplinen),
                      klassen: zahl(health.data.katalog.klassen),
                    })
                  : t("server.katalog_fehlt")}
              </dd>
            </div>
            {health.data.katalog && (
              <div>
                <dt>{t("server.katalog_eingelesen")}</dt>
                <dd className={health.data.katalog.fehler.length > 0 ? s.schlecht : undefined}>
                  {t("server.katalog_eingelesen_wert", {
                    zeit: health.data.katalog.importiert_am
                      ? formatZeitpunkt(health.data.katalog.importiert_am, sprache)
                      : "–",
                    zustand:
                      health.data.katalog.fehler.length > 0
                        ? t("server.katalog_fehler", {
                            count: health.data.katalog.fehler.length,
                            anzahl: zahl(health.data.katalog.fehler.length),
                          })
                        : t("server.katalog_ohne_fehler"),
                  })}
                </dd>
              </div>
            )}
            {status && (
              <div>
                <dt>{t("server.geraet")}</dt>
                <dd>{status.device?.name ?? t("server.geraet_nicht_gekoppelt")}</dd>
              </div>
            )}
          </dl>
        )}
      </section>
      <PruefungBereich />
    </>
  );
}
