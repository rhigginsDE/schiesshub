import { Button, Menu } from "@mantine/core";
import { Ban, ChevronDown, Clock, PlayCircle, Undo2 } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Chip } from "../../components/Chip";
import { formatUhrzeit } from "../../lib/format";
import { ABBRUCHGRUENDE, type Abbruchgrund, type Bahn, type StationStart } from "../anmeldung/api";
import { useAnzeigename } from "./aktionen";
import s from "./stand.module.css";

/**
 * Stelle für „Ergebnis erfassen“ an der Bahnkachel. Kommt mit dem Ergebnis-Modul: dann liefert
 * diese Funktion den Pfad zur Eingabe des aufgerufenen Starts. Solange sie `null` ist, zeigt die
 * Kachel keinen Link.
 */
export const ERGEBNIS_ERFASSEN_PFAD: ((start: StationStart) => string) | null = null;

/**
 * Wann ein Start auf die Bahn kam. Der Server liefert dafür (noch) keinen Zeitpunkt; die Seite
 * merkt sich deshalb, wann sie einen Aufruf selbst gesehen hat. Was schon beim Laden auf der Bahn
 * stand, bleibt ohne Zeit (`null`), statt eine falsche Uhrzeit zu zeigen.
 */
export function useAufrufZeiten(
  bahnen: readonly Bahn[] | undefined,
): ReadonlyMap<string, Date | null> {
  const zeiten = useRef(new Map<string, Date | null>());
  const erstesMal = useRef(true);
  const [, setStand] = useState(0);

  useEffect(() => {
    if (!bahnen) return;
    const karte = zeiten.current;
    let neu = false;
    for (const bahn of bahnen) {
      if (bahn.start && !karte.has(bahn.start.start_id)) {
        karte.set(bahn.start.start_id, erstesMal.current ? null : new Date());
        neu = true;
      }
    }
    erstesMal.current = false;
    if (neu) setStand((n) => n + 1);
  }, [bahnen]);

  return zeiten.current;
}

interface BahnKachelProps {
  bahn: Bahn;
  /** Planung des Wettbewerbs des Starts auf der Bahn */
  planung: "queue" | "schedule" | null;
  seit: Date | null | undefined;
  /** „Nächsten auf Bahn n“; fehlt, wenn niemand aufrufbar ist */
  onNaechsten?: () => void;
  onZurueck: (start: StationStart, position: "front" | "back") => void;
  onAbbrechen: (start: StationStart, grund: Abbruchgrund) => void;
  beschaeftigt: boolean;
}

/** Eine Bahn als große Kachel: frei oder belegt mit Startnummer, Name, Wettbewerb und seit wann. */
export function BahnKachel({
  bahn,
  planung,
  seit,
  onNaechsten,
  onZurueck,
  onAbbrechen,
  beschaeftigt,
}: BahnKachelProps) {
  const { t, i18n } = useTranslation("stand");
  const anzeigename = useAnzeigename();
  const start = bahn.start;
  const titelId = `bahn-${bahn.lane}-titel`;

  let zeit: ReactNode = null;
  if (start?.heat_number != null && start.heat_starts_at) {
    zeit = t("bahn.durchgang", {
      nummer: start.heat_number,
      zeit: formatUhrzeit(new Date(start.heat_starts_at), i18n.language),
    });
  } else if (seit) {
    zeit = t("bahn.seit", { zeit: formatUhrzeit(seit, i18n.language) });
  }

  return (
    <li className={s.bahn} data-belegt={start ? "ja" : "nein"} aria-labelledby={titelId}>
      <div className={s.bahnKopf}>
        <h3 className={s.bahnTitel} id={titelId}>
          {t("bahn.titel", { bahn: bahn.lane })}
        </h3>
        <Chip ton={start ? "gruen" : "neutral"} punkt={Boolean(start)}>
          {start ? t("bahn.belegt") : t("bahn.frei")}
        </Chip>
      </div>

      {start ? (
        <>
          <div className={s.bahnStart}>
            <span className={`num ${s.bahnNummer}`}>
              <span className="nur-screenreader">{t("bahn.startnummer")} </span>
              {start.start_number}
            </span>
            <span className={s.bahnWer}>
              <strong data-ohne-name={start.display_name === null || undefined}>
                {anzeigename(start)}
              </strong>
              {start.club && <span className="gedaempft">{start.club}</span>}
            </span>
          </div>
          <p className={s.bahnWas}>
            <span>{start.competition_name}</span>
            <span className="gedaempft">
              {start.class_short} · {t("bahn.start_nr", { nr: start.attempt })}
            </span>
          </p>
          {zeit && (
            <p className={`gedaempft ${s.bahnZeit}`}>
              <Clock aria-hidden />
              <span className="num">{zeit}</span>
            </p>
          )}
          <div className={s.bahnAktionen}>
            {/* „Ergebnis erfassen“: erscheint, sobald ERGEBNIS_ERFASSEN_PFAD gesetzt ist. */}
            {ERGEBNIS_ERFASSEN_PFAD && (
              <Button
                component="a"
                href={ERGEBNIS_ERFASSEN_PFAD(start)}
                variant="default"
                size="md"
              >
                {t("bahn.ergebnis")}
              </Button>
            )}
            {planung === "schedule" ? (
              <Button
                variant="default"
                size="md"
                leftSection={<Undo2 aria-hidden />}
                disabled={beschaeftigt}
                title={t("bahn.zurueck_zeitplan")}
                onClick={() => onZurueck(start, "back")}
              >
                {t("bahn.zurueck")}
              </Button>
            ) : (
              <Menu position="bottom-start" withinPortal>
                <Menu.Target>
                  <Button
                    variant="default"
                    size="md"
                    leftSection={<Undo2 aria-hidden />}
                    rightSection={<ChevronDown aria-hidden />}
                    disabled={beschaeftigt}
                  >
                    {t("bahn.zurueck")}
                  </Button>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item onClick={() => onZurueck(start, "front")}>
                    {t("bahn.zurueck_vorn")}
                  </Menu.Item>
                  <Menu.Item onClick={() => onZurueck(start, "back")}>
                    {t("bahn.zurueck_hinten")}
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            )}
            <AbbruchMenue disabled={beschaeftigt} onWahl={(grund) => onAbbrechen(start, grund)} />
          </div>
        </>
      ) : (
        <div className={s.bahnFrei}>
          {!onNaechsten && <span className="gedaempft">{t("bahn.frei_text")}</span>}
          {onNaechsten && (
            <Button
              variant="default"
              size="md"
              leftSection={<PlayCircle aria-hidden />}
              disabled={beschaeftigt}
              onClick={onNaechsten}
            >
              {t("bahn.naechsten", { bahn: bahn.lane })}
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

interface AbbruchMenueProps {
  disabled?: boolean;
  onWahl: (grund: Abbruchgrund) => void;
  /** Nur als Symbol (in Listen) statt mit Beschriftung */
  kompakt?: ReactNode;
}

/** Menü „Abbrechen“ mit den drei Gründen; die Rückfrage stellt der Aufrufer. */
export function AbbruchMenue({ disabled, onWahl, kompakt }: AbbruchMenueProps) {
  const { t } = useTranslation("stand");
  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        {kompakt ?? (
          <Button
            variant="default"
            size="md"
            className={s.gefahr}
            leftSection={<Ban aria-hidden />}
            rightSection={<ChevronDown aria-hidden />}
            disabled={disabled}
          >
            {t("bahn.abbrechen")}
          </Button>
        )}
      </Menu.Target>
      <Menu.Dropdown>
        {ABBRUCHGRUENDE.map((grund) => (
          <Menu.Item key={grund} onClick={() => onWahl(grund)}>
            {t(`abbruch.grund.${grund}`)}
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}
