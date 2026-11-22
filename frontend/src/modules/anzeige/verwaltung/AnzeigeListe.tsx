import { ActionIcon, Button, Menu, TextInput } from "@mantine/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, MonitorPlay, MoreVertical, Pencil, Plus, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiFehler, serverMeldung } from "../../../api/client";
import { Bestaetigung } from "../../../components/Bestaetigung";
import { Dialog } from "../../../components/Dialog";
import { FehlerHinweis, useFehlerText } from "../../../components/FehlerHinweis";
import { zeigeMeldung } from "../../../components/Meldungen";
import { verschiebe } from "../../../components/Reihenfolge";
import { useAktivesTurnier } from "../../../components/useAktivesTurnier";
import type { Turnier } from "../../turnier/typen";
import {
  anzeigeAendern,
  anzeigeFuerTurnierAnlegen,
  anzeigeLoeschen,
  anzeigeSchluessel,
  standardAnlegen,
} from "../api";
import type { Anzeige } from "../typen";
import s from "./verwaltung.module.css";

interface AnzeigeListeProps {
  anzeigen: Anzeige[];
  aktivId: string | null;
  turniere: Turnier[];
  onWahl: (id: string) => void;
}

/** Linke Spalte: alle Anzeigen, anlegen, umbenennen, löschen, Reihenfolge. */
export function AnzeigeListe({ anzeigen, aktivId, turniere, onWahl }: AnzeigeListeProps) {
  const { t } = useTranslation("anzeige");
  const neuAnlegen = useNeueAnzeige(anzeigen.length);
  const queryClient = useQueryClient();
  const [anlegen, setAnlegen] = useState(false);
  const neuLaden = () => queryClient.invalidateQueries({ queryKey: anzeigeSchluessel.alle });

  const ordnen = useMutation({
    mutationFn: async (neu: Anzeige[]) => {
      for (const [index, anzeige] of neu.entries()) {
        if (anzeige.sort !== index) await anzeigeAendern(anzeige.id, { sort: index });
      }
    },
    onSettled: neuLaden,
  });
  const fehlerText = useFehlerText();

  const unterzeile = (anzeige: Anzeige) => {
    const turnier = anzeige.tournament_id
      ? (turniere.find((x) => x.id === anzeige.tournament_id)?.name ?? t("liste.turnier_fest"))
      : t("liste.turnier_auto");
    const szenen = t("liste.szenen", { count: anzeige.config.scenes?.length ?? 0 });
    const geraet = anzeige.device_id ? t("liste.mit_geraet") : null;
    return [turnier, szenen, geraet].filter(Boolean).join(" · ");
  };

  return (
    <nav className={`panel ${s.liste}`} aria-label={t("liste.titel")}>
      <div className={s.listeKopf}>
        <h1 className="h-section">{t("titel")}</h1>
        <Button
          variant="default"
          leftSection={<Plus aria-hidden />}
          onClick={() => setAnlegen(true)}
        >
          {t("liste.neu")}
        </Button>
      </div>
      <ul className={s.eintraege}>
        {anzeigen.map((anzeige, index) => (
          <li
            key={anzeige.id}
            className={s.eintrag}
            aria-current={anzeige.id === aktivId ? "true" : undefined}
          >
            <button type="button" className={s.eintragKnopf} onClick={() => onWahl(anzeige.id)}>
              <strong>{anzeige.name}</strong>
              <span>{unterzeile(anzeige)}</span>
            </button>
            <span className={s.eintragAktionen}>
              <EintragMenue
                anzeige={anzeige}
                kannHoch={index > 0 && !ordnen.isPending}
                kannRunter={index < anzeigen.length - 1 && !ordnen.isPending}
                onVerschieben={(richtung) => ordnen.mutate(verschiebe(anzeigen, index, richtung))}
              />
            </span>
          </li>
        ))}
      </ul>
      {ordnen.isError && <FehlerHinweis fehler={ordnen.error} text={fehlerText(ordnen.error)} />}
      {anlegen && (
        <NameDialog
          titel={t("liste.neu_titel")}
          start=""
          speichern={neuAnlegen}
          onFertig={(neu) => {
            setAnlegen(false);
            if (neu) onWahl(neu.id);
          }}
        />
      )}
    </nav>
  );
}

/**
 * Neue Anzeige gleich brauchbar: fest auf das Turnier dieses Geräts (sonst wählt der Server das
 * laufende), mit Live-Wertung, Startliste und Siegerliste.
 */
function useNeueAnzeige(sort: number) {
  const { turnier } = useAktivesTurnier();
  return (name: string) => anzeigeFuerTurnierAnlegen(name, turnier?.id ?? null, sort);
}

/** Ohne Anzeige: Standard anlegen oder eine neue. */
export function KeineAnzeige({ onWahl }: { onWahl: (id: string) => void }) {
  const { t } = useTranslation("anzeige");
  const neuAnlegen = useNeueAnzeige(0);
  const queryClient = useQueryClient();
  const [anlegen, setAnlegen] = useState(false);
  const standard = useMutation({
    mutationFn: standardAnlegen,
    onSuccess: (neu) => {
      void queryClient.invalidateQueries({ queryKey: anzeigeSchluessel.alle });
      onWahl(neu.id);
    },
  });
  return (
    <>
      <Button
        leftSection={<MonitorPlay aria-hidden />}
        loading={standard.isPending}
        onClick={() => standard.mutate()}
      >
        {t("leer.standard")}
      </Button>
      <Button variant="default" leftSection={<Plus aria-hidden />} onClick={() => setAnlegen(true)}>
        {t("liste.neu")}
      </Button>
      <FehlerHinweis fehler={standard.error} />
      {anlegen && (
        <NameDialog
          titel={t("liste.neu_titel")}
          start=""
          speichern={neuAnlegen}
          onFertig={(neu) => {
            setAnlegen(false);
            if (neu) onWahl(neu.id);
          }}
        />
      )}
    </>
  );
}

function EintragMenue({
  anzeige,
  kannHoch,
  kannRunter,
  onVerschieben,
}: {
  anzeige: Anzeige;
  kannHoch: boolean;
  kannRunter: boolean;
  onVerschieben: (richtung: -1 | 1) => void;
}) {
  const { t } = useTranslation("anzeige");
  const queryClient = useQueryClient();
  const [frage, setFrage] = useState<"umbenennen" | "loeschen" | null>(null);
  const loeschen = useMutation({
    mutationFn: () => anzeigeLoeschen(anzeige.id),
    onSuccess: () => {
      setFrage(null);
      void queryClient.invalidateQueries({ queryKey: anzeigeSchluessel.alle });
      zeigeMeldung({ ton: "info", titel: t("liste.geloescht", { name: anzeige.name }) });
    },
  });
  const loeschFehler = (() => {
    if (!loeschen.error) return undefined;
    const grund = serverMeldung(loeschen.error);
    if (loeschen.error instanceof ApiFehler && loeschen.error.art === "konflikt") {
      return t("liste.loeschen_konflikt", { grund: grund ?? "" });
    }
    return grund ?? t("liste.loeschen_fehler");
  })();

  return (
    <>
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <ActionIcon
            variant="subtle"
            color="gray"
            size={40}
            aria-label={t("liste.aktionen", { name: anzeige.name })}
          >
            <MoreVertical aria-hidden />
          </ActionIcon>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item
            leftSection={<ArrowUp aria-hidden />}
            disabled={!kannHoch}
            onClick={() => onVerschieben(-1)}
          >
            {t("liste.nach_oben")}
          </Menu.Item>
          <Menu.Item
            leftSection={<ArrowDown aria-hidden />}
            disabled={!kannRunter}
            onClick={() => onVerschieben(1)}
          >
            {t("liste.nach_unten")}
          </Menu.Item>
          <Menu.Item leftSection={<Pencil aria-hidden />} onClick={() => setFrage("umbenennen")}>
            {t("liste.umbenennen")}
          </Menu.Item>
          <Menu.Item
            color="red"
            leftSection={<Trash2 aria-hidden />}
            onClick={() => {
              loeschen.reset();
              setFrage("loeschen");
            }}
          >
            {t("liste.loeschen")}
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
      {frage === "umbenennen" && (
        <NameDialog
          titel={t("liste.umbenennen_titel")}
          start={anzeige.name}
          speichern={(name) => anzeigeAendern(anzeige.id, { name })}
          onFertig={() => setFrage(null)}
        />
      )}
      <Bestaetigung
        offen={frage === "loeschen"}
        titel={t("liste.loeschen_titel", { name: anzeige.name })}
        text={anzeige.device_id ? t("liste.loeschen_text_geraet") : t("liste.loeschen_text")}
        bestaetigen={t("liste.loeschen")}
        abbrechen={t("aktion.abbrechen")}
        ton="gefahr"
        laedt={loeschen.isPending}
        fehler={loeschFehler}
        onSchliessen={() => setFrage(null)}
        onBestaetigen={() => loeschen.mutate()}
      />
    </>
  );
}

function NameDialog({
  titel,
  start,
  speichern,
  onFertig,
}: {
  titel: string;
  start: string;
  speichern: (name: string) => Promise<Anzeige>;
  onFertig: (neu?: Anzeige) => void;
}) {
  const { t } = useTranslation("anzeige");
  const queryClient = useQueryClient();
  const fehlerText = useFehlerText();
  const [name, setName] = useState(start);
  const senden = useMutation({
    mutationFn: speichern,
    onSuccess: (neu) => {
      void queryClient.invalidateQueries({ queryKey: anzeigeSchluessel.alle });
      onFertig(neu);
    },
  });
  const feldFehler =
    senden.error instanceof ApiFehler
      ? senden.error.felder.find((f) => f.feld === "name")?.meldung
      : undefined;
  const abschicken = (ereignis: FormEvent) => {
    ereignis.preventDefault();
    if (name.trim()) senden.mutate(name.trim());
  };

  return (
    <Dialog onClose={() => onFertig()} title={titel} centered>
      <form onSubmit={abschicken} style={{ display: "grid", gap: 16 }}>
        <TextInput
          label={t("liste.name")}
          value={name}
          maxLength={80}
          required
          data-autofocus
          onChange={(ereignis) => setName(ereignis.currentTarget.value)}
          error={feldFehler ?? (senden.isError ? fehlerText(senden.error) : undefined)}
        />
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="default" onClick={() => onFertig()} disabled={senden.isPending}>
            {t("aktion.abbrechen")}
          </Button>
          <Button type="submit" loading={senden.isPending} disabled={!name.trim()}>
            {t("aktion.speichern")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
