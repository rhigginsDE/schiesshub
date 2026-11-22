import { Button, Skeleton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { CalendarX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Dialog } from "../../components/Dialog";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { formatUhrzeit } from "../../lib/format";
import type { Stand, Wettbewerb } from "../turnier/typen";
import s from "./AnmeldungSeite.module.css";
import { type Durchgang, durchgaengeAbfrage, type StationStart, startlisteAbfrage } from "./api";
import type { Platz } from "./buchen";

/** Belegte Bahnen je Durchgang (ohne abgebrochene Starts, wie der Server zählt). */
export function belegteBahnen(starts: readonly StationStart[]): Map<string, Set<number>> {
  const belegt = new Map<string, Set<number>>();
  for (const start of starts) {
    if (!start.heat_id || start.lane === null || start.status === "aborted") continue;
    const bahnen = belegt.get(start.heat_id) ?? new Set<number>();
    bahnen.add(start.lane);
    belegt.set(start.heat_id, bahnen);
  }
  return belegt;
}

/** Durchgänge, die noch nicht vorbei sind, nach Beginn. */
export function kommendeDurchgaenge(durchgaenge: readonly Durchgang[], jetzt: Date): Durchgang[] {
  return durchgaenge
    .filter((d) => Date.parse(d.ends_at) > jetzt.getTime())
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at) || a.number - b.number);
}

interface PlatzWahlProps {
  turnierId: string;
  wettbewerb: Wettbewerb;
  stand: Stand | undefined;
  gewaehlt: Platz | null;
  onWahl: (platz: Platz) => void;
  onSchliessen: () => void;
}

/** Durchgang und Bahn für den ersten neuen Start selbst wählen (statt des Vorschlags). */
export function PlatzWahl({
  turnierId,
  wettbewerb,
  stand,
  gewaehlt,
  onWahl,
  onSchliessen,
}: PlatzWahlProps) {
  const { t, i18n } = useTranslation("anmeldung");
  const standId = wettbewerb.range_id ?? "";
  const durchgaenge = useQuery(durchgaengeAbfrage(turnierId, standId));
  const startliste = useQuery(startlisteAbfrage(turnierId, { stand: standId }));
  const belegt = belegteBahnen(startliste.data ?? []);
  const kommende = kommendeDurchgaenge(durchgaenge.data ?? [], new Date());
  const bahnen = Array.from({ length: stand?.lane_count ?? 0 }, (_, i) => i + 1);

  return (
    <Dialog
      onClose={onSchliessen}
      title={t("platz.titel", {
        // Mit Kennziffer: 1001 und 1201 heißen beide „Pistole bis 9 mm“.
        wettbewerb: [wettbewerb.catalog_code, wettbewerb.name].filter(Boolean).join(" "),
      })}
      size="lg"
      closeButtonProps={{ "aria-label": t("platz.schliessen") }}
    >
      <div className={s.platzWahl}>
        <p className="gedaempft">{t("platz.hinweis", { stand: stand?.name ?? "" })}</p>
        {durchgaenge.isPending || startliste.isPending ? (
          <Skeleton height={120} />
        ) : durchgaenge.isError ? (
          <Fehlerzustand fehler={durchgaenge.error} onErneut={() => void durchgaenge.refetch()} />
        ) : startliste.isError ? (
          <Fehlerzustand fehler={startliste.error} onErneut={() => void startliste.refetch()} />
        ) : kommende.length === 0 ? (
          <Leerzustand icon={CalendarX} titel={t("platz.leer_titel")} text={t("platz.leer_text")} />
        ) : (
          <ul className={s.durchgaenge}>
            {kommende.map((durchgang) => {
              const besetzt = belegt.get(durchgang.id) ?? new Set<number>();
              const zeit = formatUhrzeit(new Date(durchgang.starts_at), i18n.language);
              return (
                <li key={durchgang.id} className={s.durchgang}>
                  <span className={s.durchgangZeit}>
                    <b className="num">{zeit}</b>
                    <span className="gedaempft">
                      {t("platz.durchgang", { nummer: durchgang.number })} ·{" "}
                      <span className="num">
                        {durchgang.booked}/{durchgang.capacity}
                      </span>
                    </span>
                  </span>
                  <span className={s.bahnKnoepfe}>
                    {bahnen.map((bahn) => {
                      const frei = !besetzt.has(bahn);
                      const aktiv =
                        gewaehlt?.durchgangId === durchgang.id && gewaehlt.bahn === bahn;
                      return (
                        <Button
                          key={bahn}
                          size="md"
                          variant={aktiv ? "light" : "default"}
                          disabled={!frei}
                          aria-pressed={aktiv}
                          aria-label={t(frei ? "platz.bahn_frei" : "platz.bahn_belegt", {
                            bahn,
                            zeit,
                          })}
                          onClick={() => onWahl({ durchgangId: durchgang.id, bahn })}
                          className="num"
                        >
                          {bahn}
                        </Button>
                      );
                    })}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Dialog>
  );
}
