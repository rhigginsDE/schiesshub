import { ActionIcon, Button, Menu, Switch } from "@mantine/core";
import { CalendarClock, MoreVertical, PlayCircle, Plus } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { Chip } from "../../components/Chip";
import { Leerzustand } from "../../components/Zustand";
import { formatUhrzeit } from "../../lib/format";
import {
  ABBRUCHGRUENDE,
  type Abbruchgrund,
  type Durchgang,
  type StationStart,
} from "../anmeldung/api";
import { useAnzeigename } from "./aktionen";
import { belegungDurchgang, durchgangErledigt, sortiereDurchgaenge } from "./logik";
import s from "./stand.module.css";

interface ZeitplanProps {
  turnierId: string;
  durchgaenge: readonly Durchgang[];
  /** Starts der Zeitplan-Wettbewerbe dieses Stands */
  starts: readonly StationStart[];
  /** Durchgang, den die Hauptaktion aufruft (nicht doppelt als Knopf zeigen) */
  hauptDurchgangId: string | null;
  beschaeftigt: boolean;
  onSerie: () => void;
  onDurchgangAufrufen: (durchgang: Durchgang) => void;
  onDurchgangAendern: (durchgang: Durchgang) => void;
  onDurchgangLoeschen: (durchgang: Durchgang) => void;
  onPlatz: (start: StationStart) => void;
  onHerausnehmen: (start: StationStart) => void;
  onAufrufen: (start: StationStart) => void;
  onAbbrechen: (start: StationStart, grund: Abbruchgrund) => void;
}

/** Durchgänge des Stands mit Uhrzeit, Belegung je Bahn und den Aktionen der Standaufsicht. */
export function Zeitplan(props: ZeitplanProps) {
  const { t, i18n } = useTranslation("stand");
  const { durchgaenge, starts, beschaeftigt } = props;
  const [vergangene, setVergangene] = useState(false);
  const sortiert = sortiereDurchgaenge(durchgaenge);
  const erledigt = sortiert.filter((d) => durchgangErledigt(d, starts));
  const gezeigt = vergangene ? sortiert : sortiert.filter((d) => !erledigt.includes(d));
  const ohnePlatz = starts.filter((st) => st.status === "registered" && !st.heat_id);
  const uhr = (iso: string) => formatUhrzeit(new Date(iso), i18n.language);

  return (
    <div className={s.zeitplan}>
      <div className={s.abschnittWerkzeug}>
        <Button
          variant="default"
          size="md"
          leftSection={<Plus aria-hidden />}
          onClick={props.onSerie}
        >
          {t("zeitplan.serie")}
        </Button>
        {erledigt.length > 0 && (
          <Switch
            size="md"
            label={t("zeitplan.vergangene")}
            checked={vergangene}
            onChange={(e) => setVergangene(e.currentTarget.checked)}
          />
        )}
      </div>

      {ohnePlatz.length > 0 && (
        <section className={`inset ${s.ohnePlatz}`} aria-labelledby="ohne-platz-titel">
          <h3 className="h-label" id="ohne-platz-titel">
            {t("zeitplan.ohne_platz")}
          </h3>
          <p className="gedaempft">{t("zeitplan.ohne_platz_text")}</p>
          <ul className={s.ohnePlatzListe}>
            {ohnePlatz.map((start) => (
              <StartZeile key={start.start_id} start={start} turnierId={props.turnierId}>
                <Button
                  variant="default"
                  size="md"
                  disabled={beschaeftigt}
                  onClick={() => props.onPlatz(start)}
                >
                  {t("zeitplan.einplanen")}
                </Button>
              </StartZeile>
            ))}
          </ul>
        </section>
      )}

      {gezeigt.length === 0 ? (
        <Leerzustand
          icon={CalendarClock}
          titel={t("zeitplan.leer_titel")}
          text={t("zeitplan.leer_text")}
        />
      ) : (
        <ol className={s.durchgaenge}>
          {gezeigt.map((durchgang) => {
            const belegung = belegungDurchgang(durchgang, starts);
            const wartend = starts.some(
              (st) => st.heat_id === durchgang.id && st.status === "registered",
            );
            const vorbei = erledigt.includes(durchgang);
            const titelId = `durchgang-${durchgang.id}`;
            return (
              <li key={durchgang.id} className={s.durchgang} aria-labelledby={titelId}>
                <div className={s.durchgangKopf}>
                  <h3 className={s.durchgangTitel} id={titelId}>
                    <span className="num">
                      {t("zeitplan.zeit", {
                        von: uhr(durchgang.starts_at),
                        bis: uhr(durchgang.ends_at),
                      })}
                    </span>
                    <span className="gedaempft">
                      {t("zeitplan.durchgang", { nummer: durchgang.number })}
                    </span>
                  </h3>
                  <Chip ton={durchgang.booked >= durchgang.capacity ? "warn" : "neutral"}>
                    <span className="num">
                      {t("zeitplan.belegung", {
                        belegt: durchgang.booked,
                        kapazitaet: durchgang.capacity,
                      })}
                    </span>
                  </Chip>
                  {vorbei && <Chip ton="info">{t("zeitplan.vorbei")}</Chip>}
                  <span className={s.durchgangAktionen}>
                    {wartend && props.hauptDurchgangId !== durchgang.id && (
                      <Button
                        variant="default"
                        size="md"
                        leftSection={<PlayCircle aria-hidden />}
                        disabled={beschaeftigt}
                        onClick={() => props.onDurchgangAufrufen(durchgang)}
                      >
                        {t("aktion.durchgang_aufrufen_kurz")}
                      </Button>
                    )}
                    <Menu position="bottom-end" withinPortal>
                      <Menu.Target>
                        <ActionIcon
                          variant="subtle"
                          color="gray"
                          size={44}
                          aria-label={t("zeitplan.aktionen", { nummer: durchgang.number })}
                          title={t("zeitplan.aktionen", { nummer: durchgang.number })}
                        >
                          <MoreVertical aria-hidden />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item onClick={() => props.onDurchgangAendern(durchgang)}>
                          {t("zeitplan.aendern")}
                        </Menu.Item>
                        <Menu.Item color="red" onClick={() => props.onDurchgangLoeschen(durchgang)}>
                          {t("zeitplan.loeschen")}
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </span>
                </div>
                {belegung.every(({ start }) => start === null) ? (
                  <p className="gedaempft">
                    {t("zeitplan.alle_frei", { count: durchgang.capacity })}
                  </p>
                ) : (
                  <ul className={s.durchgangBahnen}>
                    {belegung.map(({ bahn, start }) => (
                      <li key={bahn} className={s.platz} data-frei={start ? undefined : "ja"}>
                        <span className={`num ${s.platzBahn}`}>{t("bahn.titel", { bahn })}</span>
                        {start ? (
                          <PlatzInhalt start={start} {...props} />
                        ) : (
                          <span className="gedaempft">{t("zeitplan.frei")}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function PlatzInhalt({
  turnierId,
  start,
  beschaeftigt,
  onPlatz,
  onHerausnehmen,
  onAufrufen,
  onAbbrechen,
}: { start: StationStart } & ZeitplanProps) {
  const { t } = useTranslation("stand");
  const anzeigename = useAnzeigename(turnierId);
  const nr = start.start_number;
  const wartet = start.status === "registered";
  return (
    <>
      <span className={s.platzWer}>
        <strong>
          <span className="num">{nr}</span> {anzeigename(start).text}
        </strong>
        <span className="gedaempft">
          {start.competition_name} · {t("bahn.start_nr", { nr: start.attempt })}
        </span>
      </span>
      {!wartet && (
        <Chip
          ton={start.status === "aborted" ? "krit" : start.status === "called" ? "gruen" : "info"}
        >
          {start.status === "aborted" && start.abort_reason
            ? t(`abbruch.grund.${start.abort_reason}`)
            : t(`status.${start.status}`)}
        </Chip>
      )}
      {wartet && (
        <Menu position="bottom-end" withinPortal>
          <Menu.Target>
            <ActionIcon
              variant="subtle"
              color="gray"
              size={44}
              disabled={beschaeftigt}
              aria-label={t("zeitplan.start_aktionen", { nr })}
              title={t("zeitplan.start_aktionen", { nr })}
            >
              <MoreVertical aria-hidden />
            </ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item onClick={() => onAufrufen(start)}>
              {t("zeitplan.einzeln_aufrufen")}
            </Menu.Item>
            <Menu.Item onClick={() => onPlatz(start)}>{t("zeitplan.umsetzen")}</Menu.Item>
            <Menu.Item onClick={() => onHerausnehmen(start)}>
              {t("zeitplan.herausnehmen")}
            </Menu.Item>
            <Menu.Divider />
            <Menu.Label>{t("bahn.abbrechen")}</Menu.Label>
            {ABBRUCHGRUENDE.map((grund) => (
              <Menu.Item key={grund} onClick={() => onAbbrechen(start, grund)}>
                {t(`abbruch.grund.${grund}`)}
              </Menu.Item>
            ))}
          </Menu.Dropdown>
        </Menu>
      )}
    </>
  );
}

function StartZeile({
  start,
  turnierId,
  children,
}: {
  start: StationStart;
  turnierId: string;
  children: ReactNode;
}) {
  const { t } = useTranslation("stand");
  const anzeigename = useAnzeigename(turnierId);
  return (
    <li className={s.platz}>
      <span className={`num ${s.platzBahn}`}>{start.start_number}</span>
      <span className={s.platzWer}>
        <strong>{anzeigename(start).text}</strong>
        <span className="gedaempft">
          {start.competition_name} · {t("bahn.start_nr", { nr: start.attempt })}
        </span>
      </span>
      {children}
    </li>
  );
}
