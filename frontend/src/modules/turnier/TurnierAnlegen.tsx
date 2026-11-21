import { Button, Group, Modal, SegmentedControl, TextInput } from "@mantine/core";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useTurnierAnlegen } from "./abfragen";
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
  organizer: string;
  date_from: string;
  date_to: string;
  template: Vorlage;
}): TurnierAnlage {
  const anlage: TurnierAnlage = {
    name: werte.name.trim(),
    date_from: werte.date_from,
    template: werte.template,
  };
  if (werte.organizer.trim()) anlage.organizer = werte.organizer.trim();
  if (werte.date_to && werte.date_to !== werte.date_from) anlage.date_to = werte.date_to;
  return anlage;
}

interface TurnierAnlegenProps {
  offen: boolean;
  onSchliessen: () => void;
}

export function TurnierAnlegen({ offen, onSchliessen }: TurnierAnlegenProps) {
  const { t } = useTranslation("turnier");
  const navigate = useNavigate();
  const anlegen = useTurnierAnlegen();
  const [werte, setWerte] = useState({
    name: "",
    organizer: "",
    date_from: heute(),
    date_to: "",
    template: "open" as Vorlage,
  });
  const [geprueft, setGeprueft] = useState(false);

  const eigene: Record<string, string> = {};
  if (geprueft && !werte.name.trim()) eigene.name = t("pruefung.pflicht");
  if (geprueft && !werte.date_from) eigene.date_from = t("pruefung.pflicht");
  if (werte.date_to && werte.date_from && werte.date_to < werte.date_from) {
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
          anlegen.mutate(anlageAusFormular(werte), {
            onSuccess: (turnier) => {
              onSchliessen();
              void navigate({
                to: EINRICHTEN_PFAD,
                params: { turnierId: turnier.id },
                search: { bereich: "stammdaten" },
              });
            },
          });
        }}
      >
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
        <TextInput
          label={t("feld.veranstalter")}
          placeholder={t("feld.veranstalter_platzhalter")}
          size="md"
          value={werte.organizer}
          error={fehler.organizer}
          onChange={(e) => setze("organizer", e.currentTarget.value)}
        />
        <div className={s.zweiSpalten}>
          <TextInput
            type="date"
            label={t("feld.datum_von")}
            required
            size="md"
            value={werte.date_from}
            error={fehler.date_from}
            onChange={(e) => setze("date_from", e.currentTarget.value)}
          />
          <TextInput
            type="date"
            label={t("feld.datum_bis")}
            description={t("feld.datum_bis_hilfe")}
            size="md"
            value={werte.date_to}
            min={werte.date_from}
            error={fehler.date_to}
            onChange={(e) => setze("date_to", e.currentTarget.value)}
          />
        </div>
        <div className={s.feldGruppe}>
          <span className={s.feldLabel} id="vorlage-label">
            {t("feld.vorlage")}
          </span>
          <SegmentedControl
            aria-labelledby="vorlage-label"
            fullWidth
            size="md"
            value={werte.template}
            onChange={(wert) => setze("template", wert)}
            data={VORLAGEN.map((vorlage) => ({
              value: vorlage,
              label: t(`vorlage.${vorlage}.name`),
            }))}
            className={s.segmente}
          />
          <p className={s.hilfe}>{t(`vorlage.${werte.template}.text`)}</p>
        </div>
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
