import { Button, CloseButton, Skeleton, TextInput } from "@mantine/core";
import { useDebouncedCallback } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search, SearchX, UserPlus, Users } from "lucide-react";
import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { formatZahl } from "../lib/format";
import { type Person, personenAbfrage } from "../modules/teilnehmer/api";
import { Chip } from "./Chip";
import s from "./PersonenSuche.module.css";
import { Fehlerzustand, Leerzustand } from "./Zustand";

const SUCHE_VERZOEGERUNG_MS = 200;

/**
 * Suche und Auswahl einer Person – serverseitig (`GET /persons?q=`), entprellt.
 * Gedacht für jede Stelle, an der eine Person gewählt wird: Teilnehmerverwaltung, später die
 * Anmeldung (Starts buchen).
 *
 * Schnittstelle:
 * - `onAuswahl(person)`: Person gewählt (Klick/Tippen oder Enter im Suchfeld mit Suchtext =
 *   erster Treffer).
 * - `onNeu(name)`: optional. Zeigt „Neue Person anlegen“; `name` ist der getippte Suchtext
 *   (bereinigt, ggf. leer) als Vorschlag für das Namensfeld.
 * - `aktivId`: ID der gerade geöffneten Person; wird in der Liste markiert.
 * - `onEsc`: optional. Esc im leeren Suchfeld (z. B. Detailansicht schließen). Esc mit Text leert
 *   zuerst die Suche.
 * - `tastenkuerzel` (Standard `true`): „/“ springt von überall auf der Seite ins Suchfeld, außer
 *   aus Eingabefeldern und Dialogen heraus.
 * - `primaerNeu`: „Neue Person anlegen“ als grüner Hauptknopf (nur, wenn die Ansicht sonst keinen hat).
 * - `markierung(person)`: optional. Zusatz am Treffer, z. B. „angemeldet · Nr. 7“.
 * - `vorTreffern(text)`: optional. Inhalt über der Trefferliste zum getippten Text (bereinigt), z. B.
 *   ein Treffer über die Startnummer. Liefert sie etwas, entfällt der Hinweis „keine Treffer“.
 * - `enterVorrang(text)`: optional. Enter im Suchfeld fragt zuerst hier; `true` = erledigt.
 * - `autoFokus`: Suchfeld beim Einblenden fokussieren (z. B. nach dem Speichern neu einblenden).
 *
 * Tastatur: „/“ fokussiert, Enter öffnet den ersten Treffer (nur mit Suchtext; im leeren Feld
 * springt Enter in die Liste, ohne jemanden zu öffnen), ↓/↑ wandern durch die Treffer.
 * Datenschutz: Der Suchtext bleibt im Zustand der Komponente – nicht in der Adresse, nicht im
 * Browser-Speicher, nicht im Protokoll.
 *
 * Layout: In einer Spalte mit fester Höhe (Fenster-Layout) scrollt nur die Trefferliste; ohne
 * feste Höhe wächst die Liste mit und die Seite scrollt.
 */
export interface PersonenSucheProps {
  onAuswahl: (person: Person) => void;
  onNeu?: (name: string) => void;
  aktivId?: string | null;
  onEsc?: () => void;
  tastenkuerzel?: boolean;
  primaerNeu?: boolean;
  markierung?: (person: Person) => ReactNode;
  vorTreffern?: (text: string) => ReactNode;
  enterVorrang?: (text: string) => boolean;
  autoFokus?: boolean;
}

export function PersonenSuche({
  onAuswahl,
  onNeu,
  aktivId,
  onEsc,
  tastenkuerzel = true,
  primaerNeu = false,
  markierung,
  vorTreffern,
  enterVorrang,
  autoFokus = false,
}: PersonenSucheProps) {
  const { t, i18n } = useTranslation("teilnehmer");
  const [eingabe, setEingabe] = useState("");
  const [suchtext, setSuchtext] = useState("");
  const feld = useRef<HTMLInputElement>(null);
  const liste = useRef<HTMLUListElement>(null);
  const listeId = useId();
  // Enter vor dem Ende der Entprellung: ersten Treffer öffnen, sobald die Antwort da ist.
  const ersterNachLaden = useRef<string | null>(null);

  const abfrage = useQuery({ ...personenAbfrage(suchtext), placeholderData: keepPreviousData });
  const aktuell = !abfrage.isPlaceholderData;

  const verzoegert = useDebouncedCallback((text: string) => setSuchtext(text.trim()), {
    delay: SUCHE_VERZOEGERUNG_MS,
  });

  useEffect(() => {
    const ziel = ersterNachLaden.current;
    if (ziel === null || !aktuell || !abfrage.data || ziel !== suchtext) return;
    ersterNachLaden.current = null;
    const erster = abfrage.data.personen[0];
    if (erster) onAuswahl(erster);
  }, [abfrage.data, aktuell, suchtext, onAuswahl]);

  useEffect(() => {
    if (!tastenkuerzel) return;
    const beiTaste = (ereignis: globalThis.KeyboardEvent) => {
      if (ereignis.key !== "/" || ereignis.ctrlKey || ereignis.metaKey || ereignis.altKey) return;
      const ziel = ereignis.target as HTMLElement | null;
      if (ziel?.closest("input, textarea, select, [contenteditable=true], [role=dialog]")) return;
      if (document.querySelector("[role=dialog]")) return;
      ereignis.preventDefault();
      feld.current?.focus();
      feld.current?.select();
    };
    window.addEventListener("keydown", beiTaste);
    return () => window.removeEventListener("keydown", beiTaste);
  }, [tastenkuerzel]);

  const leeren = () => {
    setEingabe("");
    verzoegert.cancel();
    setSuchtext("");
    feld.current?.focus();
  };

  const trefferFokussieren = (index: number) => {
    const knoepfe = liste.current?.querySelectorAll<HTMLButtonElement>("button[data-treffer]");
    if (!knoepfe || knoepfe.length === 0) return;
    if (index < 0) {
      feld.current?.focus();
      return;
    }
    knoepfe[Math.min(index, knoepfe.length - 1)]?.focus();
  };

  const beiFeldTaste = (ereignis: KeyboardEvent<HTMLInputElement>) => {
    if (ereignis.key === "Enter") {
      ereignis.preventDefault();
      const text = eingabe.trim();
      // Ohne Suchtext öffnet Enter niemanden (typischer Fehlgriff „Enter zum Absenden“):
      // höchstens in die Liste springen, damit die Wahl bewusst bleibt.
      if (!text) {
        trefferFokussieren(0);
        return;
      }
      if (enterVorrang?.(text)) return;
      if (text !== suchtext || !aktuell) {
        verzoegert.cancel();
        ersterNachLaden.current = text;
        setSuchtext(text);
        return;
      }
      const erster = abfrage.data?.personen[0];
      if (erster) onAuswahl(erster);
    } else if (ereignis.key === "ArrowDown") {
      ereignis.preventDefault();
      trefferFokussieren(0);
    } else if (ereignis.key === "Escape") {
      if (eingabe) {
        ereignis.preventDefault();
        ereignis.stopPropagation();
        leeren();
      } else if (onEsc) {
        ereignis.preventDefault();
        ereignis.stopPropagation();
        onEsc();
      }
    }
  };

  const beiTrefferTaste = (ereignis: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (ereignis.key === "ArrowDown") {
      ereignis.preventDefault();
      trefferFokussieren(index + 1);
    } else if (ereignis.key === "ArrowUp") {
      ereignis.preventDefault();
      trefferFokussieren(index - 1);
    } else if (ereignis.key === "Escape" || ereignis.key === "/") {
      ereignis.preventDefault();
      ereignis.stopPropagation();
      feld.current?.focus();
    }
  };

  const sprache = i18n.language;
  const daten = abfrage.data;
  const gezeigt = daten?.personen.length ?? 0;
  const zusatz = vorTreffern?.(eingabe.trim()) ?? null;

  return (
    <div className={s.suche}>
      <div className={s.kopf}>
        <TextInput
          ref={feld}
          type="search"
          size="lg"
          value={eingabe}
          onChange={(ereignis) => {
            setEingabe(ereignis.currentTarget.value);
            verzoegert(ereignis.currentTarget.value);
          }}
          onKeyDown={beiFeldTaste}
          placeholder={t("suche.platzhalter")}
          aria-label={t("suche.beschriftung")}
          aria-controls={listeId}
          aria-describedby={`${listeId}-tasten`}
          autoComplete="off"
          spellCheck={false}
          autoFocus={autoFokus}
          classNames={{ input: s.feld }}
          leftSection={<Search aria-hidden />}
          rightSectionWidth={52}
          rightSection={
            eingabe ? (
              <CloseButton aria-label={t("suche.leeren")} onClick={leeren} />
            ) : tastenkuerzel ? (
              <kbd className={s.taste} title={t("suche.taste")}>
                /
              </kbd>
            ) : null
          }
        />
        <span id={`${listeId}-tasten`} className="nur-screenreader">
          {t("suche.tasten")}
        </span>
        <div className={s.fuss}>
          <span className="gedaempft" aria-live="polite">
            {daten &&
              t(suchtext ? "suche.treffer" : "suche.alle", {
                count: daten.gesamt,
                anzahl: formatZahl(daten.gesamt, {}, sprache),
              })}
          </span>
          {onNeu && (
            <Button
              variant={primaerNeu ? "filled" : "default"}
              size="sm"
              leftSection={<UserPlus aria-hidden />}
              onClick={() => onNeu(eingabe.trim())}
            >
              {eingabe.trim() ? t("suche.neu_mit_name", { name: eingabe.trim() }) : t("suche.neu")}
            </Button>
          )}
        </div>
      </div>

      <div className={s.inhalt}>
        {zusatz}
        {abfrage.isPending ? (
          <div className={s.skelett} aria-busy="true">
            {[0, 1, 2, 3, 4, 5].map((nr) => (
              <Skeleton key={nr} height={52} radius="sm" />
            ))}
          </div>
        ) : abfrage.isError ? (
          <Fehlerzustand fehler={abfrage.error} onErneut={() => void abfrage.refetch()} />
        ) : gezeigt === 0 ? (
          zusatz !== null ? null : suchtext ? (
            <Leerzustand
              icon={SearchX}
              titel={t("suche.leer_titel")}
              text={t("suche.leer_text", { q: suchtext })}
            >
              <Button variant="default" onClick={leeren}>
                {t("suche.leeren")}
              </Button>
            </Leerzustand>
          ) : (
            <Leerzustand
              icon={Users}
              titel={t("suche.leer_bestand_titel")}
              text={t("suche.leer_bestand_text")}
            />
          )
        ) : (
          <>
            <ul
              ref={liste}
              id={listeId}
              className={s.liste}
              aria-label={t("suche.beschriftung")}
              data-laedt={abfrage.isPlaceholderData || undefined}
            >
              {daten?.personen.map((person, index) => (
                <li key={person.id}>
                  <button
                    type="button"
                    data-treffer
                    className={s.treffer}
                    aria-current={person.id === aktivId ? "true" : undefined}
                    onClick={() => onAuswahl(person)}
                    onKeyDown={(ereignis) => beiTrefferTaste(ereignis, index)}
                  >
                    <span className={s.trefferText}>
                      <strong>{person.name}</strong>
                      <span>
                        {person.club_name ?? t("suche.ohne_verein")}
                        {person.member_no && (
                          <>
                            {" · "}
                            <span className="num">
                              {t("suche.mitgliedsnummer", { nr: person.member_no })}
                            </span>
                          </>
                        )}
                      </span>
                    </span>
                    {markierung?.(person)}
                    {person.display_mode !== "full" && (
                      <Chip ton={person.display_mode === "hidden" ? "warn" : "info"}>
                        {t(`anzeige.chip_${person.display_mode}`)}
                      </Chip>
                    )}
                  </button>
                </li>
              ))}
            </ul>
            {daten && daten.gesamt > gezeigt && (
              <p className={s.begrenzt}>
                {t("suche.begrenzt", {
                  gezeigt: formatZahl(gezeigt, {}, sprache),
                  gesamt: formatZahl(daten.gesamt, {}, sprache),
                })}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
