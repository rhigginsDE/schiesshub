import { createContext, useContext, useEffect, useId, useRef, useState } from "react";

function gleich(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Was ein Formular dem Register meldet. */
interface Meldung {
  geaendert: boolean;
  verwerfen: () => void;
  /** Speichert den Entwurf; `false`, wenn die Prüfung oder der Server ihn ablehnt. */
  speichern?: () => Promise<boolean>;
}

/**
 * Sammelt die ungespeicherten Entwürfe einer Seite. Die Seite fragt damit vor dem Verlassen nach
 * („Speichern / Verwerfen / Weiter bearbeiten“) und zeigt den Speicherstand an.
 */
export class EntwurfRegister {
  private readonly eintraege = new Map<string, { current: Meldung }>();
  private readonly hoerer = new Set<() => void>();

  setze(id: string, meldung: { current: Meldung }) {
    this.eintraege.set(id, meldung);
    this.melde();
  }

  entferne(id: string) {
    this.eintraege.delete(id);
    this.melde();
  }

  melde() {
    for (const hoerer of this.hoerer) hoerer();
  }

  abonniere = (hoerer: () => void) => {
    this.hoerer.add(hoerer);
    return () => {
      this.hoerer.delete(hoerer);
    };
  };

  /** Gibt es irgendwo ungespeicherte Änderungen? */
  geaendert = (): boolean => this.offen().length > 0;

  /** Lässt sich alles Ungespeicherte von hier aus speichern? */
  speicherbar(): boolean {
    const offen = this.offen();
    return offen.length > 0 && offen.every((m) => m.speichern);
  }

  async speichern(): Promise<boolean> {
    for (const meldung of this.offen()) {
      if (!meldung.speichern || !(await meldung.speichern())) return false;
    }
    return true;
  }

  verwerfen() {
    for (const meldung of this.offen()) meldung.verwerfen();
  }

  private offen(): Meldung[] {
    return [...this.eintraege.values()].map((e) => e.current).filter((m) => m.geaendert);
  }
}

export const EntwurfKontext = createContext<EntwurfRegister | null>(null);

/**
 * Lokaler Entwurf eines Formulars über Serverdaten. Kommen neue Daten vom Server (Ereignis,
 * anderes Gerät) und ist nichts geändert, folgt der Entwurf; sonst bleiben die Eingaben stehen.
 * Innerhalb eines `EntwurfKontext` meldet sich der Entwurf an, damit die Seite vor dem Verlassen
 * nachfragt. Mit `speichern` bietet die Rückfrage auch „Speichern“ an.
 */
export function useEntwurf<T>(quelle: T, optionen?: { speichern?: () => Promise<boolean> }) {
  const [basis, setBasis] = useState(quelle);
  const [werte, setWerte] = useState(quelle);
  const geaendert = !gleich(werte, basis);

  if (!gleich(quelle, basis)) {
    setBasis(quelle);
    if (!geaendert) setWerte(quelle);
  }

  const verwerfen = () => setWerte(basis);
  const register = useContext(EntwurfKontext);
  const id = useId();
  const meldung = useRef<Meldung>({ geaendert, verwerfen, speichern: optionen?.speichern });

  // Immer den letzten Stand melden; das Register liest nur bei Bedarf.
  useEffect(() => {
    meldung.current = { geaendert, verwerfen, speichern: optionen?.speichern };
  });
  useEffect(() => {
    if (!register) return;
    register.setze(id, meldung);
    return () => register.entferne(id);
  }, [register, id]);
  useEffect(() => {
    meldung.current = { ...meldung.current, geaendert };
    register?.melde();
  }, [register, geaendert]);

  return {
    werte,
    setWerte,
    geaendert,
    /** Server-Stand, gegen den verglichen wird */
    basis,
    verwerfen,
  };
}
