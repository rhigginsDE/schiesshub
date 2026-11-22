import { Button } from "@mantine/core";
import { useBlocker } from "@tanstack/react-router";
import { CircleAlert, Save, Trash2 } from "lucide-react";
import { useState, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "./Dialog";
import a from "./EntwurfSchutz.module.css";
import type { EntwurfRegister } from "./useEntwurf";

/** Ob im Register etwas ungespeichert ist; rendert bei jeder Änderung neu. */
export function useUngespeichert(register: EntwurfRegister): boolean {
  return useSyncExternalStore(register.abonniere, register.geaendert, register.geaendert);
}

/**
 * Fragt nach, bevor ungespeicherte Änderungen verloren gehen („Speichern / Verwerfen / Weiter
 * bearbeiten“): beim Wechsel der Seite oder des Bereichs (Adresse oder Suchteil ändert sich) und
 * beim Schließen des Fensters. `ort` nennt, wo geändert wurde („Startgeld und Vorgaben“).
 */
export function EntwurfSchutz({ register, ort }: { register: EntwurfRegister; ort: string }) {
  const { t } = useTranslation("shell");
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState(false);
  const blocker = useBlocker({
    shouldBlockFn: ({ current, next }) =>
      register.geaendert() &&
      (current.pathname !== next.pathname ||
        JSON.stringify(current.search) !== JSON.stringify(next.search)),
    enableBeforeUnload: () => register.geaendert(),
    withResolver: true,
  });
  const offen = blocker.status === "blocked";
  const speicherbar = offen && register.speicherbar();

  const schliessen = () => {
    setFehler(false);
    blocker.reset?.();
  };

  return (
    <Dialog opened={offen} onClose={schliessen} title={t("entwurf.titel")} centered size="lg">
      <div className={a.rueckfrage}>
        <p>{t(speicherbar ? "entwurf.text" : "entwurf.text_ohne_speichern", { ort })}</p>
        {fehler && (
          <p role="alert" className={a.fehler}>
            <CircleAlert aria-hidden />
            {t("entwurf.fehler")}
          </p>
        )}
        <div className={a.knoepfe}>
          <Button variant="default" onClick={schliessen} disabled={laedt} data-autofocus>
            {t("entwurf.weiter_bearbeiten")}
          </Button>
          <Button
            variant="default"
            color="red"
            leftSection={<Trash2 aria-hidden />}
            disabled={laedt}
            onClick={() => {
              register.verwerfen();
              setFehler(false);
              blocker.proceed?.();
            }}
          >
            {t("entwurf.verwerfen")}
          </Button>
          {speicherbar && (
            <Button
              leftSection={<Save aria-hidden />}
              loading={laedt}
              onClick={async () => {
                setLaedt(true);
                const ok = await register.speichern();
                setLaedt(false);
                if (ok) {
                  setFehler(false);
                  blocker.proceed?.();
                } else {
                  // Fehler stehen am Formular; dort weiterarbeiten.
                  setFehler(true);
                }
              }}
            >
              {t("entwurf.speichern")}
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  );
}
