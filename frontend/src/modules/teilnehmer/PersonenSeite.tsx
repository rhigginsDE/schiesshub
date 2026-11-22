import { Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { MousePointerClick } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiFehler } from "../../api/client";
import { Bestaetigung } from "../../components/Bestaetigung";
import { PersonenSuche } from "../../components/PersonenSuche";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { type Person, personAbfrage, vereineAbfrage } from "./api";
import { Kopf } from "./Kopf";
import { PersonFormular } from "./PersonFormular";
import type { PersonenAdresse } from "./pfade";
import s from "./teilnehmer.module.css";

interface PersonenSeiteProps {
  adresse: PersonenAdresse;
  /** Schreibt die Auswahl in die Adresse. */
  onAdresse: (adresse: PersonenAdresse) => void;
}

function gleich(a: PersonenAdresse, b: PersonenAdresse): boolean {
  return (a.person ?? null) === (b.person ?? null) && Boolean(a.neu) === Boolean(b.neu);
}

/** Personen als Fenster-Layout: links Suche und Treffer, rechts die gewählte Person. */
export function PersonenSeite({ adresse, onAdresse }: PersonenSeiteProps) {
  const { t } = useTranslation("teilnehmer");
  const [vorschlag, setVorschlag] = useState({ name: "", nr: 0 });
  const [meldung, setMeldung] = useState<string | null>(null);
  const ungespeichert = useRef(false);
  const [ausstehend, setAusstehend] = useState<(() => void) | null>(null);
  const detailOffen = Boolean(adresse.person || adresse.neu);
  // Vereine früh laden, damit die Vereinsauswahl sofort Treffer hat.
  useQuery(vereineAbfrage());

  // Wird gerade gespeichert, ist nichts „ungespeichert“: Der Wechsel wartet dann ohne Rückfrage, bis
  // der Server geantwortet hat. Scheitert das Speichern, kommt die Rückfrage doch noch.
  const speichert = useRef(false);
  const nachSpeichern = useRef<(() => void) | null>(null);

  const merkeUngespeichert = useCallback((wert: boolean) => {
    ungespeichert.current = wert;
  }, []);

  const merkeSpeichert = useCallback((laeuft: boolean) => {
    speichert.current = laeuft;
    if (laeuft || !nachSpeichern.current) return;
    const aktion = nachSpeichern.current;
    nachSpeichern.current = null;
    if (ungespeichert.current) setAusstehend(() => aktion);
    else aktion();
  }, []);

  /** Wechselt die Ansicht; mit ungespeicherten Eingaben erst nach Rückfrage. */
  const gehe = useCallback(
    (ziel: PersonenAdresse, vorher?: () => void) => {
      const ausfuehren = () => {
        vorher?.();
        setMeldung(null);
        onAdresse(ziel);
      };
      if (ungespeichert.current && !(gleich(ziel, adresse) && !vorher)) {
        if (speichert.current) nachSpeichern.current = ausfuehren;
        else setAusstehend(() => ausfuehren);
      } else {
        ausfuehren();
      }
    },
    [adresse, onAdresse],
  );

  const schliessen = useCallback(() => gehe({}), [gehe]);

  // Esc schließt die Detailansicht – nicht aus Eingabefeldern heraus, damit nichts verloren geht.
  useEffect(() => {
    if (!detailOffen) return;
    const beiTaste = (ereignis: KeyboardEvent) => {
      if (ereignis.key !== "Escape" || ereignis.defaultPrevented) return;
      const ziel = ereignis.target as HTMLElement | null;
      if (ziel?.closest("input, textarea, select, [role=dialog], [role=listbox]")) return;
      if (document.querySelector("[role=dialog]")) return;
      schliessen();
    };
    window.addEventListener("keydown", beiTaste);
    return () => window.removeEventListener("keydown", beiTaste);
  }, [detailOffen, schliessen]);

  const auswahl = useCallback((person: Person) => gehe({ person: person.id }), [gehe]);

  const formularProps = {
    onSchliessen: schliessen,
    onUngespeichert: merkeUngespeichert,
    onSpeichert: merkeSpeichert,
    onOeffnen: (id: string) => gehe({ person: id }),
    onGeloescht: () => {
      ungespeichert.current = false;
      onAdresse({});
    },
    onAngelegt: (person: Person) => {
      ungespeichert.current = false;
      // Während des Speicherns wurde schon etwas anderes gewählt: dorthin statt zur neuen Person.
      const aktion = nachSpeichern.current;
      nachSpeichern.current = null;
      if (aktion) {
        aktion();
        return;
      }
      setMeldung(t("formular.angelegt"));
      onAdresse({ person: person.id });
    },
  };

  return (
    <div className={s.seite} data-layout="fenster" data-detail={detailOffen ? "offen" : "zu"}>
      <Kopf aktiv="personen" />
      <div className={s.spalten}>
        <section className={`panel ${s.listenSpalte}`} aria-label={t("reiter.personen")}>
          <PersonenSuche
            aktivId={adresse.person}
            onAuswahl={auswahl}
            onNeu={(name) =>
              gehe({ neu: true }, () => setVorschlag((alt) => ({ name, nr: alt.nr + 1 })))
            }
            onEsc={detailOffen ? schliessen : undefined}
            primaerNeu={!detailOffen}
          />
        </section>

        <div className={s.detailSpalte}>
          {adresse.neu ? (
            <PersonFormular
              key={`neu-${vorschlag.nr}`}
              vorschlag={vorschlag.name}
              {...formularProps}
            />
          ) : adresse.person ? (
            <PersonDetail
              key={adresse.person}
              id={adresse.person}
              meldung={meldung}
              {...formularProps}
            />
          ) : (
            <div className="panel">
              <Leerzustand
                icon={MousePointerClick}
                titel={t("auswahl.titel")}
                text={t("auswahl.text")}
              />
            </div>
          )}
        </div>
      </div>

      <Bestaetigung
        offen={ausstehend !== null}
        titel={t("verwerfen.titel")}
        text={t("verwerfen.text")}
        bestaetigen={t("verwerfen.bestaetigen")}
        abbrechen={t("verwerfen.weiter_bearbeiten")}
        ton="gefahr"
        onBestaetigen={() => {
          const aktion = ausstehend;
          setAusstehend(null);
          ungespeichert.current = false;
          aktion?.();
        }}
        onSchliessen={() => setAusstehend(null)}
      />
    </div>
  );
}

type FormularProps = Omit<
  Parameters<typeof PersonFormular>[0],
  "person" | "vorschlag" | "entfernt"
>;

interface PersonDetailProps extends FormularProps {
  id: string;
}

function PersonDetail({ id, ...formular }: PersonDetailProps) {
  const { t } = useTranslation("teilnehmer");
  const abfrage = useQuery(personAbfrage(id));
  const fehlt = abfrage.error instanceof ApiFehler && abfrage.error.art === "nicht_gefunden";

  // Daten vorhanden: Formular zeigen, auch wenn ein Neuladen danach scheitert (Eingaben bleiben).
  if (abfrage.data) {
    return <PersonFormular person={abfrage.data} entfernt={fehlt} {...formular} />;
  }
  return (
    <article className={`panel ${s.detailPanel}`}>
      <button type="button" className={s.zurueck} onClick={formular.onSchliessen}>
        {t("formular.zurueck")}
      </button>
      {abfrage.isPending ? (
        <div className={s.skelett} aria-busy="true">
          <Skeleton height={34} width="60%" radius="sm" />
          <Skeleton height={60} radius="md" />
          <Skeleton height={60} radius="md" />
          <Skeleton height={120} radius="md" />
        </div>
      ) : (
        <Fehlerzustand
          fehler={abfrage.error}
          onErneut={() => void abfrage.refetch()}
          eigene={{
            nicht_gefunden: {
              titel: t("formular.nicht_gefunden_titel"),
              text: t("formular.nicht_gefunden_text"),
            },
          }}
        />
      )}
    </article>
  );
}
