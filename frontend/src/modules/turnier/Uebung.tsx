import { Button } from "@mantine/core";
import { useNavigate } from "@tanstack/react-router";
import { FlaskConical, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../app/berechtigungen";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip } from "../../components/Chip";
import { merkeTurnier } from "../../components/useAktivesTurnier";
import { useUebungAnlegen, useUebungLoeschen } from "./abfragen";
import { fehlerText } from "./fehlertext";
import { EINRICHTEN_PFAD, TURNIER_PFAD } from "./pfade";
import v from "./vorlagen.module.css";

/**
 * Kennzeichen „Übung“ in Info-Farbe (nicht Gold, nicht Grün): Am Turniertag soll niemand
 * versehentlich im Übungsturnier arbeiten.
 */
export function UebungChip() {
  const { t } = useTranslation("turnier");
  return (
    <Chip ton="info" icon={FlaskConical} title={t("uebung.kennzeichen_lang")}>
      {t("uebung.kennzeichen")}
    </Chip>
  );
}

interface UebungStartenProps {
  /** `knopf`: Knopf mit Rahmen (Leerzustand); `leise`: Textknopf (dezent unter anderen Wegen) */
  darstellung?: "knopf" | "leise";
  /** Text des Knopfs; Standard „Zum Ausprobieren: Übungsturnier mit Beispieldaten“ */
  text?: string;
  /** Vor dem Wechsel ins Übungsturnier, z. B. einen Dialog schließen */
  onGeoeffnet?: () => void;
}

/**
 * Legt das Übungsturnier an und öffnet es. Gibt es schon eins, öffnet der Knopf das vorhandene.
 * Erscheint nur mit dem Recht, Turniere einzurichten.
 */
export function UebungStarten({ darstellung = "knopf", text, onGeoeffnet }: UebungStartenProps) {
  const { t } = useTranslation("turnier");
  const navigate = useNavigate();
  const anlegen = useUebungAnlegen();
  const darf = useDarf("tournament.edit");
  if (!darf) return null;

  return (
    <div className={v.uebungStarten}>
      <Button
        variant={darstellung === "leise" ? "subtle" : "default"}
        color={darstellung === "leise" ? "gray" : undefined}
        size="md"
        leftSection={<FlaskConical aria-hidden />}
        classNames={{ root: v.mehrzeilig, inner: v.mehrzeiligInnen, label: v.mehrzeiligText }}
        loading={anlegen.isPending}
        onClick={() =>
          anlegen.mutate(undefined, {
            onSuccess: ({ id }) => {
              merkeTurnier(id);
              onGeoeffnet?.();
              void navigate({ to: EINRICHTEN_PFAD, params: { turnierId: id }, search: {} });
            },
          })
        }
      >
        {text ?? t("uebung.starten")}
      </Button>
      {anlegen.isError && (
        <p className={v.fehler} role="alert">
          {fehlerText(anlegen.error)}
        </p>
      )}
    </div>
  );
}

interface UebungLoeschenProps {
  turnierId: string;
  offen: boolean;
  onSchliessen: () => void;
  /** Nach dem Löschen, z. B. zur Liste wechseln */
  onGeloescht?: () => void;
}

/** Rückfrage vor dem Löschen des Übungsturniers (Meldefarbe kritisch). */
export function UebungLoeschen({
  turnierId,
  offen,
  onSchliessen,
  onGeloescht,
}: UebungLoeschenProps) {
  const { t } = useTranslation("turnier");
  const loeschen = useUebungLoeschen();
  return (
    <Bestaetigung
      offen={offen}
      titel={t("uebung.loeschen_titel")}
      text={<p>{t("uebung.loeschen_text")}</p>}
      bestaetigen={t("uebung.loeschen_knopf")}
      abbrechen={t("aktion.abbrechen")}
      ton="gefahr"
      laedt={loeschen.isPending}
      fehler={loeschen.isError ? fehlerText(loeschen.error) : undefined}
      onSchliessen={() => {
        loeschen.reset();
        onSchliessen();
      }}
      onBestaetigen={() =>
        loeschen.mutate(turnierId, {
          onSuccess: () => {
            onSchliessen();
            onGeloescht?.();
          },
        })
      }
    />
  );
}

/** Hinweis oben in der Einrichtung des Übungsturniers, mit „Übung löschen“. */
export function UebungBanner({ turnierId }: { turnierId: string }) {
  const { t } = useTranslation("turnier");
  const navigate = useNavigate();
  const darf = useDarf("tournament.edit");
  const [frage, setFrage] = useState(false);
  return (
    <section className={v.uebungBanner} aria-labelledby="uebung-titel">
      <FlaskConical aria-hidden className={v.bannerSymbol} />
      <div className={v.bannerText}>
        <strong id="uebung-titel">{t("uebung.banner_titel")}</strong>
        <span>{t("uebung.banner_text")}</span>
      </div>
      {darf && (
        <Button
          variant="default"
          className={v.gefahrKnopf}
          leftSection={<Trash2 aria-hidden />}
          onClick={() => setFrage(true)}
        >
          {t("uebung.loeschen")}
        </Button>
      )}
      <UebungLoeschen
        turnierId={turnierId}
        offen={frage}
        onSchliessen={() => setFrage(false)}
        onGeloescht={() => void navigate({ to: TURNIER_PFAD })}
      />
    </section>
  );
}
