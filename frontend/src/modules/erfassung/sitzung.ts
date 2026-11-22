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
 *   Eigenes ungespeichert ist; sonst gilt dasselbe wie bei 409. Steht beim Server schon genau das,
 *   was eingegeben wurde, ist es kein Konflikt.
 * - Was der Server noch nicht bestätigt hat, liegt zusätzlich in einer Ablage (im Terminal der
 *   `sessionStorage` des Tabs). Wird die Ansicht neu aufgebaut (Neuladen, Fehleranzeige, Wechsel),
 *   kommt die Eingabe von dort zurück und wird gesendet, statt still verloren zu gehen.
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
  /** Eine noch nicht bestätigte Eingabe wurde aus der Ablage zurückgeholt */
  wiederhergestellt: boolean;
}

/** Noch nicht bestätigte Eingabe mit dem Stand des Servers, auf dem sie beruht. */
export interface AbgelegterEntwurf {
  baseSeq: number;
  entwurf: Entwurf;
  /**
   * Rohwerte, die gerade auf `baseSeq` unterwegs sind. Kommt nach dem Neuladen genau dieser Stand
   * mit `baseSeq + 1` vom Server, ist die eigene Sendung angekommen (kein fremdes Gerät).
   */
  unterwegs?: Rohwerte | null;
}

/** Ablage für unbestätigte Eingaben (je Start). Fehler beim Schreiben werden geschluckt. */
export interface EntwurfAblage {
  lesen: () => AbgelegterEntwurf | null;
  schreiben: (wert: AbgelegterEntwurf | null) => void;
}

/** Ablage im `sessionStorage` (je Tab; überlebt Neuladen, nicht das Schließen). */
export function sitzungsAblage(schluessel: string): EntwurfAblage {
  return {
    lesen: () => {
      try {
        const text = globalThis.sessionStorage?.getItem(schluessel);
        if (!text) return null;
        const wert = JSON.parse(text) as Partial<AbgelegterEntwurf>;
        if (typeof wert.baseSeq !== "number" || typeof wert.entwurf !== "object" || !wert.entwurf) {
          return null;
        }
        return {
          baseSeq: wert.baseSeq,
          entwurf: entwurfAus(wert.entwurf as unknown as Rohwerte),
          unterwegs: typeof wert.unterwegs === "object" ? wert.unterwegs : null,
        };
      } catch {
        return null;
      }
    },
    schreiben: (wert) => {
      try {
        if (wert) globalThis.sessionStorage?.setItem(schluessel, JSON.stringify(wert));
        else globalThis.sessionStorage?.removeItem(schluessel);
      } catch {
        // Kein Speicher (privates Fenster, voll): dann eben ohne Ablage.
      }
    },
  };
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
  ablage?: EntwurfAblage | null;
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
  private readonly ablage: EntwurfAblage | null;
  /** Rohwerte der Sendung, die gerade unterwegs ist (für die Ablage) */
  private unterwegs: Rohwerte | null = null;
  /** Aus der Ablage: Sendung, die vor dem Neuladen unterwegs war und noch ankommen kann */
  private frueherUnterwegs: { baseSeq: number; raw: Rohwerte } | null = null;

  constructor(optionen: SitzungOptionen) {
    this.rohwerte = optionen.rohwerte;
    this.senden = optionen.senden;
    this.automatisch = optionen.automatisch ?? true;
    this.verzoegerungMs = optionen.verzoegerungMs ?? VERZOEGERUNG_MS;
    this.wiederholungMs = optionen.wiederholungMs ?? WIEDERHOLUNG_MS;
    this.uhr = optionen.uhr ?? STANDARD_UHR;
    this.ablage = optionen.ablage ?? null;
    const basis = optionen.basis;
    this.zustand = {
      entwurf: entwurfAus(basis.raw),
      basis,
      phase: "gespeichert",
      ungespeichert: false,
      fehler: null,
      feldFehler: [],
      konflikt: null,
      versuche: 0,
      fremdUebernommen: 0,
      wiederhergestellt: false,
    };
    this.zurueckholen();
  }

  /**
   * Unbestätigte Eingabe aus der Ablage holen. Beruht sie auf dem aktuellen Stand des Servers, wird
   * sie beim `starten` gesendet; hat sich der Stand inzwischen geändert, entscheidet der Mensch
   * (wie bei einem Konflikt). Steht beim Server schon dasselbe, ist nichts zu tun.
   */
  private zurueckholen() {
    if (!this.ablage || !this.automatisch) return;
    const abgelegt = this.ablage.lesen();
    if (!abgelegt) return;
    const basis = this.zustand.basis;
    if (gleicheRohwerte(this.rohwerte(abgelegt.entwurf), basis.raw)) {
      this.ablage.schreiben(null);
      return;
    }
    const offen = basis.status !== "final" && basis.status !== "aborted";
    // Die eigene, beim Neuladen unterbrochene Sendung ist angekommen: Rest darauf aufbauen.
    const eigeneAngekommen =
      abgelegt.unterwegs != null &&
      basis.seq === abgelegt.baseSeq + 1 &&
      gleicheRohwerte(abgelegt.unterwegs, basis.raw);
    const passt = (abgelegt.baseSeq === basis.seq || eigeneAngekommen) && offen;
    // Die unterbrochene Sendung kann auch erst nach dem Neuladen ankommen (409 beim nächsten
    // Senden): merken, um sie dann wiederzuerkennen.
    if (abgelegt.unterwegs != null && abgelegt.baseSeq === basis.seq) {
      this.frueherUnterwegs = { baseSeq: abgelegt.baseSeq, raw: abgelegt.unterwegs };
    }
    this.zustand = {
      ...this.zustand,
      entwurf: abgelegt.entwurf,
      phase: passt ? "wartet" : "konflikt",
      konflikt: passt ? null : basis,
      ungespeichert: true,
      wiederhergestellt: true,
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
    // Ablage: nur bei automatischer Sendung (nicht im Korrekturmodus), nur solange unbestätigt.
    if (this.ablage && this.automatisch) {
      this.ablage.schreiben(
        neu.ungespeichert
          ? { baseSeq: neu.basis.seq, entwurf: neu.entwurf, unterwegs: this.unterwegs }
          : null,
      );
    }
    for (const rueckruf of this.hoerer) rueckruf();
  }

  /** Unbestätigte Eingabe bewusst verwerfen (Wechsel trotz Rückfrage): nicht zurückholen. */
  ablageLeeren() {
    this.timerStoppen();
    this.ablage?.schreiben(null);
  }

  /**
   * Alles, was eingegeben wurde, hat der Server bestätigt: nichts wartet, nichts ist unterwegs.
   * Erst dann darf abgeschlossen werden.
   */
  allesBestaetigt(): boolean {
    return (
      this.zustand.phase === "gespeichert" &&
      !this.zustand.ungespeichert &&
      !this.laeuft &&
      this.timer === null
    );
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

  /**
   * Beim Einblenden und nach `beenden` (React StrictMode baut Effekte doppelt auf): Liegt eine
   * unbestätigte Eingabe vor (z. B. aus der Ablage zurückgeholt), wird sie jetzt gesendet.
   */
  starten() {
    this.beendet = false;
    if (
      this.zustand.ungespeichert &&
      this.zustand.phase !== "konflikt" &&
      this.timer === null &&
      !this.laeuft
    ) {
      this.erneut();
    }
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
      // Wieder genau der Stand des Servers: Feldfehler einer abgelehnten Eingabe gelten nicht mehr.
      if (!this.laeuft) this.setzen({ phase: "gespeichert", fehler: null, feldFehler: [] });
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
    this.unterwegs = raw;
    this.setzen({ phase: "sendet" });
    try {
      const antwort = await this.senden(raw, basis.seq, schluessel);
      this.laeuft = false;
      if (this.beendet) return;
      this.ausstehend = null;
      this.unterwegs = null;
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

  /** Steht beim Server schon genau die eigene Eingabe? Dann gibt es nichts zu entscheiden. */
  private schonBeimServer(stand: ErgebnisStand): boolean {
    return gleicheRohwerte(this.rohwerte(this.zustand.entwurf), stand.raw);
  }

  private fehlerBehandeln(fehler: unknown) {
    if (fehler instanceof SeqKonflikt) {
      this.ausstehend = null;
      this.unterwegs = null;
      if (this.schonBeimServer(fehler.aktuell)) {
        this.uebernehmen(fehler.aktuell);
        return;
      }
      const frueher = this.frueherUnterwegs;
      this.frueherUnterwegs = null;
      if (
        frueher &&
        fehler.aktuell.seq === frueher.baseSeq + 1 &&
        gleicheRohwerte(frueher.raw, fehler.aktuell.raw) &&
        fehler.aktuell.status !== "final" &&
        fehler.aktuell.status !== "aborted"
      ) {
        // Eigene Sendung von vor dem Neuladen ist angekommen: darauf aufbauen und erneut senden.
        this.setzen({ basis: fehler.aktuell, fehler: null });
        this.planen(0);
        return;
      }
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
    this.unterwegs = null;
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
    this.unterwegs = null;
    this.setzen({
      basis: stand,
      entwurf: entwurfAus(stand.raw),
      phase: "gespeichert",
      fehler: null,
      feldFehler: [],
      konflikt: null,
      versuche: 0,
      wiederhergestellt: false,
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
    if (this.schonBeimServer(stand)) {
      this.uebernehmen(stand);
      return;
    }
    const frueher = this.frueherUnterwegs;
    if (
      frueher &&
      stand.seq === frueher.baseSeq + 1 &&
      gleicheRohwerte(frueher.raw, stand.raw) &&
      stand.status !== "final" &&
      stand.status !== "aborted"
    ) {
      // Eigene Sendung von vor dem Neuladen ist angekommen: Rest darauf aufbauen.
      this.frueherUnterwegs = null;
      this.ausstehend = null;
      this.setzen({ basis: stand, fehler: null });
      this.planen(0);
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
