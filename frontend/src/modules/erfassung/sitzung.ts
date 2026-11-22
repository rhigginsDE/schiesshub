/**
 * Sende-Sitzung eines Starts: hält den Entwurf, sendet ihn entprellt als Rohwerte und übernimmt die
 * Antwort des Servers. Ohne React, mit austauschbarer Uhr einzeln getestet.
 *
 * - Eingaben erscheinen sofort (Entwurf); Summen und Rechenweg kommen nur aus der Antwort (`basis`).
 * - Jede Sendung trägt einen Idempotency-Key. Nach einem Netzfehler bleibt der Entwurf stehen und
 *   wird mit demselben Schlüssel erneut gesendet, solange er sich nicht ändert.
 * - 409 mit Stand des Servers (anderes Gerät war schneller): nichts wird überschrieben; die Sitzung
 *   wartet, bis gewählt ist, welcher Stand gilt.
 * - Fremde Änderungen, die über die Server-Ereignisse kommen, werden nur übernommen, wenn nichts
 *   Eigenes ungespeichert ist; sonst gilt dasselbe wie bei 409.
 */
import { ApiFehler } from "../../api/client";
import {
  type ErgebnisStand,
  istVoruebergehend,
  neuerSchluessel,
  type Rohwerte,
  SeqKonflikt,
} from "./api";
import {
  type Entwurf,
  entwurfAus,
  gleicheRohwerte,
  normalerPfad,
  type PfadMeldung,
  stabil,
} from "./rohwerte";

/**
 * - `gespeichert`: Entwurf und Server stimmen überein
 * - `wartet`: Eingabe läuft, Sendung folgt gleich
 * - `sendet`: Sendung unterwegs
 * - `netzfehler`: nicht angekommen, wird von selbst erneut gesendet
 * - `abgelehnt`: Der Server hat die Eingabe abgelehnt (Prüffehler oder Zustand passt nicht)
 * - `konflikt`: Jemand anderes hat denselben Start geändert; Entscheidung nötig
 */
export type Phase = "gespeichert" | "wartet" | "sendet" | "netzfehler" | "abgelehnt" | "konflikt";

export interface SitzungsZustand {
  entwurf: Entwurf;
  basis: ErgebnisStand;
  phase: Phase;
  /** Entwurf weicht vom Stand des Servers ab */
  ungespeichert: boolean;
  fehler: unknown;
  feldFehler: PfadMeldung[];
  /** Stand des Servers bei einem Konflikt */
  konflikt: ErgebnisStand | null;
  /** Fehlversuche seit der letzten erfolgreichen Sendung */
  versuche: number;
  /** Zähler, der bei jeder von einem anderen Gerät übernommenen Änderung steigt */
  fremdUebernommen: number;
}

export type Senden = (raw: Rohwerte, baseSeq: number, schluessel: string) => Promise<ErgebnisStand>;

export interface Uhr {
  setTimeout: (rueckruf: () => void, ms: number) => unknown;
  clearTimeout: (id: unknown) => void;
}

export interface SitzungOptionen {
  basis: ErgebnisStand;
  rohwerte: (entwurf: Entwurf) => Rohwerte;
  senden: Senden;
  /** `false`: nichts von selbst senden (Korrektur eines abgeschlossenen Ergebnisses) */
  automatisch?: boolean;
  verzoegerungMs?: number;
  wiederholungMs?: readonly number[];
  uhr?: Uhr;
}

export const VERZOEGERUNG_MS = 450;
export const WIEDERHOLUNG_MS = [1000, 2000, 4000, 8000, 15000] as const;

const STANDARD_UHR: Uhr = {
  setTimeout: (rueckruf, ms) => globalThis.setTimeout(rueckruf, ms),
  clearTimeout: (id) => globalThis.clearTimeout(id as ReturnType<typeof setTimeout>),
};

interface Ausstehend {
  schluessel: string;
  text: string;
  baseSeq: number;
}

export class Sitzung {
  private zustand: SitzungsZustand;
  private readonly hoerer = new Set<() => void>();
  private rohwerte: (entwurf: Entwurf) => Rohwerte;
  private readonly senden: Senden;
  private automatisch: boolean;
  private readonly verzoegerungMs: number;
  private readonly wiederholungMs: readonly number[];
  private readonly uhr: Uhr;
  private timer: unknown = null;
  private laeuft = false;
  private nochmal = false;
  private ausstehend: Ausstehend | null = null;
  private beendet = false;

  constructor(optionen: SitzungOptionen) {
    this.rohwerte = optionen.rohwerte;
    this.senden = optionen.senden;
    this.automatisch = optionen.automatisch ?? true;
    this.verzoegerungMs = optionen.verzoegerungMs ?? VERZOEGERUNG_MS;
    this.wiederholungMs = optionen.wiederholungMs ?? WIEDERHOLUNG_MS;
    this.uhr = optionen.uhr ?? STANDARD_UHR;
    this.zustand = {
      entwurf: entwurfAus(optionen.basis.raw),
      basis: optionen.basis,
      phase: "gespeichert",
      ungespeichert: false,
      fehler: null,
      feldFehler: [],
      konflikt: null,
      versuche: 0,
      fremdUebernommen: 0,
    };
  }

  // --- Abonnement (useSyncExternalStore) ---

  readonly abonnieren = (rueckruf: () => void) => {
    this.hoerer.add(rueckruf);
    return () => {
      this.hoerer.delete(rueckruf);
    };
  };

  readonly lesen = (): SitzungsZustand => this.zustand;

  private setzen(teil: Partial<SitzungsZustand>) {
    const neu = { ...this.zustand, ...teil };
    neu.ungespeichert = !gleicheRohwerte(this.rohwerte(neu.entwurf), neu.basis.raw);
    this.zustand = neu;
    for (const rueckruf of this.hoerer) rueckruf();
  }

  // --- Einstellungen ---

  /** Neue Formularbeschreibung (z. B. andere Erfassungsart): bestimmt, was gesendet wird. */
  setzeRohwerte(rohwerte: (entwurf: Entwurf) => Rohwerte) {
    this.rohwerte = rohwerte;
    this.setzen({});
  }

  setzeAutomatisch(automatisch: boolean) {
    this.automatisch = automatisch;
    if (!automatisch) this.timerStoppen();
  }

  /** Nach `beenden` wieder aufnehmen (React StrictMode baut Effekte doppelt auf). */
  starten() {
    if (!this.beendet) return;
    this.beendet = false;
    if (this.zustand.ungespeichert && this.zustand.phase !== "konflikt") this.erneut();
  }

  /** Timer anhalten; Antworten, die danach ankommen, werden nicht mehr übernommen. */
  beenden() {
    this.beendet = true;
    this.timerStoppen();
  }

  // --- Eingabe ---

  aendern(entwurf: Entwurf) {
    this.setzen({ entwurf });
    if (!this.automatisch || this.zustand.phase === "konflikt") return;
    this.planen(this.verzoegerungMs);
  }

  /** Sofort senden, z. B. „erneut senden“ oder wenn das Netz zurück ist. */
  erneut() {
    if (!this.automatisch || this.zustand.phase === "konflikt") return;
    this.planen(0);
  }

  private timerStoppen() {
    if (this.timer !== null) this.uhr.clearTimeout(this.timer);
    this.timer = null;
  }

  private planen(ms: number) {
    this.timerStoppen();
    if (!this.zustand.ungespeichert) {
      if (!this.laeuft) this.setzen({ phase: "gespeichert", fehler: null });
      return;
    }
    if (!this.laeuft && this.zustand.phase !== "netzfehler" && this.zustand.phase !== "abgelehnt") {
      this.setzen({ phase: "wartet" });
    }
    this.timer = this.uhr.setTimeout(() => {
      this.timer = null;
      void this.sendeJetzt();
    }, ms);
  }

  private async sendeJetzt() {
    if (this.beendet) return;
    if (this.laeuft) {
      this.nochmal = true;
      return;
    }
    const raw = this.rohwerte(this.zustand.entwurf);
    const basis = this.zustand.basis;
    if (gleicheRohwerte(raw, basis.raw)) {
      this.setzen({ phase: "gespeichert", fehler: null });
      return;
    }
    const text = stabil(raw);
    // Dieselbe Eingabe auf demselben Stand behält ihren Schlüssel (Wiederholung nach Netzfehler).
    if (
      !this.ausstehend ||
      this.ausstehend.text !== text ||
      this.ausstehend.baseSeq !== basis.seq
    ) {
      this.ausstehend = { schluessel: neuerSchluessel(), text, baseSeq: basis.seq };
    }
    const { schluessel } = this.ausstehend;
    this.laeuft = true;
    this.nochmal = false;
    this.setzen({ phase: "sendet" });
    try {
      const antwort = await this.senden(raw, basis.seq, schluessel);
      this.laeuft = false;
      if (this.beendet) return;
      this.ausstehend = null;
      this.setzen({ basis: antwort, fehler: null, feldFehler: [], versuche: 0 });
      if (this.zustand.ungespeichert) {
        this.setzen({ phase: "wartet" });
        this.planen(this.nochmal ? 0 : this.verzoegerungMs);
      } else {
        this.setzen({ phase: "gespeichert" });
      }
    } catch (fehler) {
      this.laeuft = false;
      if (this.beendet) return;
      this.fehlerBehandeln(fehler);
    }
  }

  private fehlerBehandeln(fehler: unknown) {
    if (fehler instanceof SeqKonflikt) {
      this.ausstehend = null;
      this.setzen({ phase: "konflikt", konflikt: fehler.aktuell, fehler });
      return;
    }
    if (istVoruebergehend(fehler)) {
      const versuche = this.zustand.versuche + 1;
      this.setzen({ phase: "netzfehler", fehler, versuche });
      const ms =
        this.wiederholungMs[Math.min(versuche - 1, this.wiederholungMs.length - 1)] ?? 5000;
      this.timerStoppen();
      this.timer = this.uhr.setTimeout(() => {
        this.timer = null;
        void this.sendeJetzt();
      }, ms);
      return;
    }
    this.ausstehend = null;
    const feldFehler =
      fehler instanceof ApiFehler
        ? fehler.felder.map((f) => ({ pfad: normalerPfad(f.feld), meldung: f.meldung }))
        : [];
    this.setzen({ phase: "abgelehnt", fehler, feldFehler });
  }

  /**
   * Fehler eines Vorgangs außerhalb der automatischen Sendung (z. B. Korrektur): Feldfehler an die
   * Felder, 409 mit Stand als Konflikt. Netzfehler bleiben beim Aufrufer (kein automatisches Senden).
   */
  vorgangFehler(fehler: unknown) {
    if (fehler instanceof SeqKonflikt) {
      this.setzen({ phase: "konflikt", konflikt: fehler.aktuell, fehler });
      return;
    }
    const feldFehler =
      fehler instanceof ApiFehler
        ? fehler.felder.map((f) => ({ pfad: normalerPfad(f.feld), meldung: f.meldung }))
        : [];
    this.setzen({
      fehler,
      feldFehler,
      phase: feldFehler.length > 0 ? "abgelehnt" : this.zustand.phase,
    });
  }

  // --- Stand des Servers ---

  /** Stand übernehmen, den ein anderer Vorgang geliefert hat (Abschluss, Korrektur, Abbruch …). */
  uebernehmen(stand: ErgebnisStand) {
    this.timerStoppen();
    this.ausstehend = null;
    this.setzen({
      basis: stand,
      entwurf: entwurfAus(stand.raw),
      phase: "gespeichert",
      fehler: null,
      feldFehler: [],
      konflikt: null,
      versuche: 0,
    });
  }

  /**
   * Stand, den der Server beim Neuladen meldet (z. B. nach einem Ereignis). Neuer als der eigene:
   * übernehmen, wenn nichts Eigenes ungespeichert ist; sonst als Konflikt vorlegen.
   */
  serverStand(stand: ErgebnisStand) {
    const basis = this.zustand.basis;
    if (stand.start_id !== basis.start_id || this.laeuft || this.zustand.phase === "konflikt") {
      return;
    }
    if (stand.seq < basis.seq) return;
    if (stand.seq === basis.seq) {
      // Gleiches Ereignis, aber z. B. Status oder Prüfkennzeichen geändert.
      if (stabil(stand) !== stabil(basis)) this.setzen({ basis: stand });
      return;
    }
    if (!this.zustand.ungespeichert) {
      this.uebernehmen(stand);
      this.setzen({ fremdUebernommen: this.zustand.fremdUebernommen + 1 });
      return;
    }
    this.timerStoppen();
    this.ausstehend = null;
    this.setzen({ phase: "konflikt", konflikt: stand });
  }

  /** Konflikt: Stand des Servers gilt, eigene Eingabe wird verworfen. */
  konfliktServer() {
    const stand = this.zustand.konflikt;
    if (stand) this.uebernehmen(stand);
  }

  /** Konflikt: eigene Eingabe auf den Stand des Servers setzen und senden (neues Ereignis). */
  konfliktMeins() {
    const stand = this.zustand.konflikt;
    if (!stand) return;
    this.setzen({ basis: stand, konflikt: null, phase: "wartet", fehler: null });
    if (this.automatisch) this.planen(0);
    else this.setzen({ phase: "gespeichert" });
  }
}
