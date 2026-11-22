import { Button, Checkbox, Group, Modal, Radio, TextInput } from "@mantine/core";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useTurnierAnlegen } from "./abfragen";
import a from "./aufgaben.module.css";
import { EINRICHTEN_PFAD } from "./pfade";
import { feldFehlerFuer } from "./senden";
import s from "./turnier.module.css";
import { type TurnierAnlage, VORLAGEN, type Vorlage } from "./typen";

const FELDER = ["name", "organizer", "date_from", "date_to", "template"] as const;

function heute(): string {
  const jetzt = new Date();
  const zwei = (zahl: number) => String(zahl).padStart(2, "0");
  return `${jetzt.getFullYear()}-${zwei(jetzt.getMonth() + 1)}-${zwei(jetzt.getDate())}`;
}

/** Formular → Anlage für `POST /tournaments`. Leere Angaben fallen weg (eintägig, ohne Veranstalter). */
export function anlageAusFormular(werte: {
  name: string;
  organizer?: string;
  date_from: string;
  date_to: string;
  template: Vorlage;
}): TurnierAnlage {
  const anlage: TurnierAnlage = {
    name: werte.name.trim(),
    date_from: werte.date_from,
    template: werte.template,
  };
  if (werte.organizer?.trim()) anlage.organizer = werte.organizer.trim();
  if (werte.date_to && werte.date_to !== werte.date_from) anlage.date_to = werte.date_to;
  return anlage;
}

interface TurnierAnlegenProps {
  offen: boolean;
  onSchliessen: () => void;
}

/**
 * Neues Turnier mit so wenigen Fragen wie möglich: Name, Datum (heute vorbelegt, eintägig) und
 * Turnierart. Alles Weitere folgt Schritt für Schritt in der Einrichtung; dorthin geht es danach.
 */
export function TurnierAnlegen({ offen, onSchliessen }: TurnierAnlegenProps) {
  const { t } = useTranslation("turnier");
  const navigate = useNavigate();
  const anlegen = useTurnierAnlegen();
  const [werte, setWerte] = useState({
    name: "",
    date_from: heute(),
    date_to: "",
    template: "open" as Vorlage,
  });
  const [mehrtaegig, setMehrtaegig] = useState(false);
  const [geprueft, setGeprueft] = useState(false);

  const eigene: Record<string, string> = {};
  if (geprueft && !werte.name.trim()) eigene.name = t("pruefung.pflicht");
  if (geprueft && !werte.date_from) eigene.date_from = t("pruefung.pflicht");
  if (mehrtaegig && werte.date_to && werte.date_from && werte.date_to < werte.date_from) {
    eigene.date_to = t("pruefung.datum_reihenfolge");
  }
  const server = anlegen.isError ? feldFehlerFuer(anlegen.error, FELDER) : {};
  const fehler = { ...server, ...eigene };

  const setze = (feld: keyof typeof werte, wert: string) => {
    setWerte((vorher) => ({ ...vorher, [feld]: wert }));
    if (anlegen.isError) anlegen.reset();
  };

  return (
    <Modal
      opened={offen}
      onClose={onSchliessen}
      title={t("anlegen.titel")}
      closeButtonProps={{ "aria-label": t("aktion.abbrechen") }}
      centered
      size="lg"
    >
      <form
        className={s.formular}
        noValidate
        onSubmit={(ereignis) => {
          ereignis.preventDefault();
          setGeprueft(true);
          if (!werte.name.trim() || !werte.date_from || eigene.date_to) return;
          anlegen.mutate(
            anlageAusFormular({ ...werte, date_to: mehrtaegig ? werte.date_to : "" }),
            {
              onSuccess: (turnier) => {
                onSchliessen();
                // Ohne Bereich öffnet die Einrichtung den ersten Schritt, in dem noch etwas fehlt.
                void navigate({
                  to: EINRICHTEN_PFAD,
                  params: { turnierId: turnier.id },
                  search: {},
                });
              },
            },
          );
        }}
      >
        <p className={s.hilfe}>{t("anlegen.text")}</p>
        <TextInput
          label={t("feld.name")}
          placeholder={t("feld.name_platzhalter")}
          required
          size="md"
          data-autofocus
          value={werte.name}
          error={fehler.name}
          onChange={(e) => setze("name", e.currentTarget.value)}
        />
        <div className={s.zweiSpalten}>
          <TextInput
            type="date"
            label={mehrtaegig ? t("feld.datum_von") : t("feld.datum")}
            required
            size="md"
            value={werte.date_from}
            error={fehler.date_from}
            onChange={(e) => setze("date_from", e.currentTarget.value)}
          />
          {mehrtaegig && (
            <TextInput
              type="date"
              label={t("feld.datum_bis")}
              size="md"
              value={werte.date_to}
              min={werte.date_from}
              error={fehler.date_to}
              onChange={(e) => setze("date_to", e.currentTarget.value)}
            />
          )}
        </div>
        <Checkbox
          size="md"
          label={t("anlegen.mehrtaegig")}
          checked={mehrtaegig}
          onChange={(e) => setMehrtaegig(e.currentTarget.checked)}
        />
        <Radio.Group
          label={t("anlegen.art")}
          size="md"
          value={werte.template}
          onChange={(wert) => setze("template", wert)}
        >
          <div className={a.arten}>
            {VORLAGEN.map((vorlage) => (
              <Radio.Card
                key={vorlage}
                value={vorlage}
                withBorder={false}
                radius="md"
                className={a.art}
                aria-label={t(`vorlage.${vorlage}.name`)}
              >
                <Radio.Indicator size="md" />
                <span className={a.artText}>
                  <strong>{t(`vorlage.${vorlage}.name`)}</strong>
                  <span>{t(`vorlage.${vorlage}.text`)}</span>
                </span>
              </Radio.Card>
            ))}
          </div>
        </Radio.Group>
        {fehler[""] && (
          <p className={s.fehlerText} role="alert">
            {fehler[""]}
          </p>
        )}
        <Group justify="flex-end" gap="sm">
          <Button variant="default" size="md" onClick={onSchliessen}>
            {t("aktion.abbrechen")}
          </Button>
          <Button type="submit" size="md" loading={anlegen.isPending}>
            {t("anlegen.knopf")}
          </Button>
        </Group>
      </form>
    </Modal>
  );
}
