import { Button, Skeleton } from "@mantine/core";
import { Link } from "@tanstack/react-router";
import { ArrowRight, CalendarDays, Flag, Repeat, Trophy } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { formatDatum } from "../lib/format";
import type { Turnier } from "../modules/turnier/typen";
import { Chip, type ChipTon } from "./Chip";
import s from "./TurnierWahl.module.css";
import { type AktivesTurnier, useAktivesTurnier } from "./useAktivesTurnier";
import { Fehlerzustand, Leerzustand } from "./Zustand";

const STATUS_TON: Record<Turnier["status"], ChipTon> = {
  active: "gruen",
  draft: "neutral",
  closed: "info",
};

/** Statusmarke eines Turniers („Aktiv“, „Entwurf“, „Abgeschlossen“). */
export function TurnierStatusChip({ status }: { status: Turnier["status"] }) {
  const { t } = useTranslation("turnierwahl");
  return (
    <Chip ton={STATUS_TON[status]} punkt={status === "active"}>
      {t(`status.${status}`)}
    </Chip>
  );
}

function zeitraum(turnier: Turnier, sprache: string): string {
  const von = formatDatum(turnier.date_from, sprache);
  const bis = formatDatum(turnier.date_to, sprache);
  return von === bis ? von : `${von} – ${bis}`;
}

interface TurnierAuswahlProps {
  turniere: readonly Turnier[];
  aktivId?: string | null;
  onWahl: (id: string) => void;
  /** Zurück zum bisherigen Turnier (nur, wenn schon eins gewählt war) */
  onAbbrechen?: () => void;
  /** Wofür gewählt wird, z. B. „Die Anmeldung arbeitet in einem Turnier.“ */
  hinweis?: string;
}

/** Auswahl des Turniers für eine Station: aktive zuerst, große Ziele für Touch. */
export function TurnierAuswahl({
  turniere,
  aktivId,
  onWahl,
  onAbbrechen,
  hinweis,
}: TurnierAuswahlProps) {
  const { t, i18n } = useTranslation("turnierwahl");
  // Am Wettkampftag arbeiten die Stationen im gestarteten Turnier. Gibt es noch keins, sagt die
  // Auswahl, was als Nächstes zu tun ist, statt nur Entwürfe aufzulisten.
  const keinAktives = turniere.length > 0 && !turniere.some((x) => x.status === "active");
  const entwurf = turniere.find((x) => x.status === "draft");
  return (
    <section className={`panel ${s.auswahl}`} aria-labelledby="turnierwahl-titel">
      <div className="panel-kopf">
        <h2 className="h-section" id="turnierwahl-titel">
          {t("titel")}
        </h2>
        {onAbbrechen && (
          <Button variant="default" onClick={onAbbrechen}>
            {t("abbrechen")}
          </Button>
        )}
      </div>
      <p className="gedaempft">{hinweis ?? t("hinweis")}</p>
      {keinAktives && (
        <div className={s.nichtGestartet} role="note">
          <Flag aria-hidden className={s.nichtGestartetSymbol} />
          <div className={s.nichtGestartetText}>
            <strong>{t("nicht_gestartet_titel")}</strong>
            <span>{t("nicht_gestartet_text")}</span>
          </div>
          <Button
            renderRoot={(props) =>
              entwurf ? (
                <Link
                  {...props}
                  to={`/turnier/${entwurf.id}`}
                  search={{ bereich: "zusammenfassung" }}
                />
              ) : (
                <Link {...props} to="/turnier" />
              )
            }
            variant="default"
            rightSection={<ArrowRight aria-hidden />}
          >
            {t("nicht_gestartet_link")}
          </Button>
        </div>
      )}
      {turniere.length === 0 ? (
        <Leerzustand icon={Trophy} titel={t("leer_titel")} text={t("leer_text")}>
          <Button component={Link} to="/turnier" variant="default">
            {t("leer_link")}
          </Button>
        </Leerzustand>
      ) : (
        <ul className={s.liste}>
          {turniere.map((turnier, index) => (
            <li key={turnier.id}>
              <button
                type="button"
                className={s.eintrag}
                aria-current={turnier.id === aktivId ? "true" : undefined}
                onClick={() => onWahl(turnier.id)}
                // Erster Eintrag bekommt den Fokus, damit Enter sofort wählt.
                data-autofocus={index === 0 || undefined}
              >
                <span className={s.eintragText}>
                  <strong>{turnier.name}</strong>
                  <span className="gedaempft">
                    <CalendarDays aria-hidden />
                    <span className="num">{zeitraum(turnier, i18n.language)}</span>
                  </span>
                </span>
                <TurnierStatusChip status={turnier.status} />
                <ArrowRight className={s.pfeil} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

interface TurnierWechselProps {
  turnier: Turnier;
  onWechseln: () => void;
}

/** Das Turnier der Station im Seitenkopf, mit „wechseln“. */
export function TurnierWechsel({ turnier, onWechseln }: TurnierWechselProps) {
  const { t } = useTranslation("turnierwahl");
  return (
    <div className={s.wechsel}>
      <Trophy aria-hidden className={s.wechselSymbol} />
      <span className={s.wechselName}>
        <span className="nur-screenreader">{t("aktuell")}: </span>
        <strong>{turnier.name}</strong>
      </span>
      {turnier.status !== "active" && <TurnierStatusChip status={turnier.status} />}
      <Button
        variant="subtle"
        color="gray"
        size="compact-sm"
        leftSection={<Repeat aria-hidden />}
        onClick={onWechseln}
        aria-label={t("wechseln_lang", { name: turnier.name })}
      >
        {t("wechseln")}
      </Button>
    </div>
  );
}

interface MitTurnierProps {
  /** Wofür gewählt wird; erscheint in der Auswahl */
  hinweis?: string;
  /** Kopf der Seite, solange gewählt wird (z. B. Titel der Station) */
  kopf?: ReactNode;
  children: (wahl: AktivesTurnier & { turnier: Turnier }) => ReactNode;
}

/**
 * Rahmen für Stationen, die in genau einem Turnier arbeiten: lädt die Turniere, wählt das einzige
 * aktive von selbst, sonst zeigt er die Auswahl. Der Inhalt bekommt das gewählte Turnier.
 */
export function MitTurnier({ hinweis, kopf, children }: MitTurnierProps) {
  const wahl = useAktivesTurnier();
  const { abfrage, turnier } = wahl;

  if (abfrage.isPending) {
    return (
      <div className={s.rahmen} aria-busy="true">
        {kopf}
        <Skeleton height={160} radius="md" />
      </div>
    );
  }
  if (abfrage.isError) {
    return (
      <div className={s.rahmen}>
        {kopf}
        <div className="panel">
          <Fehlerzustand fehler={abfrage.error} onErneut={() => void abfrage.refetch()} />
        </div>
      </div>
    );
  }
  if (wahl.auswahlOffen || turnier === null) {
    return (
      <div className={s.rahmen}>
        {kopf}
        <TurnierAuswahl
          turniere={wahl.turniere}
          aktivId={turnier?.id}
          onWahl={wahl.waehlen}
          onAbbrechen={turnier ? wahl.abbrechen : undefined}
          hinweis={hinweis}
        />
      </div>
    );
  }
  return <>{children({ ...wahl, turnier })}</>;
}
