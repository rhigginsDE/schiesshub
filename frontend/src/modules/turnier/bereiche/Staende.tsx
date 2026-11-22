import { ActionIcon, Button, NumberInput, TextInput } from "@mantine/core";
import { LandPlot, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bestaetigung } from "../../../components/Bestaetigung";
import { ReihenfolgeKnoepfe, verschiebe } from "../../../components/Reihenfolge";
import { Leerzustand } from "../../../components/Zustand";
import { formatZahl } from "../../../lib/format";
import {
  useStaendeSortieren,
  useStandAendern,
  useStandAnlegen,
  useStandLoeschen,
} from "../abfragen";
import a from "../aufgaben.module.css";
import { fehlerText } from "../fehlertext";
import { feldFehlerFuer } from "../senden";
import s from "../turnier.module.css";
import type { Stand, TurnierUebersicht } from "../typen";
import { BereichKopf } from "./Bausteine";

const FELDER = ["name", "lane_count"] as const;

interface StandWerte {
  name: string;
  lane_count: number | "";
}

function pruefe(werte: StandWerte, t: (s: string) => string): Record<string, string> {
  const fehler: Record<string, string> = {};
  if (!werte.name.trim()) fehler.name = t("pruefung.pflicht");
  if (typeof werte.lane_count !== "number" || werte.lane_count < 1) {
    fehler.lane_count = t("pruefung.ganz_positiv");
  }
  return fehler;
}

export function Staende({ turnier, gesperrt }: { turnier: TurnierUebersicht; gesperrt: boolean }) {
  const { t } = useTranslation("turnier");
  const sortieren = useStaendeSortieren(turnier.id);
  const staende = turnier.ranges;
  // Mit einem Stand ist alles entschieden; ein weiterer Stand ist eine bewusste Zusatzaufgabe.
  const [weiterer, setWeiterer] = useState(false);

  return (
    <div className={s.bereich}>
      <BereichKopf titel={t("bereich.staende.titel")} text={t("bereich.staende.text")} />
      {staende.length === 0 ? (
        !gesperrt ? (
          <StandNeu turnierId={turnier.id} erster />
        ) : (
          <section className="panel">
            <Leerzustand
              icon={LandPlot}
              titel={t("staende.leer_titel")}
              text={t("staende.leer_text")}
            />
          </section>
        )
      ) : (
        <section className="panel" aria-labelledby="staende-liste">
          <h3 className="nur-screenreader" id="staende-liste">
            {t("bereich.staende.titel")}
          </h3>
          <ul className={s.zeilenListe}>
            {staende.map((stand, index) => (
              <StandZeile
                key={stand.id}
                turnier={turnier}
                stand={stand}
                index={index}
                gesperrt={gesperrt || sortieren.isPending}
                onVerschieben={(richtung) =>
                  sortieren.mutate(
                    verschiebe(staende, index, richtung).map((eintrag) => eintrag.id),
                  )
                }
              />
            ))}
          </ul>
          {staende.length > 1 && <p className={s.hilfe}>{t("staende.reihenfolge_hinweis")}</p>}
          {sortieren.isError && (
            <p className={s.fehlerText} role="alert">
              {fehlerText(sortieren.error)}
            </p>
          )}
        </section>
      )}
      {!gesperrt &&
        staende.length > 0 &&
        (weiterer ? (
          <StandNeu turnierId={turnier.id} onFertig={() => setWeiterer(false)} />
        ) : (
          <div className={a.knopfLinks}>
            <Button
              variant="default"
              size="md"
              leftSection={<Plus aria-hidden />}
              onClick={() => setWeiterer(true)}
            >
              {t("staende.weiterer")}
            </Button>
          </div>
        ))}
    </div>
  );
}

/**
 * Formular für einen Stand. Beim ersten Stand ist „Stand anlegen“ die Hauptaktion; ein weiterer
 * Stand lässt sich abbrechen.
 */
function StandNeu({
  turnierId,
  erster,
  onFertig,
}: {
  turnierId: string;
  erster?: boolean;
  onFertig?: () => void;
}) {
  const { t } = useTranslation("turnier");
  const anlegen = useStandAnlegen(turnierId);
  const [werte, setWerte] = useState<StandWerte>({ name: "", lane_count: 6 });
  const [geprueft, setGeprueft] = useState(false);
  const fehler = {
    ...(anlegen.isError ? feldFehlerFuer(anlegen.error, FELDER) : {}),
    ...(geprueft ? pruefe(werte, t) : {}),
  };

  return (
    <form
      className={`panel ${s.formular}`}
      aria-labelledby="stand-neu"
      noValidate
      onSubmit={(ereignis) => {
        ereignis.preventDefault();
        setGeprueft(true);
        if (Object.keys(pruefe(werte, t)).length > 0) return;
        anlegen.mutate(
          { name: werte.name.trim(), lane_count: werte.lane_count as number },
          {
            onSuccess: () => {
              setWerte({ name: "", lane_count: werte.lane_count });
              setGeprueft(false);
              onFertig?.();
            },
          },
        );
      }}
    >
      <div>
        <h3 className="h-section" id="stand-neu">
          {erster ? t("staende.erster_titel") : t("staende.neu")}
        </h3>
        {erster && <p className={s.hilfe}>{t("staende.erster_text")}</p>}
      </div>
      <div className={s.zeileFormular}>
        <TextInput
          label={t("staende.name")}
          placeholder={t("staende.name_platzhalter")}
          size="md"
          autoFocus={!erster}
          value={werte.name}
          error={fehler.name}
          onChange={(e) => setWerte({ ...werte, name: e.currentTarget.value })}
        />
        <NumberInput
          label={t("staende.bahnen")}
          size="md"
          min={1}
          max={200}
          allowDecimal={false}
          value={werte.lane_count}
          error={fehler.lane_count}
          onChange={(wert) =>
            setWerte({ ...werte, lane_count: typeof wert === "number" ? wert : "" })
          }
        />
        <Button
          type="submit"
          size="md"
          variant={erster ? "filled" : "default"}
          leftSection={<Plus aria-hidden />}
          loading={anlegen.isPending}
        >
          {t("staende.anlegen")}
        </Button>
      </div>
      {fehler[""] && (
        <p className={s.fehlerText} role="alert">
          {fehler[""]}
        </p>
      )}
      {onFertig && (
        <div className={a.knopfLinks}>
          <Button variant="subtle" color="gray" size="md" onClick={onFertig}>
            {t("aktion.abbrechen")}
          </Button>
        </div>
      )}
    </form>
  );
}

interface StandZeileProps {
  turnier: TurnierUebersicht;
  stand: Stand;
  index: number;
  gesperrt: boolean;
  onVerschieben: (richtung: -1 | 1) => void;
}

function StandZeile({ turnier, stand, index, gesperrt, onVerschieben }: StandZeileProps) {
  const { t, i18n } = useTranslation("turnier");
  const aendern = useStandAendern(turnier.id);
  const loeschen = useStandLoeschen(turnier.id);
  const [bearbeiten, setBearbeiten] = useState(false);
  const [frage, setFrage] = useState(false);
  const [werte, setWerte] = useState<StandWerte>({
    name: stand.name,
    lane_count: stand.lane_count,
  });
  const fehler = {
    ...(aendern.isError ? feldFehlerFuer(aendern.error, FELDER) : {}),
    ...pruefe(werte, t),
  };
  const betroffen = turnier.competitions.filter((w) => w.range_id === stand.id).length;

  if (bearbeiten) {
    return (
      <li className={s.zeileOffen}>
        <form
          className={s.zeileFormular}
          noValidate
          onSubmit={(ereignis) => {
            ereignis.preventDefault();
            if (Object.keys(pruefe(werte, t)).length > 0) return;
            aendern.mutate(
              {
                standId: stand.id,
                daten: { name: werte.name.trim(), lane_count: werte.lane_count as number },
              },
              { onSuccess: () => setBearbeiten(false) },
            );
          }}
        >
          <TextInput
            label={t("staende.name")}
            size="md"
            data-autofocus
            value={werte.name}
            error={fehler.name}
            onChange={(e) => setWerte({ ...werte, name: e.currentTarget.value })}
          />
          <NumberInput
            label={t("staende.bahnen")}
            size="md"
            min={1}
            max={200}
            allowDecimal={false}
            value={werte.lane_count}
            error={fehler.lane_count}
            onChange={(wert) =>
              setWerte({ ...werte, lane_count: typeof wert === "number" ? wert : "" })
            }
          />
          <div className={s.knopfReihe}>
            <Button variant="default" size="md" onClick={() => setBearbeiten(false)}>
              {t("aktion.abbrechen")}
            </Button>
            <Button type="submit" variant="default" size="md" loading={aendern.isPending}>
              {t("aktion.uebernehmen")}
            </Button>
          </div>
        </form>
        {fehler[""] && (
          <p className={s.fehlerText} role="alert">
            {fehler[""]}
          </p>
        )}
      </li>
    );
  }

  return (
    <li className={s.zeile}>
      <span className={s.zeileText}>
        <strong>{stand.name}</strong>
        <span className="gedaempft">
          <span className="num">
            {t("staende.bahnen_anzahl", {
              count: stand.lane_count,
              anzahl: formatZahl(stand.lane_count, {}, i18n.language),
            })}
          </span>
          {betroffen > 0 && ` · ${t("staende.wettbewerbe", { count: betroffen })}`}
        </span>
      </span>
      <span className={s.zeilenAktionen}>
        {turnier.ranges.length > 1 && (
          <ReihenfolgeKnoepfe
            index={index}
            anzahl={turnier.ranges.length}
            hoch={t("aktion.nach_oben", { name: stand.name })}
            runter={t("aktion.nach_unten", { name: stand.name })}
            gesperrt={gesperrt}
            onVerschieben={onVerschieben}
          />
        )}
        <ActionIcon
          variant="subtle"
          color="gray"
          size={40}
          aria-label={t("aktion.bearbeiten", { name: stand.name })}
          title={t("aktion.bearbeiten", { name: stand.name })}
          disabled={gesperrt}
          onClick={() => {
            setWerte({ name: stand.name, lane_count: stand.lane_count });
            aendern.reset();
            setBearbeiten(true);
          }}
        >
          <Pencil aria-hidden />
        </ActionIcon>
        <ActionIcon
          variant="subtle"
          color="gray"
          size={40}
          aria-label={t("aktion.loeschen", { name: stand.name })}
          title={t("aktion.loeschen", { name: stand.name })}
          disabled={gesperrt}
          onClick={() => {
            loeschen.reset();
            setFrage(true);
          }}
        >
          <Trash2 aria-hidden />
        </ActionIcon>
      </span>
      <Bestaetigung
        offen={frage}
        titel={t("staende.loeschen_titel", { name: stand.name })}
        text={
          <p>
            {betroffen > 0
              ? t("staende.loeschen_text_wettbewerbe", { count: betroffen })
              : t("staende.loeschen_text")}
          </p>
        }
        bestaetigen={t("aktion.loeschen_knopf")}
        abbrechen={t("aktion.abbrechen")}
        ton="gefahr"
        laedt={loeschen.isPending}
        fehler={loeschen.isError ? fehlerText(loeschen.error) : undefined}
        onSchliessen={() => setFrage(false)}
        onBestaetigen={() => loeschen.mutate(stand.id, { onSuccess: () => setFrage(false) })}
      />
    </li>
  );
}
