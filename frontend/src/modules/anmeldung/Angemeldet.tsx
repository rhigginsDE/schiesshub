import { CloseButton, Skeleton, TextInput } from "@mantine/core";
import type { UseQueryResult } from "@tanstack/react-query";
import { Search, SearchX, TriangleAlert, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Chip } from "../../components/Chip";
import { formatGeld } from "../../components/geld";
import { Fehlerzustand, Leerzustand } from "../../components/Zustand";
import { formatZahl } from "../../lib/format";
import type { TurnierUebersicht } from "../turnier/typen";
import { kennziffer } from "./AnmeldungFormular";
import s from "./AnmeldungSeite.module.css";
import type { Anmeldung } from "./api";
import { istWarnung, kennzahlen, statusAnzeige, sucheAnmeldungen } from "./logik";

interface AngemeldetProps {
  uebersicht: TurnierUebersicht | undefined;
  abfrage: UseQueryResult<Anmeldung[]>;
  aktivPersonId: string | null;
  onAuswahl: (anmeldung: Anmeldung) => void;
}

/** Rechte Spalte: Kennzahlen und alle Anmeldungen des Turniers, mit Suche. */
export function Angemeldet({ uebersicht, abfrage, aktivPersonId, onAuswahl }: AngemeldetProps) {
  const { t, i18n } = useTranslation("anmeldung");
  const sprache = i18n.language;
  const [suche, setSuche] = useState("");
  const alle = abfrage.data ?? [];
  const treffer = useMemo(() => sucheAnmeldungen(abfrage.data ?? [], suche), [abfrage.data, suche]);
  const zahlen = kennzahlen(alle);
  const waehrung = uebersicht?.settings.currency ?? "EUR";
  const wettbewerbe = new Map((uebersicht?.competitions ?? []).map((w) => [w.id, w]));
  const klassen = new Map((uebersicht?.classes ?? []).map((k) => [k.id, k]));

  return (
    <section className={`panel ${s.rechts}`} aria-labelledby="anmeldung-liste">
      <div className="panel-kopf">
        <h2 className="h-section" id="anmeldung-liste">
          {t("liste.titel")}
        </h2>
      </div>
      <dl className={s.kennzahlen}>
        <div>
          <dt className="h-label">{t("liste.schuetzen")}</dt>
          <dd className="num">{formatZahl(zahlen.schuetzen, {}, sprache)}</dd>
        </div>
        <div>
          <dt className="h-label">{t("liste.starts")}</dt>
          <dd className="num">{formatZahl(zahlen.starts, {}, sprache)}</dd>
        </div>
        <div>
          <dt className="h-label">{t("liste.startgeld")}</dt>
          <dd className="num">{formatGeld(zahlen.cents, waehrung, sprache)}</dd>
        </div>
      </dl>
      <TextInput
        type="search"
        size="md"
        value={suche}
        onChange={(ereignis) => setSuche(ereignis.currentTarget.value)}
        onKeyDown={(ereignis) => {
          if (ereignis.key === "Escape" && suche) {
            ereignis.preventDefault();
            ereignis.stopPropagation();
            setSuche("");
          } else if (ereignis.key === "Enter" && treffer[0]) {
            ereignis.preventDefault();
            onAuswahl(treffer[0]);
          }
        }}
        placeholder={t("liste.suche_platzhalter")}
        aria-label={t("liste.suche")}
        autoComplete="off"
        spellCheck={false}
        leftSection={<Search aria-hidden />}
        rightSection={
          suche ? (
            <CloseButton aria-label={t("liste.suche_leeren")} onClick={() => setSuche("")} />
          ) : null
        }
      />
      <div className={s.listeInhalt}>
        {abfrage.isPending ? (
          <div className={s.skelett} aria-busy="true">
            {[0, 1, 2, 3].map((nr) => (
              <Skeleton key={nr} height={56} radius="sm" />
            ))}
          </div>
        ) : abfrage.isError ? (
          <Fehlerzustand fehler={abfrage.error} onErneut={() => void abfrage.refetch()} />
        ) : alle.length === 0 ? (
          <Leerzustand icon={Users} titel={t("liste.leer_titel")} text={t("liste.leer_text")} />
        ) : treffer.length === 0 ? (
          <Leerzustand icon={SearchX} titel={t("liste.keine_titel")} text={t("liste.keine_text")} />
        ) : (
          <ul className={s.anmeldungen} aria-label={t("liste.titel")}>
            {treffer.map((anmeldung) => {
              const klasse = klassen.get(anmeldung.class_id);
              return (
                <li key={anmeldung.id}>
                  <button
                    type="button"
                    className={s.anmeldungZeile}
                    aria-current={anmeldung.person.id === aktivPersonId ? "true" : undefined}
                    onClick={() => onAuswahl(anmeldung)}
                  >
                    <span className={`num ${s.nummer}`}>{anmeldung.start_number}</span>
                    <span className={s.anmeldungText}>
                      <strong>{anmeldung.person.name}</strong>
                      <span className="gedaempft">
                        {anmeldung.person.club ?? t("person.ohne_verein")}
                        {klasse && ` · ${klasse.short}`}
                      </span>
                      {anmeldung.starts.length > 0 && (
                        <span className={s.startChips}>
                          {startGruppen(anmeldung.starts).map(({ start, anzahl }) => {
                            const wettbewerb = wettbewerbe.get(start.competition_id);
                            const anzeige = statusAnzeige(start);
                            // Warnung zum Startrecht im Wettbewerb: Symbol mit Text für Screenreader
                            const warnung = anmeldung.starts.some(
                              (st) =>
                                st.competition_id === start.competition_id &&
                                st.start_rights?.some(istWarnung),
                            );
                            return (
                              <Chip key={start.id} ton={anzeige.ton}>
                                {warnung && (
                                  <TriangleAlert
                                    role="img"
                                    aria-label={t("startrecht.markiert")}
                                    className={s.chipWarnung}
                                  >
                                    <title>{t("startrecht.markiert")}</title>
                                  </TriangleAlert>
                                )}
                                <span className="num">
                                  {wettbewerb ? kennziffer(wettbewerb) : "—"}
                                  {anzahl > 1 && ` ${t("liste.mal", { count: anzahl })}`}
                                </span>
                                {anzeige.schluessel !== "angemeldet" &&
                                  ` · ${t(`status.${anzeige.schluessel}`)}`}
                              </Chip>
                            );
                          })}
                        </span>
                      )}
                    </span>
                    <span className={`num ${s.anmeldungBetrag}`}>
                      {formatGeld(anmeldung.fee_total_cents, waehrung, sprache)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

/**
 * Starts im selben Wettbewerb mit demselben Stand zusammengefasst (Nachkauf: „4401 ×2“ statt
 * „4401 4401“). Reihenfolge wie gebucht.
 */
function startGruppen<
  T extends Parameters<typeof statusAnzeige>[0] & { id: string; competition_id: string },
>(starts: readonly T[]): { start: T; anzahl: number }[] {
  const gruppen = new Map<string, { start: T; anzahl: number }>();
  for (const start of starts) {
    const schluessel = `${start.competition_id}|${statusAnzeige(start).schluessel}`;
    const gruppe = gruppen.get(schluessel);
    if (gruppe) gruppe.anzahl += 1;
    else gruppen.set(schluessel, { start, anzahl: 1 });
  }
  return [...gruppen.values()];
}
