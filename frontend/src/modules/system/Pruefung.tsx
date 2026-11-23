import { Button, Skeleton } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Circle, CircleCheck, LockKeyhole } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { schluessel } from "../../api/abfragen";
import { ApiFehler, apiGet, apiSenden } from "../../api/client";
import { useAnmeldung } from "../../app/anmeldung";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { useFehlerText } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { Fehlerzustand } from "../../components/Zustand";
import {
  type AufgabeId,
  type PruefungsLage,
  pruefungsAufgaben,
  unbekannteHindernisse,
} from "./pruefungsLage";
import s from "./system.module.css";

/** Präfix für Ereignisse; die Abfrage hängt zusätzlich an Gerät und Benutzer dieses Browsers. */
export const PRUEFUNG_SCHLUESSEL = ["auth", "enforcement"] as const;

/** Wohin ein offener Schritt führt. */
const WEG: Record<AufgabeId, string> = {
  admin: "/system/personen",
  geraet: "/system/geraete",
  eingeloggt: "/anmelden",
};

/**
 * Koppeln und PIN verlangen (`AUTH_ENFORCED` bzw. der Schalter in der App). Einschalten geht hier,
 * ausschalten nur auf dem Server. Der Server lässt nur einschalten, wer an einem gekoppelten Gerät
 * als Administrator eingeloggt ist; dieses Gerät sperrt sich dabei also nicht aus.
 */
export function PruefungBereich() {
  const { t } = useTranslation("system");
  const queryClient = useQueryClient();
  const fehlerText = useFehlerText();
  const { status } = useAnmeldung();
  const [rueckfrage, setRueckfrage] = useState(false);

  const schluesselHier = [
    ...PRUEFUNG_SCHLUESSEL,
    status?.device?.id ?? null,
    status?.user?.id ?? null,
  ] as const;
  const lage = useQuery({
    queryKey: schluesselHier,
    queryFn: ({ signal }) => apiGet<PruefungsLage>("/auth/enforcement", { signal }),
    staleTime: 0,
  });

  const einschalten = useMutation({
    mutationFn: () => apiSenden<PruefungsLage>("POST", "/auth/enforcement/enable"),
    onSuccess: (neu) => {
      setRueckfrage(false);
      queryClient.setQueryData(schluesselHier, neu);
      void queryClient.invalidateQueries({ queryKey: schluessel.auth.status });
      zeigeMeldung({ ton: "erfolg", titel: t("pin_pflicht.eingeschaltet") });
    },
    onError: (fehler) => {
      // Voraussetzungen haben sich geändert: Liste neu laden, der Dialog nennt den Grund.
      if (fehler instanceof ApiFehler && fehler.code === "enforcement_blocked") {
        void queryClient.invalidateQueries({ queryKey: PRUEFUNG_SCHLUESSEL });
      }
    },
  });

  const schliessen = () => {
    setRueckfrage(false);
    einschalten.reset();
  };

  return (
    <section className="panel" aria-labelledby="pin-pflicht-titel">
      <div className={s.kopf}>
        <h2 className="h-section" id="pin-pflicht-titel">
          {t("pin_pflicht.titel")}
        </h2>
        {lage.data && (
          <Chip ton={lage.data.enforced ? "gruen" : "neutral"} punkt>
            {lage.data.enforced ? t("pin_pflicht.an") : t("pin_pflicht.aus")}
          </Chip>
        )}
      </div>
      {lage.isPending ? (
        <Skeleton height={160} radius="md" />
      ) : lage.isError ? (
        <Fehlerzustand fehler={lage.error} onErneut={() => void lage.refetch()} />
      ) : lage.data.enforced ? (
        <Eingeschaltet quelle={lage.data.source} />
      ) : (
        <>
          <p className={s.einleitung}>{t("pin_pflicht.erklaerung")}</p>
          <Voraussetzungen lage={lage.data} />
          {lage.data.can_enable && (
            <div className={s.aktionen}>
              <Button leftSection={<LockKeyhole aria-hidden />} onClick={() => setRueckfrage(true)}>
                {t("pin_pflicht.einschalten")}
              </Button>
            </div>
          )}
        </>
      )}
      <Bestaetigung
        offen={rueckfrage}
        titel={t("pin_pflicht.rueckfrage_titel")}
        text={
          <>
            <p>{t("pin_pflicht.rueckfrage_alle")}</p>
            <p>
              {t("pin_pflicht.rueckfrage_dieses", {
                geraet: status?.device?.name ?? "",
                name: status?.user?.name ?? "",
              })}
            </p>
            <p>
              <strong>{t("pin_pflicht.rueckfrage_aus")}</strong>
            </p>
          </>
        }
        bestaetigen={t("pin_pflicht.einschalten_ok")}
        abbrechen={t("allgemein.abbrechen")}
        laedt={einschalten.isPending}
        fehler={einschalten.isError ? fehlerText(einschalten.error) : undefined}
        onSchliessen={schliessen}
        onBestaetigen={() => einschalten.mutate()}
      />
    </section>
  );
}

function Eingeschaltet({ quelle }: { quelle: PruefungsLage["source"] }) {
  const { t } = useTranslation("system");
  return (
    <>
      <p className={s.einleitung}>{t("pin_pflicht.an_text")}</p>
      <p className={s.einleitung}>
        {quelle === "env" ? t("pin_pflicht.aus_nur_server_fest") : t("pin_pflicht.aus_nur_server")}
      </p>
      <details className={s.pruefErgebnis}>
        <summary>{t("pin_pflicht.betreuer")}</summary>
        <p className={s.hinweis}>
          {quelle === "env" ? t("pin_pflicht.betreuer_env") : t("pin_pflicht.betreuer_konsole")}
        </p>
      </details>
    </>
  );
}

function Voraussetzungen({ lage }: { lage: PruefungsLage }) {
  const { t } = useTranslation("system");
  const aufgaben = pruefungsAufgaben(lage.blockers);
  const unbekannt = unbekannteHindernisse(lage.blockers);
  const erledigt = aufgaben.filter((aufgabe) => aufgabe.erledigt).length;
  const naechste = aufgaben.find((aufgabe) => !aufgabe.erledigt)?.id;
  return (
    <div className={`inset ${s.aufgaben}`}>
      <div className={s.aufgabenKopf}>
        <h3 className={s.aufgabenTitel}>{t("pin_pflicht.vorher")}</h3>
        <span className="gedaempft num">
          {t("pin_pflicht.fortschritt", { erledigt, gesamt: aufgaben.length })}
        </span>
      </div>
      <ol className={s.aufgabenListe}>
        {aufgaben.map((aufgabe) => {
          const aktiv = aufgabe.id === naechste;
          return (
            <li
              key={aufgabe.id}
              className={s.aufgabe}
              data-zustand={aufgabe.erledigt ? "erledigt" : aktiv ? "aktiv" : "offen"}
              aria-current={aktiv ? "step" : undefined}
            >
              {aufgabe.erledigt ? (
                <CircleCheck className={s.aufgabeSymbol} aria-hidden />
              ) : (
                <Circle className={s.aufgabeSymbol} aria-hidden />
              )}
              <span className={s.aufgabeText}>
                <strong>{t(`pin_pflicht.schritt.${aufgabe.id}`)}</strong>
                {aufgabe.code && (
                  <span>
                    {t(`pin_pflicht.grund.${aufgabe.code}`)}{" "}
                    <Link to={WEG[aufgabe.id]}>{t(`pin_pflicht.weg.${aufgabe.id}`)}</Link>
                  </span>
                )}
              </span>
              <span className={s.aufgabeZustand}>
                {aufgabe.erledigt ? t("pin_pflicht.erledigt") : t("pin_pflicht.offen")}
              </span>
            </li>
          );
        })}
        {unbekannt.map((hindernis) => (
          <li key={hindernis.code} className={s.aufgabe} data-zustand="offen">
            <Circle className={s.aufgabeSymbol} aria-hidden />
            <span className={s.aufgabeText}>
              <strong>{hindernis.message_de}</strong>
            </span>
            <span className={s.aufgabeZustand}>{t("pin_pflicht.offen")}</span>
          </li>
        ))}
      </ol>
      {lage.can_enable && <p className={s.hinweis}>{t("pin_pflicht.bereit")}</p>}
    </div>
  );
}
