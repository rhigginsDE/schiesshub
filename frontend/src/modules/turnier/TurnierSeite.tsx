import { ActionIcon, Button, Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { CalendarPlus, Copy, type LucideIcon, Trash2, Trophy } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDarf } from "../../app/berechtigungen";
import { useBereiche } from "../../app/modul";
import { Bestaetigung } from "../../components/Bestaetigung";
import { Kachel, KachelRaster } from "../../components/Kachel";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { turnierListeAbfrage, useTurnierLoeschen } from "./abfragen";
import { fehlerText } from "./fehlertext";
import { zeitraum } from "./klartext";
import { EINRICHTEN_PFAD } from "./pfade";
import { StatusAktionen, StatusChip } from "./Status";
import { TurnierAnlegen } from "./TurnierAnlegen";
import s from "./turnier.module.css";
import type { Turnier } from "./typen";
import { UebungChip, UebungLoeschen, UebungStarten } from "./Uebung";
import v from "./vorlagen.module.css";

interface TurnierSeiteProps {
  station: string;
  icon: LucideIcon;
}

/** Station Turnier: vorhandene Turniere, neues Turnier anlegen, Bereiche wie der Katalog. */
export function TurnierSeite({ station, icon: Icon }: TurnierSeiteProps) {
  const { t } = useTranslation();
  const bereiche = useBereiche(station);
  const turniere = useQuery(turnierListeAbfrage());
  const [anlegen, setAnlegen] = useState(false);
  const darfBearbeiten = useDarf("tournament.edit");

  return (
    <div className={s.listenSeite}>
      <section className={`panel ${s.kopf}`}>
        <div className={s.kopfZeile}>
          <div className={s.titel}>
            <span className={s.symbol}>
              <Icon aria-hidden />
            </span>
            <div>
              <h1 className="h-display">{t("turnier:titel")}</h1>
              <p className={s.zweck}>{t("turnier:zweck")}</p>
            </div>
          </div>
          {darfBearbeiten && (
            <Button
              size="md"
              leftSection={<CalendarPlus aria-hidden />}
              onClick={() => setAnlegen(true)}
            >
              {t("turnier:liste.anlegen")}
            </Button>
          )}
        </div>
      </section>

      <section className="panel" aria-labelledby="turnier-liste">
        <div className="panel-kopf">
          <h2 className="h-section" id="turnier-liste">
            {t("turnier:liste.titel")}
          </h2>
        </div>
        {turniere.isPending ? (
          <div className={s.skelett} aria-busy="true">
            {[0, 1, 2].map((nr) => (
              <Skeleton key={nr} height={64} radius="md" />
            ))}
          </div>
        ) : turniere.isError ? (
          <Fehlerzustand fehler={turniere.error} onErneut={() => void turniere.refetch()} />
        ) : turniere.data.length === 0 ? (
          <Leerzustand
            icon={Trophy}
            titel={t("turnier:liste.leer_titel")}
            text={t("turnier:liste.leer_text")}
          >
            <UebungStarten />
          </Leerzustand>
        ) : (
          <ul className={s.turnierListe}>
            {turniere.data.map((turnier) => (
              <TurnierZeile key={turnier.id} turnier={turnier} />
            ))}
          </ul>
        )}
      </section>

      {bereiche.length > 0 && (
        <section className={s.bereiche} aria-labelledby="turnier-bereiche">
          <h2 className="h-label" id="turnier-bereiche">
            {t("turnier:bereiche")}
          </h2>
          <KachelRaster>
            {bereiche.map((modul) => (
              <Kachel
                key={modul.id}
                pfad={modul.navigation.pfad}
                icon={modul.navigation.icon}
                titel={t(`${modul.namensraum}:titel`)}
                text={t(`${modul.namensraum}:zweck`)}
              />
            ))}
          </KachelRaster>
        </section>
      )}

      {anlegen && <TurnierAnlegen offen onSchliessen={() => setAnlegen(false)} />}
    </div>
  );
}

function TurnierZeile({ turnier }: { turnier: Turnier }) {
  const { t, i18n } = useTranslation("turnier");
  const navigate = useNavigate();
  const loeschen = useTurnierLoeschen();
  const darfBearbeiten = useDarf("tournament.edit");
  const [frage, setFrage] = useState(false);
  const [kopieren, setKopieren] = useState(false);
  const uebung = turnier.is_practice;

  return (
    <li className={s.turnierZeile}>
      <div className={s.turnierText}>
        <Link
          to={EINRICHTEN_PFAD}
          params={{ turnierId: turnier.id }}
          search={{}}
          className={s.turnierName}
        >
          {turnier.name}
        </Link>
        <span className="gedaempft">
          <span className="num">{zeitraum(turnier, i18n.language)}</span>
          {turnier.organizer && ` · ${turnier.organizer}`}
          {` · ${t(`vorlage.${turnier.template}.name`)}`}
        </span>
      </div>
      <span className={v.chips}>
        <StatusChip status={turnier.status} />
        {uebung && <UebungChip />}
      </span>
      <div className={s.zeilenAktionen}>
        <Button
          variant="default"
          onClick={() =>
            void navigate({ to: EINRICHTEN_PFAD, params: { turnierId: turnier.id }, search: {} })
          }
        >
          {t("liste.oeffnen")}
        </Button>
        {darfBearbeiten && (
          <Button
            variant="default"
            leftSection={<Copy aria-hidden />}
            aria-label={t("liste.kopieren_lang", { name: turnier.name })}
            title={t("liste.kopieren_lang", { name: turnier.name })}
            onClick={() => setKopieren(true)}
          >
            {t("liste.kopieren")}
          </Button>
        )}
        <StatusAktionen turnier={turnier} darstellung="menue" />
        {(turnier.status === "draft" || uebung) && darfBearbeiten && (
          <ActionIcon
            variant="subtle"
            color="gray"
            size={40}
            aria-label={t("liste.loeschen", { name: turnier.name })}
            title={t("liste.loeschen", { name: turnier.name })}
            onClick={() => {
              loeschen.reset();
              setFrage(true);
            }}
          >
            <Trash2 aria-hidden />
          </ActionIcon>
        )}
      </div>
      {kopieren && (
        <TurnierAnlegen offen vorbild={turnier.id} onSchliessen={() => setKopieren(false)} />
      )}
      {uebung ? (
        <UebungLoeschen turnierId={turnier.id} offen={frage} onSchliessen={() => setFrage(false)} />
      ) : (
        <Bestaetigung
          offen={frage}
          titel={t("liste.loeschen_titel", { name: turnier.name })}
          text={<p>{t("liste.loeschen_text")}</p>}
          bestaetigen={t("liste.loeschen_knopf")}
          abbrechen={t("aktion.abbrechen")}
          ton="gefahr"
          laedt={loeschen.isPending}
          fehler={loeschen.isError ? fehlerText(loeschen.error) : undefined}
          onSchliessen={() => setFrage(false)}
          onBestaetigen={() => loeschen.mutate(turnier.id, { onSuccess: () => setFrage(false) })}
        />
      )}
    </li>
  );
}
