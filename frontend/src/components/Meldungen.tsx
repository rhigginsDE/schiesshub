import { CloseButton } from "@mantine/core";
import { CircleCheck, Info, ShieldAlert, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import s from "./Meldungen.module.css";

export type MeldungTon = "erfolg" | "info" | "warn" | "krit";

export interface Meldung {
  id: number;
  ton: MeldungTon;
  titel: string;
  text?: string;
  /** Gleiche Schlüssel ersetzen sich, statt sich zu stapeln (z. B. „Berechtigung fehlt“). */
  schluessel?: string;
  /** Nach so vielen Millisekunden ausblenden; `0` = bleibt, bis man sie schließt. */
  dauerMs: number;
}

/** Lang genug auch für langsame Leser; beim Überfahren oder Berühren läuft die Zeit nicht weiter. */
export const STANDARD_DAUER_MS = { erfolg: 6000, info: 8000, warn: 10000, krit: 0 } as const;

let liste: Meldung[] = [];
let naechsteId = 1;
const hoerer = new Set<() => void>();

function aendern(neu: Meldung[]) {
  liste = neu;
  for (const rueckruf of hoerer) rueckruf();
}

/**
 * Kurze Rückmeldung am Bildschirmrand, z. B. „Gespeichert“ oder „Dafür fehlt die Berechtigung“.
 * Fehler, die zu einem Formular gehören, stehen besser direkt am Formular.
 */
export function zeigeMeldung(
  meldung: Omit<Meldung, "id" | "dauerMs"> & { dauerMs?: number },
): number {
  const id = naechsteId++;
  const neu: Meldung = {
    ...meldung,
    id,
    dauerMs: meldung.dauerMs ?? STANDARD_DAUER_MS[meldung.ton],
  };
  const ohneGleiche = meldung.schluessel
    ? liste.filter((eintrag) => eintrag.schluessel !== meldung.schluessel)
    : liste;
  aendern([...ohneGleiche.slice(-3), neu]);
  return id;
}

/** Alle Meldungen entfernen, z. B. zwischen Tests. */
export function meldungenLeeren() {
  aendern([]);
}

export function schliesseMeldung(id: number) {
  aendern(liste.filter((eintrag) => eintrag.id !== id));
}

function abonnieren(rueckruf: () => void) {
  hoerer.add(rueckruf);
  return () => hoerer.delete(rueckruf);
}

const SYMBOLE = { erfolg: CircleCheck, info: Info, warn: TriangleAlert, krit: ShieldAlert };

/** Ausgabestelle für `zeigeMeldung`; steht einmal in der App-Shell. */
export function Meldungen() {
  const meldungen = useSyncExternalStore(abonnieren, () => liste);
  return (
    <section className={s.stapel} aria-live="polite">
      {meldungen.map((meldung) => (
        <MeldungKarte key={meldung.id} meldung={meldung} />
      ))}
    </section>
  );
}

function MeldungKarte({ meldung }: { meldung: Meldung }) {
  const { t } = useTranslation();
  const Icon = SYMBOLE[meldung.ton];
  const [angehalten, setAngehalten] = useState(false);
  const rest = useRef(meldung.dauerMs);

  useEffect(() => {
    if (meldung.dauerMs <= 0 || angehalten) return;
    const start = Date.now();
    const timer = setTimeout(() => schliesseMeldung(meldung.id), rest.current);
    return () => {
      clearTimeout(timer);
      rest.current = Math.max(1000, rest.current - (Date.now() - start));
    };
  }, [meldung.id, meldung.dauerMs, angehalten]);

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: hält nur den Zeitgeber an, löst nichts aus
    <div
      className={`${s.karte} ${s[meldung.ton]}`}
      role={meldung.ton === "krit" ? "alert" : "status"}
      onPointerEnter={() => setAngehalten(true)}
      onPointerLeave={() => setAngehalten(false)}
      onFocus={() => setAngehalten(true)}
      onBlur={() => setAngehalten(false)}
    >
      <Icon className={s.symbol} aria-hidden />
      <div className={s.text}>
        <strong>{meldung.titel}</strong>
        {meldung.text && <p>{meldung.text}</p>}
      </div>
      <CloseButton
        size="lg"
        aria-label={t("shell:meldung.schliessen")}
        onClick={() => schliesseMeldung(meldung.id)}
      />
    </div>
  );
}
