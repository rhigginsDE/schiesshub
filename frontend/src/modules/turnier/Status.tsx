import { Button, Menu } from "@mantine/core";
import {
  ChevronDown,
  CircleCheck,
  CirclePlay,
  PencilLine,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../app/berechtigungen";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Chip, type ChipTon } from "../../components/Chip";
import { useStatusWechseln } from "./abfragen";
import { fehlerText } from "./fehlertext";
import s from "./turnier.module.css";
import type { Turnier, TurnierStatus } from "./typen";

/** Berechtigung zum Zurückstufen (Backend: `tournament.reopen`). */
export const RECHT_WIEDEROEFFNEN = "tournament.reopen";

const TON: Record<TurnierStatus, ChipTon> = { draft: "warn", active: "gruen", closed: "neutral" };
const SYMBOL = { draft: PencilLine, active: CirclePlay, closed: CircleCheck } as const;

export function StatusChip({ status }: { status: TurnierStatus }) {
  const { t } = useTranslation("turnier");
  return (
    <Chip ton={TON[status]} icon={SYMBOL[status]}>
      {t(`status.${status}`)}
    </Chip>
  );
}

interface Wechsel {
  ziel: TurnierStatus;
  /** Schlüssel unter `status_wechsel.*` */
  art: "starten" | "abschliessen" | "entwurf" | "wieder_oeffnen";
  zurueck: boolean;
}

/** Mögliche Wechsel: nur schrittweise; zurück nur mit Recht. */
export function moeglicheWechsel(status: TurnierStatus, darfZurueck: boolean): Wechsel[] {
  const liste: Wechsel[] = [];
  if (status === "draft") liste.push({ ziel: "active", art: "starten", zurueck: false });
  if (status === "active") {
    liste.push({ ziel: "closed", art: "abschliessen", zurueck: false });
    if (darfZurueck) liste.push({ ziel: "draft", art: "entwurf", zurueck: true });
  }
  if (status === "closed" && darfZurueck) {
    liste.push({ ziel: "active", art: "wieder_oeffnen", zurueck: true });
  }
  return liste;
}

interface StatusAktionenProps {
  turnier: Turnier;
  /** `menue`: ein Knopf „Status ändern“ mit Auswahl (Liste); `knoepfe`: einzelne Knöpfe */
  darstellung: "menue" | "knoepfe";
  /** Der Wechsel „Turnier starten“ ist hier die Hauptaktion (grün) */
  startenPrimaer?: boolean;
  /** Hinweise, die vor dem Start in der Rückfrage stehen (offene Punkte) */
  hinweiseVorStart?: string[];
}

/** Statuswechsel mit Rückfrage. */
export function StatusAktionen({
  turnier,
  darstellung,
  startenPrimaer,
  hinweiseVorStart = [],
}: StatusAktionenProps) {
  const { t } = useTranslation("turnier");
  const wechseln = useStatusWechseln();
  const [gewaehlt, setGewaehlt] = useState<Wechsel | null>(null);
  const darfWechseln = useDarf("tournament.edit");
  const darfZurueck = useDarf(RECHT_WIEDEROEFFNEN);
  const wechsel = darfWechseln ? moeglicheWechsel(turnier.status, darfZurueck) : [];
  if (wechsel.length === 0) return null;

  const oeffnen = (eintrag: Wechsel) => {
    wechseln.reset();
    setGewaehlt(eintrag);
  };

  return (
    <>
      {darstellung === "menue" ? (
        <Menu position="bottom-end" withinPortal>
          <Menu.Target>
            <Button variant="default" rightSection={<ChevronDown aria-hidden />}>
              {t("status_wechsel.menue")}
            </Button>
          </Menu.Target>
          <Menu.Dropdown>
            {wechsel.map((eintrag) => (
              <Menu.Item
                key={eintrag.art}
                leftSection={
                  eintrag.zurueck ? <RotateCcw aria-hidden /> : <CirclePlay aria-hidden />
                }
                onClick={() => oeffnen(eintrag)}
              >
                {t(`status_wechsel.${eintrag.art}.knopf`)}
              </Menu.Item>
            ))}
          </Menu.Dropdown>
        </Menu>
      ) : (
        <div className={s.knopfReihe}>
          {wechsel.map((eintrag) => (
            <Button
              key={eintrag.art}
              variant={startenPrimaer && eintrag.art === "starten" ? "filled" : "default"}
              size="md"
              leftSection={eintrag.zurueck ? <RotateCcw aria-hidden /> : <CirclePlay aria-hidden />}
              onClick={() => oeffnen(eintrag)}
            >
              {t(`status_wechsel.${eintrag.art}.knopf`)}
            </Button>
          ))}
        </div>
      )}

      <Bestaetigung
        offen={gewaehlt !== null}
        titel={gewaehlt ? t(`status_wechsel.${gewaehlt.art}.titel`, { name: turnier.name }) : ""}
        text={
          gewaehlt && (
            <>
              <p>{t(`status_wechsel.${gewaehlt.art}.text`)}</p>
              {gewaehlt.art === "starten" && hinweiseVorStart.length > 0 && (
                <div className={s.warnKasten}>
                  <TriangleAlert aria-hidden />
                  <div>
                    <strong>{t("status_wechsel.starten.offen")}</strong>
                    <ul className={s.punktListe}>
                      {hinweiseVorStart.map((hinweis) => (
                        <li key={hinweis}>{hinweis}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </>
          )
        }
        bestaetigen={gewaehlt ? t(`status_wechsel.${gewaehlt.art}.knopf`) : ""}
        abbrechen={t("aktion.abbrechen")}
        ton={gewaehlt?.zurueck ? "gefahr" : "normal"}
        laedt={wechseln.isPending}
        fehler={wechseln.isError ? fehlerText(wechseln.error) : undefined}
        onSchliessen={() => setGewaehlt(null)}
        onBestaetigen={() => {
          if (!gewaehlt) return;
          wechseln.mutate(
            { id: turnier.id, status: gewaehlt.ziel },
            { onSuccess: () => setGewaehlt(null) },
          );
        }}
      />
    </>
  );
}
