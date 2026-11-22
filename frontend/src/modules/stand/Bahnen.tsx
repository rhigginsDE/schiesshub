import { Button, Menu } from "@mantine/core";
import { Link } from "@tanstack/react-router";
import { Ban, ChevronDown, Clock, LogOut, PencilLine, PlayCircle, Undo2 } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../app/berechtigungen";
import { Chip } from "../../components/Chip";
import { formatUhrzeit } from "../../lib/format";
import { ABBRUCHGRUENDE, type Abbruchgrund, type Bahn, type StationStart } from "../anmeldung/api";
import { ERFASSUNG_PFAD } from "../erfassung/pfade";
import { type StandRechte, useAnzeigename } from "./aktionen";
import s from "./stand.module.css";
import { type Kennziffern, WettbewerbName } from "./Wettbewerb";

interface BahnKachelProps {
  bahn: Bahn;
  /** Planung des Wettbewerbs des Starts auf der Bahn */
  planung: "queue" | "schedule" | null;
  /** „Nächsten auf Bahn n“; fehlt, wenn niemand aufrufbar ist */
  onNaechsten?: () => void;
  onZurueck: (start: StationStart, position: "front" | "back") => void;
  onAbbrechen: (start: StationStart, grund: Abbruchgrund) => void;
  /** „Bahn freigeben“ (Rückfrage stellt der Aufrufer): Start mit angefangenem Ergebnis */
  onFreigeben: (start: StationStart) => void;
  beschaeftigt: boolean;
  /** Was die Person am Stand darf (Knöpfe ohne Recht fehlen) */
  rechte: StandRechte;
  kennziffern: Kennziffern;
}

/** Eine Bahn als große Kachel: frei oder belegt mit Startnummer, Name, Wettbewerb und seit wann. */
export function BahnKachel({
  bahn,
  planung,
  onNaechsten,
  onZurueck,
  onAbbrechen,
  onFreigeben,
  beschaeftigt,
  rechte,
  kennziffern,
}: BahnKachelProps) {
  const { t, i18n } = useTranslation("stand");
  const anzeigename = useAnzeigename();
  const darfErfassen = useDarf(["result.capture", "result.read"]);
  const start = bahn.start;
  const name = start ? anzeigename(start) : null;
  // Ein angefangenes Ergebnis hält die Bahn bis zum Abschließen; Zurückstellen geht dann nicht mehr.
  const inErfassung = start?.status === "captured";
  const fortschritt = bahn.progress ?? null;
  const titelId = `bahn-${bahn.lane}-titel`;

  let zeit: ReactNode = null;
  if (start?.heat_number != null && start.heat_starts_at) {
    zeit = t("bahn.durchgang", {
      nummer: start.heat_number,
      zeit: formatUhrzeit(new Date(start.heat_starts_at), i18n.language),
    });
  } else if (start?.called_at) {
    // Aufrufzeit vom Server: gleich auf jedem Gerät und auch nach dem Neuladen.
    zeit = t("bahn.seit", { zeit: formatUhrzeit(new Date(start.called_at), i18n.language) });
  }

  return (
    <li className={s.bahn} data-belegt={start ? "ja" : "nein"} aria-labelledby={titelId}>
      <div className={s.bahnKopf}>
        <h3 className={s.bahnTitel} id={titelId}>
          {t("bahn.titel", { bahn: bahn.lane })}
        </h3>
        <Chip ton={start ? "gruen" : "neutral"} punkt={Boolean(start)}>
          {start ? (inErfassung ? t("bahn.in_erfassung") : t("bahn.belegt")) : t("bahn.frei")}
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
              <strong data-ohne-name={name?.ohne || undefined}>{name?.text}</strong>
              {start.club && <span className="gedaempft">{start.club}</span>}
            </span>
          </div>
          <p className={s.bahnWas}>
            <WettbewerbName
              code={kennziffern.get(start.competition_id)}
              name={start.competition_name}
            />
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
          {fortschritt && fortschritt.series_total > 0 && (
            <div className={s.bahnFortschritt} data-fertig={fortschritt.complete || undefined}>
              <span className="num">
                {fortschritt.complete
                  ? t("bahn.fortschritt_fertig")
                  : t("bahn.fortschritt", {
                      erfasst: fortschritt.series_done,
                      gesamt: fortschritt.series_total,
                    })}
              </span>
              <progress
                className={s.bahnBalken}
                value={Math.min(fortschritt.series_done, fortschritt.series_total)}
                max={fortschritt.series_total}
                aria-hidden
              />
            </div>
          )}
          <div className={s.bahnAktionen}>
            {darfErfassen && (
              <Button
                renderRoot={(props) => (
                  <Link {...props} to={ERFASSUNG_PFAD} search={{ start: start.start_id }} />
                )}
                variant="default"
                size="md"
                leftSection={<PencilLine aria-hidden />}
              >
                {t("bahn.ergebnis")}
              </Button>
            )}
            {!rechte.aufrufen ? null : inErfassung ? (
              <Button
                variant="default"
                size="md"
                leftSection={<LogOut aria-hidden />}
                disabled={beschaeftigt}
                onClick={() => onFreigeben(start)}
              >
                {t("bahn.freigeben")}
              </Button>
            ) : planung === "schedule" ? (
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
            {rechte.abbrechen && (
              <AbbruchMenue disabled={beschaeftigt} onWahl={(grund) => onAbbrechen(start, grund)} />
            )}
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
