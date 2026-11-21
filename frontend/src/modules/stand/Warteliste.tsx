import { ActionIcon, Button, Menu } from "@mantine/core";
import { ChevronDown, ChevronsUp, MoreVertical, PlayCircle, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Chip } from "../../components/Chip";
import { ReihenfolgeKnoepfe } from "../../components/Reihenfolge";
import { Leerzustand } from "../../components/Zustand";
import { ABBRUCHGRUENDE, type Abbruchgrund, type Bahn, type StationStart } from "../anmeldung/api";
import { useAnzeigename } from "./aktionen";
import { besetzteAnmeldungen, freieBahnen } from "./logik";
import s from "./stand.module.css";

interface WartelisteProps {
  wartende: readonly StationStart[];
  bahnen: readonly Bahn[];
  beschaeftigt: boolean;
  onVerschieben: (
    start: StationStart,
    wohin: { direction: "up" | "down" } | { position: number },
  ) => void;
  onAufrufen: (start: StationStart, bahn: number) => void;
  onAbbrechen: (start: StationStart, grund: Abbruchgrund) => void;
}

/** „Als Nächstes“: die wartenden Starts der Reihenfolge, umsortierbar und einzeln aufrufbar. */
export function Warteliste({
  wartende,
  bahnen,
  beschaeftigt,
  onVerschieben,
  onAufrufen,
  onAbbrechen,
}: WartelisteProps) {
  const { t } = useTranslation("stand");
  const anzeigename = useAnzeigename();
  const frei = freieBahnen(bahnen);
  const besetzt = besetzteAnmeldungen(bahnen);
  const bahnVon = (entryId: string) => bahnen.find((b) => b.start?.entry_id === entryId)?.lane;

  if (wartende.length === 0) {
    return <Leerzustand icon={Users} titel={t("warten.leer_titel")} text={t("warten.leer_text")} />;
  }

  return (
    <ol className={s.warteliste}>
      {wartende.map((start, index) => {
        const nr = start.start_number;
        const steht = besetzt.has(start.entry_id) ? bahnVon(start.entry_id) : undefined;
        return (
          <li key={start.start_id} className={s.warteZeile}>
            <span className={`num ${s.wartePlatz}`}>
              <span className="nur-screenreader">{t("warten.position", { nr: index + 1 })}</span>
              <span aria-hidden>{index + 1}</span>
            </span>
            <span className={`num ${s.warteNummer}`}>{nr}</span>
            <span className={s.warteWer}>
              <strong data-ohne-name={start.display_name === null || undefined}>
                {anzeigename(start)}
              </strong>
              <span className="gedaempft">
                {start.competition_name} · {start.class_short} ·{" "}
                {t("bahn.start_nr", { nr: start.attempt })}
              </span>
              {steht !== undefined && (
                <Chip ton="info">{t("warten.schon_am_stand", { bahn: steht })}</Chip>
              )}
            </span>
            <span className={s.warteAktionen}>
              <ReihenfolgeKnoepfe
                index={index}
                anzahl={wartende.length}
                hoch={t("warten.hoch", { nr })}
                runter={t("warten.runter", { nr })}
                gesperrt={beschaeftigt}
                onVerschieben={(richtung) =>
                  onVerschieben(start, { direction: richtung < 0 ? "up" : "down" })
                }
              />
              <ActionIcon
                variant="subtle"
                color="gray"
                size={40}
                aria-label={t("warten.anfang", { nr })}
                title={t("warten.anfang", { nr })}
                disabled={beschaeftigt || index === 0}
                onClick={() => onVerschieben(start, { position: 1 })}
              >
                <ChevronsUp aria-hidden />
              </ActionIcon>
              <Menu position="bottom-end" withinPortal>
                <Menu.Target>
                  <Button
                    variant="default"
                    size="sm"
                    h={40}
                    leftSection={<PlayCircle aria-hidden />}
                    rightSection={<ChevronDown aria-hidden />}
                    disabled={beschaeftigt || frei.length === 0 || steht !== undefined}
                    aria-label={t("warten.aufrufen_lang", { nr })}
                    title={
                      steht !== undefined
                        ? t("warten.schon_am_stand", { bahn: steht })
                        : frei.length === 0
                          ? t("warten.keine_bahn_frei")
                          : undefined
                    }
                  >
                    {t("warten.aufrufen")}
                  </Button>
                </Menu.Target>
                <Menu.Dropdown>
                  {frei.map((bahn) => (
                    <Menu.Item key={bahn} onClick={() => onAufrufen(start, bahn)}>
                      {t("warten.auf_bahn", { bahn })}
                    </Menu.Item>
                  ))}
                </Menu.Dropdown>
              </Menu>
              <Menu position="bottom-end" withinPortal>
                <Menu.Target>
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    size={40}
                    aria-label={t("warten.mehr", { nr })}
                    title={t("warten.mehr", { nr })}
                    disabled={beschaeftigt}
                  >
                    <MoreVertical aria-hidden />
                  </ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Label>{t("bahn.abbrechen")}</Menu.Label>
                  {ABBRUCHGRUENDE.map((grund) => (
                    <Menu.Item key={grund} onClick={() => onAbbrechen(start, grund)}>
                      {t(`abbruch.grund.${grund}`)}
                    </Menu.Item>
                  ))}
                </Menu.Dropdown>
              </Menu>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
