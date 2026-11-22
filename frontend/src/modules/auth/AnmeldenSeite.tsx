import { Button, Skeleton } from "@mantine/core";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { ArrowLeft, Lock, MonitorSmartphone, UserX } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { anmeldePersonenAbfrage } from "../../api/abfragen";
import { ApiFehler, apiSenden } from "../../api/client";
import type { AuthPerson, AuthStatus } from "../../api/typenSystem";
import { useAnmeldung } from "../../app/anmeldung";
import { FehlerHinweis } from "../../components/FehlerHinweis";
import { zeigeMeldung } from "../../components/Meldungen";
import { Ziffernfeld } from "../../components/Ziffernfeld";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import s from "./auth.module.css";
import { formatRestzeit, initialen, PIN_MAX_LAENGE } from "./eingaben";

/** Personenauswahl mit großen Kacheln, danach PIN über das Ziffernfeld. */
export function AnmeldenSeite() {
  const { t } = useTranslation("auth");
  const { status, lage } = useAnmeldung();
  const navigate = useNavigate();
  const pfad = useRouterState({ select: (zustand) => zustand.location.pathname });
  // Ohne Kopplung antwortet der Server mit 401; dann gar nicht erst fragen.
  const gekoppelt = status ? Boolean(status.device) : true;
  const personen = useQuery({ ...anmeldePersonenAbfrage(), enabled: gekoppelt });
  const [auswahl, setAuswahl] = useState<AuthPerson | null>(null);

  const einrichtungFehlt = Boolean(status?.setup_required) && !gekoppelt;
  const nichtGekoppelt =
    !einrichtungFehlt &&
    (!gekoppelt ||
      (personen.error instanceof ApiFehler && personen.error.art === "nicht_angemeldet"));
  const geraetRolle = !status?.user && status?.role ? status.role.name : null;
  // Im offenen Betrieb (Einloggen nicht Pflicht) gibt es immer einen Weg zurück.
  const offen = !lage.sperren;

  if (nichtGekoppelt) {
    return (
      <section className={`panel ${s.karte}`} aria-labelledby="anmelden-titel">
        <header className={s.kopf}>
          <span className={s.symbol}>
            <MonitorSmartphone aria-hidden />
          </span>
          <h1 className="h-display" id="anmelden-titel">
            {t("anmelden.nicht_gekoppelt_titel")}
          </h1>
          <p className="gedaempft">{t("anmelden.nicht_gekoppelt_text")}</p>
        </header>
        <Button component={Link} to="/pair" size="lg">
          {t("koppeln.titel")}
        </Button>
        {offen && (
          <div className={s.auswege}>
            <p className={s.offenHinweis}>{t("anmelden.nicht_gekoppelt_offen")}</p>
            <Button
              component={Link}
              to="/"
              variant="default"
              leftSection={<ArrowLeft aria-hidden />}
            >
              {t("allgemein:aktion.zur_startseite")}
            </Button>
          </div>
        )}
      </section>
    );
  }

  return (
    <section className={`panel ${s.karte} ${s.breit}`} aria-labelledby="anmelden-titel">
      <header className={s.kopf}>
        <h1 className="h-display" id="anmelden-titel">
          {auswahl ? t("anmelden.als", { name: auswahl.name }) : t("anmelden.titel")}
        </h1>
        {!auswahl && (
          <p className="gedaempft">
            {t("anmelden.einleitung")}
            {status?.device && (
              <>
                {" "}
                <span>{t("anmelden.geraet", { name: status.device.name })}</span>
              </>
            )}
          </p>
        )}
      </header>

      {auswahl ? (
        <PinSchritt
          person={auswahl}
          onZurueck={() => setAuswahl(null)}
          onFertig={() => {
            if (pfad === "/anmelden") void navigate({ to: "/" });
          }}
        />
      ) : einrichtungFehlt || (personen.isSuccess && personen.data.length === 0) ? (
        <Leerzustand icon={UserX} titel={t("anmelden.leer_titel")} text={t("anmelden.leer_text")}>
          {status?.setup_required && (
            <Button component={Link} to="/einrichtung">
              {t("einrichtung.titel")}
            </Button>
          )}
        </Leerzustand>
      ) : personen.isPending ? (
        <div className={s.personen} aria-busy="true">
          {[0, 1, 2, 3].map((nr) => (
            <Skeleton key={nr} height={112} radius="lg" />
          ))}
        </div>
      ) : personen.isError ? (
        <Fehlerzustand fehler={personen.error} onErneut={() => void personen.refetch()} />
      ) : (
        <ul className={s.personen}>
          {personen.data.map((person) => (
            <li key={person.id}>
              <button type="button" className={s.person} onClick={() => setAuswahl(person)}>
                <span className={s.initialen} aria-hidden>
                  {initialen(person.name)}
                </span>
                <span className={s.personName}>{person.name}</span>
                {status?.user?.id === person.id && (
                  <span className={s.aktuell}>{t("anmelden.aktuell")}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Mit Geräterolle geht es auch ohne Einloggen weiter (wenn es nicht Pflicht ist);
          im offenen Betrieb sonst zurück zur Startseite. */}
      {(geraetRolle ? !lage.pflicht : offen) && !auswahl && (
        <Button
          variant="default"
          component={Link}
          to="/"
          className={s.ohne}
          leftSection={geraetRolle ? undefined : <ArrowLeft aria-hidden />}
        >
          {geraetRolle
            ? t("anmelden.ohne_anmeldung", { rolle: geraetRolle })
            : t("allgemein:aktion.zur_startseite")}
        </Button>
      )}
    </section>
  );
}

interface PinSchrittProps {
  person: AuthPerson;
  onZurueck: () => void;
  onFertig: () => void;
}

function PinSchritt({ person, onZurueck, onFertig }: PinSchrittProps) {
  const { t } = useTranslation("auth");
  const { uebernehmen } = useAnmeldung();
  const [pin, setPin] = useState("");
  const [gesperrtBis, setGesperrtBis] = useState<number | null>(null);
  const [jetzt, setJetzt] = useState(() => Date.now());

  const anmelden = useMutation({
    mutationFn: () =>
      apiSenden<AuthStatus>("POST", "/auth/login", { user_id: person.id, pin }, { still: true }),
    onSuccess: (neu) => {
      uebernehmen(neu);
      zeigeMeldung({ ton: "erfolg", titel: t("anmelden.willkommen", { name: person.name }) });
      onFertig();
    },
    onError: (fehler) => {
      setPin("");
      if (fehler instanceof ApiFehler && fehler.art === "gesperrt") {
        setGesperrtBis(
          fehler.wiederholenNachSekunden
            ? Date.now() + fehler.wiederholenNachSekunden * 1000
            : null,
        );
        setJetzt(Date.now());
      }
    },
  });

  const rest = gesperrtBis ? Math.ceil((gesperrtBis - jetzt) / 1000) : 0;
  useEffect(() => {
    if (!gesperrtBis) return;
    const timer = setInterval(() => {
      const neu = Date.now();
      setJetzt(neu);
      if (neu >= gesperrtBis) {
        setGesperrtBis(null);
        anmelden.reset();
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [gesperrtBis, anmelden]);

  const fehler = anmelden.error;
  const istGesperrt = fehler instanceof ApiFehler && fehler.art === "gesperrt";
  const gesperrtAktiv = istGesperrt && (gesperrtBis === null || rest > 0);

  return (
    <div className={s.pinSchritt}>
      <Ziffernfeld
        id="anmelden-pin"
        wert={pin}
        onChange={(neu) => {
          setPin(neu);
          if (anmelden.isError && !istGesperrt) anmelden.reset();
        }}
        onFertig={() => {
          if (pin && !anmelden.isPending) anmelden.mutate();
        }}
        fertigText={t("anmelden.absenden")}
        maxLaenge={PIN_MAX_LAENGE}
        deaktiviert={anmelden.isPending || gesperrtAktiv}
        beschriftung={t("anmelden.pin", { name: person.name })}
        beschreibungId={fehler ? "anmelden-fehler" : undefined}
      />
      <div id="anmelden-fehler" className={s.pinMeldung}>
        {istGesperrt ? (
          <p className={s.sperre} role="alert">
            <Lock aria-hidden />
            <span>
              {gesperrtBis
                ? t("anmelden.gesperrt", {
                    zeit: t("anmelden.minuten", { zeit: formatRestzeit(rest) }),
                  })
                : t("anmelden.gesperrt_ohne_zeit")}
            </span>
          </p>
        ) : fehler instanceof ApiFehler && fehler.art === "nicht_angemeldet" ? (
          <FehlerHinweis fehler={fehler} text={t("anmelden.pin_falsch")} />
        ) : (
          <FehlerHinweis fehler={fehler} />
        )}
      </div>
      <Button variant="subtle" leftSection={<ArrowLeft aria-hidden />} onClick={onZurueck}>
        {t("anmelden.andere_person")}
      </Button>
    </div>
  );
}
