import { Button, NativeSelect, Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Check, CircleAlert, CircleDashed, CircleDot, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../app/berechtigungen";
import { Fehlerzustand } from "../../components/Zustand";
import { uebersichtAbfrage } from "./abfragen";
import a from "./aufgaben.module.css";
import { Ausschreibung } from "./ausschreibung/Ausschreibung";
import { ausschreibungAbfrage } from "./ausschreibung/abfragen";
import { Einstellungen } from "./bereiche/Einstellungen";
import { Klassen } from "./bereiche/Klassen";
import { Staende } from "./bereiche/Staende";
import { Stammdaten } from "./bereiche/Stammdaten";
import { Zusammenfassung } from "./bereiche/Zusammenfassung";
import { EntwurfSchutz, useUngespeichert } from "./EntwurfSchutz";
import { KopieHinweis } from "./KopieHinweis";
import { zeitraum } from "./klartext";
import { type EinrichtenSuche, TURNIER_PFAD } from "./pfade";
import { StatusAktionen, StatusChip } from "./Status";
import { TurnierAnlegen } from "./TurnierAnlegen";
import s from "./turnier.module.css";
import { UebungBanner, UebungChip } from "./Uebung";
import { EntwurfKontext, EntwurfRegister } from "./useEntwurf";
import {
  BEREICHE,
  type Bereich,
  ersterOffenerSchritt,
  offenePunkte,
  type SchrittZustand,
  schrittZustaende,
} from "./vollstaendigkeit";
import v from "./vorlagen.module.css";
import { Wettbewerbe } from "./wettbewerbe/Wettbewerbe";

interface EinrichtenSeiteProps {
  turnierId: string;
  suche: EinrichtenSuche;
  onSuche: (suche: EinrichtenSuche) => void;
}

/**
 * Turnier einrichten: links die nummerierten Schritte mit Zustand, rechts der gewählte Schritt
 * mit „Weiter: …“ am Ende (Fenster-Layout). Ohne Angabe öffnet der erste Schritt, in dem noch
 * etwas fehlt.
 */
export function EinrichtenSeite({ turnierId, suche, onSuche }: EinrichtenSeiteProps) {
  const { t, i18n } = useTranslation("turnier");
  const abfrage = useQuery(uebersichtAbfrage(turnierId));
  const darfBearbeiten = useDarf("tournament.edit");
  // Kennt das Backend die Ausschreibung nicht (404), fehlt der Bereich.
  const ausschreibung = useQuery(ausschreibungAbfrage(turnierId));
  const mitAusschreibung = ausschreibung.data !== null;
  const [register] = useState(() => new EntwurfRegister());
  const ungespeichert = useUngespeichert(register);
  const [kopieren, setKopieren] = useState(false);

  const turnier = abfrage.data;
  const punkte = turnier ? offenePunkte(turnier) : [];
  const zustaende = turnier ? schrittZustaende(turnier, punkte) : null;
  const schritte = BEREICHE.filter((b) => b !== "ausschreibung" || mitAusschreibung);
  const bereich: Bereich =
    suche.bereich ?? (zustaende ? ersterOffenerSchritt(zustaende, schritte) : "stammdaten");

  // Den gewählten Schritt in die Adresse schreiben, damit er stehen bleibt, wenn er erledigt ist.
  const ohneBereich = !suche.bereich && Boolean(turnier);
  useEffect(() => {
    if (ohneBereich) onSuche({ bereich, wettbewerb: suche.wettbewerb });
  }, [ohneBereich, bereich, suche.wettbewerb, onSuche]);

  if (abfrage.isPending) {
    return (
      <div className={s.einrichten} aria-busy="true">
        <Skeleton height={72} radius="lg" />
        <div className={s.einrichtenSpalten}>
          <Skeleton height={320} radius="lg" />
          <Skeleton height={480} radius="lg" />
        </div>
      </div>
    );
  }
  if (abfrage.isError || !turnier || !zustaende) {
    return (
      <div className="panel">
        <Fehlerzustand
          fehler={abfrage.error}
          onErneut={() => void abfrage.refetch()}
          eigene={{
            nicht_gefunden: {
              titel: t("einrichten.nicht_gefunden_titel"),
              text: t("einrichten.nicht_gefunden_text"),
            },
          }}
        >
          <Link to={TURNIER_PFAD} className={s.textLink}>
            {t("einrichten.zur_liste")}
          </Link>
        </Fehlerzustand>
      </div>
    );
  }

  // Abgeschlossen oder ohne Recht: nur ansehen. Der Server prüft trotzdem selbst.
  const gesperrt = turnier.status === "closed" || !darfBearbeiten;
  const wechsel = (neu: Bereich) => onSuche({ bereich: neu });
  const index = schritte.indexOf(bereich);
  const naechster = schritte[index + 1];
  // „Turnier starten“ steht im Kopf erst, wenn nichts mehr fehlt; sonst nur in der Zusammenfassung.
  const statusImKopf =
    bereich !== "zusammenfassung" && (turnier.status !== "draft" || punkte.length === 0);

  return (
    <EntwurfKontext.Provider value={register}>
      <div className={s.einrichten} data-layout="fenster" data-bereich={bereich}>
        <header className={s.einrichtenKopf}>
          <div className={s.einrichtenTitel}>
            <Link to={TURNIER_PFAD} className={s.pfad}>
              {t("titel")}
            </Link>
            <div className={s.kopfZeile}>
              <h1 className="h-display">{turnier.name}</h1>
              <StatusChip status={turnier.status} />
              {turnier.is_practice && <UebungChip />}
            </div>
            <p className="gedaempft">
              <span className="num">{zeitraum(turnier, i18n.language)}</span>
              {turnier.organizer && ` · ${turnier.organizer}`}
            </p>
          </div>
          <div className={a.kopfRechts}>
            {!gesperrt && (
              <span
                className={a.speicherstand}
                data-offen={ungespeichert || undefined}
                aria-live="polite"
              >
                {ungespeichert ? <CircleDot aria-hidden /> : <Check aria-hidden />}
                {ungespeichert ? t("speichern.ungespeichert") : t("speichern.alles_gespeichert")}
              </span>
            )}
            {statusImKopf && (
              <StatusAktionen
                turnier={turnier}
                darstellung="knoepfe"
                hinweiseVorStart={punkte.map((p) => t(`offen.${p.schluessel}`, p.werte ?? {}))}
              />
            )}
          </div>
        </header>

        {turnier.is_practice && <UebungBanner turnierId={turnier.id} />}

        {turnier.status === "closed" && (
          <div className={`${s.warnBanner} ${v.umbruch}`} role="status">
            <CircleAlert aria-hidden />
            <span className={v.fuellen}>{t("einrichten.abgeschlossen")}</span>
            {darfBearbeiten && (
              <Button
                variant="default"
                leftSection={<Copy aria-hidden />}
                onClick={() => setKopieren(true)}
              >
                {t("einrichten.kopieren")}
              </Button>
            )}
          </div>
        )}

        {/* Nach dem Kopieren: geänderte Katalog-Disziplinen; nicht, solange ein Wettbewerb offen ist. */}
        {!suche.wettbewerb && <KopieHinweis key={turnier.id} turnier={turnier} />}

        <div className={s.einrichtenSpalten}>
          <Schrittliste
            schritte={schritte}
            aktuell={bereich}
            zustaende={zustaende}
            onWechsel={wechsel}
          />

          <div className={a.bereichSpalte}>
            <div
              className={s.bereichInhalt}
              data-geteilt={
                bereich === "wettbewerbe"
                  ? "zwei"
                  : bereich === "ausschreibung"
                    ? "voll"
                    : undefined
              }
            >
              {bereich === "stammdaten" && <Stammdaten turnier={turnier} gesperrt={gesperrt} />}
              {bereich === "staende" && <Staende turnier={turnier} gesperrt={gesperrt} />}
              {bereich === "klassen" && <Klassen turnier={turnier} gesperrt={gesperrt} />}
              {bereich === "einstellungen" && (
                <Einstellungen turnier={turnier} gesperrt={gesperrt} />
              )}
              {bereich === "wettbewerbe" && (
                <Wettbewerbe
                  turnier={turnier}
                  gesperrt={gesperrt}
                  offen={suche.wettbewerb}
                  onOffen={(id) => onSuche({ bereich, wettbewerb: id })}
                />
              )}
              {bereich === "ausschreibung" && (
                <Ausschreibung turnier={turnier} gesperrt={gesperrt} />
              )}
              {bereich === "zusammenfassung" && (
                <Zusammenfassung
                  turnier={turnier}
                  punkte={punkte}
                  schritte={schritte}
                  zustaende={zustaende}
                  onBereich={wechsel}
                />
              )}
            </div>
            {naechster && (
              <div className={a.weiter}>
                <span className={a.weiterHinweis}>
                  {t("aufgaben.schritt_von", { nr: index + 1, gesamt: schritte.length })}
                </span>
                <Button
                  variant="default"
                  size="md"
                  rightSection={<ArrowRight aria-hidden />}
                  onClick={() => wechsel(naechster)}
                >
                  {t("aufgaben.weiter", { name: t(`bereich.${naechster}.titel`) })}
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
      <EntwurfSchutz register={register} ort={t(`bereich.${bereich}.titel`)} />
      {kopieren && (
        <TurnierAnlegen offen vorbild={turnier.id} onSchliessen={() => setKopieren(false)} />
      )}
    </EntwurfKontext.Provider>
  );
}

const SYMBOL = { erledigt: Check, fehlt: CircleAlert, optional: CircleDashed } as const;

/** Text zum Zustand eines Schritts: „Erledigt“, „Fehlt noch: …“, „Optional“. */
export function useZustandText() {
  const { t } = useTranslation("turnier");
  return (zustand: SchrittZustand): string | null => {
    if (zustand.art === "erledigt") return t("aufgaben.erledigt");
    if (zustand.art === "optional") return t("aufgaben.optional");
    if (zustand.art === "fehlt") {
      return t("aufgaben.fehlt", {
        was: t(`aufgaben.fehlt_was.${zustand.schluessel}`, { count: zustand.anzahl }),
      });
    }
    return null;
  };
}

function Schrittliste({
  schritte,
  aktuell,
  zustaende,
  onWechsel,
}: {
  schritte: readonly Bereich[];
  aktuell: Bereich;
  zustaende: Record<Bereich, SchrittZustand>;
  onWechsel: (bereich: Bereich) => void;
}) {
  const { t } = useTranslation("turnier");
  const zustandText = useZustandText();

  return (
    <nav className={a.schritte} aria-label={t("einrichten.bereiche")}>
      <ol className={a.liste}>
        {schritte.map((eintrag, nr) => {
          const zustand = zustaende[eintrag];
          const text = zustandText(zustand);
          const Zeichen = zustand.art === "ohne" ? null : SYMBOL[zustand.art];
          return (
            <li key={eintrag}>
              <button
                type="button"
                className={a.schritt}
                data-zustand={zustand.art}
                aria-current={eintrag === aktuell ? "step" : undefined}
                onClick={() => onWechsel(eintrag)}
              >
                <span className={a.nummer} aria-hidden>
                  {nr + 1}
                </span>
                <span className={a.schrittText}>
                  <span className={a.schrittTitel}>{t(`bereich.${eintrag}.titel`)}</span>
                  {text && (
                    <span className={a.zustand} data-art={zustand.art}>
                      {Zeichen && <Zeichen aria-hidden />}
                      {text}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {/* Schmal: Auswahl statt Liste; der Zustand des gewählten Schritts steht darunter. */}
      <NativeSelect
        className={a.auswahl}
        size="md"
        label={t("aufgaben.schritt_von", {
          nr: schritte.indexOf(aktuell) + 1,
          gesamt: schritte.length,
        })}
        description={zustandText(zustaende[aktuell]) ?? undefined}
        inputWrapperOrder={["label", "input", "description", "error"]}
        value={aktuell}
        onChange={(e) => onWechsel(e.currentTarget.value as Bereich)}
        data={schritte.map((eintrag, nr) => {
          const art = zustaende[eintrag].art;
          return {
            value: eintrag,
            label: t("aufgaben.auswahl_eintrag", {
              nr: nr + 1,
              name: t(`bereich.${eintrag}.titel`),
              zustand: art === "erledigt" ? ` (${t("aufgaben.erledigt")})` : "",
            }),
          };
        })}
      />
    </nav>
  );
}
