import { TextInput } from "@mantine/core";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useTurnierAendern } from "../abfragen";
import { bisNachVon } from "../anfang";
import { feldFehlerFuer } from "../senden";
import s from "../turnier.module.css";
import type { TurnierAenderung, TurnierUebersicht } from "../typen";
import { useEntwurf } from "../useEntwurf";
import { BereichKopf, HILFE_UNTEN, Speicherleiste } from "./Bausteine";

const FELDER = ["name", "organizer", "date_from", "date_to"] as const;

interface Stammwerte {
  name: string;
  organizer: string;
  date_from: string;
  date_to: string;
}

/** Nur geänderte Stammdaten; ein leerer Veranstalter wird `null`. */
export function stammdatenAenderung(werte: Stammwerte, basis: Stammwerte): TurnierAenderung {
  const aenderung: TurnierAenderung = {};
  if (werte.name.trim() !== basis.name) aenderung.name = werte.name.trim();
  if (werte.organizer.trim() !== basis.organizer)
    aenderung.organizer = werte.organizer.trim() || null;
  if (werte.date_from !== basis.date_from) aenderung.date_from = werte.date_from;
  if (werte.date_to !== basis.date_to) aenderung.date_to = werte.date_to || werte.date_from;
  return aenderung;
}

/** Schritt 1: Name, Datum und Veranstalter des Turniers. */
export function Stammdaten({
  turnier,
  gesperrt,
}: {
  turnier: TurnierUebersicht;
  gesperrt: boolean;
}) {
  const { t } = useTranslation("turnier");
  const aendern = useTurnierAendern(turnier.id);
  const quelle = useMemo<Stammwerte>(
    () => ({
      name: turnier.name,
      organizer: turnier.organizer ?? "",
      date_from: turnier.date_from,
      date_to: turnier.date_to,
    }),
    [turnier.name, turnier.organizer, turnier.date_from, turnier.date_to],
  );
  const [geprueft, setGeprueft] = useState(false);
  const entwurf = useEntwurf(quelle, {
    speichern: async () => {
      setGeprueft(true);
      if (!gueltig(entwurf.werte)) return false;
      try {
        await aendern.mutateAsync(stammdatenAenderung(entwurf.werte, entwurf.basis));
        return true;
      } catch {
        return false;
      }
    },
  });
  const { werte } = entwurf;

  const eigene: Record<string, string> = {};
  if (geprueft && !werte.name.trim()) eigene.name = t("pruefung.pflicht");
  if (werte.date_to && werte.date_from && werte.date_to < werte.date_from) {
    eigene.date_to = t("pruefung.datum_reihenfolge");
  }
  const fehler = { ...(aendern.isError ? feldFehlerFuer(aendern.error, FELDER) : {}), ...eigene };
  // „Datum bis“ selbst geändert? Bis dahin wandert es mit „Datum von“ mit (gleiche Dauer).
  const [bisEigen, setBisEigen] = useState(false);
  const setze = (feld: keyof Stammwerte, wert: string) => {
    if (feld === "date_from") {
      entwurf.setWerte({ ...werte, date_from: wert, date_to: bisNachVon(werte, wert, bisEigen) });
    } else {
      if (feld === "date_to") setBisEigen(true);
      entwurf.setWerte({ ...werte, [feld]: wert });
    }
    if (aendern.isError) aendern.reset();
  };

  return (
    <form
      className={s.bereich}
      noValidate
      onSubmit={(ereignis) => {
        ereignis.preventDefault();
        setGeprueft(true);
        if (!gueltig(werte)) return;
        aendern.mutate(stammdatenAenderung(werte, entwurf.basis));
      }}
    >
      <BereichKopf titel={t("bereich.stammdaten.titel")} text={t("bereich.stammdaten.text")} />
      <section className={`panel ${s.formular}`}>
        <TextInput
          label={t("feld.name")}
          required
          size="md"
          disabled={gesperrt}
          value={werte.name}
          error={fehler.name}
          onChange={(e) => setze("name", e.currentTarget.value)}
        />
        <div className={s.zweiSpalten}>
          <TextInput
            type="date"
            label={t("feld.datum_von")}
            required
            size="md"
            disabled={gesperrt}
            value={werte.date_from}
            error={fehler.date_from}
            onChange={(e) => setze("date_from", e.currentTarget.value)}
          />
          <TextInput
            type="date"
            label={t("feld.datum_bis")}
            description={t("feld.datum_bis_hilfe")}
            inputWrapperOrder={HILFE_UNTEN}
            size="md"
            disabled={gesperrt}
            value={werte.date_to}
            min={werte.date_from}
            error={fehler.date_to}
            onChange={(e) => setze("date_to", e.currentTarget.value)}
          />
        </div>
        <TextInput
          label={t("feld.veranstalter")}
          description={t("feld.veranstalter_hilfe")}
          inputWrapperOrder={HILFE_UNTEN}
          placeholder={t("feld.veranstalter_platzhalter")}
          size="md"
          disabled={gesperrt}
          value={werte.organizer}
          error={fehler.organizer}
          onChange={(e) => setze("organizer", e.currentTarget.value)}
        />
        <p className={s.hilfe}>
          {t("bereich.stammdaten.vorlage_hinweis", {
            vorlage: t(`vorlage.${turnier.template}.name`),
            bereich: t("bereich.einstellungen.titel"),
          })}
        </p>
      </section>
      <Speicherleiste
        geaendert={entwurf.geaendert}
        laedt={aendern.isPending}
        gespeichert={aendern.isSuccess && !entwurf.geaendert}
        fehler={fehler[""]}
        gesperrt={gesperrt}
        onVerwerfen={() => {
          entwurf.verwerfen();
          aendern.reset();
          setGeprueft(false);
          setBisEigen(false);
        }}
      />
    </form>
  );
}

function gueltig(werte: Stammwerte): boolean {
  if (!werte.name.trim()) return false;
  return !(werte.date_to && werte.date_from && werte.date_to < werte.date_from);
}
