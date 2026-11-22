import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASIS, type ApiFehlerArt, artAusStatus } from "../../../api/client";
import { EREIGNIS_VERBUNDEN } from "../../../api/ereignisse";
import { ereignisseZumNachladen } from "../ereignisse";
import type { Feed } from "../typen";

/** Woher der Bildschirm seinen Feed holt. */
export type FeedQuelle = { art: "geraet" } | { art: "anzeige"; id: string };

export function feedPfad(quelle: FeedQuelle): string {
  return quelle.art === "geraet"
    ? "/displays/mine/feed"
    : `/displays/${encodeURIComponent(quelle.id)}/feed`;
}

/** Fehler, bei denen kein Feed mehr gezeigt wird (der Bildschirm sagt, was zu tun ist). */
export type SperrFehler = Extract<ApiFehlerArt, "nicht_angemeldet" | "verboten" | "nicht_gefunden">;

export interface FeedZustand {
  feed: Feed | null;
  /** Erster Abruf läuft noch */
  laedt: boolean;
  sperre: SperrFehler | null;
  /** Server nicht erreichbar seit (Geräteuhr); der letzte Stand bleibt stehen */
  getrenntSeit: Date | null;
  /** Serverzeit minus Geräteuhr in Millisekunden; damit läuft die Uhr nach dem Server */
  versatzMs: number;
  neuLaden: () => void;
}

const WIEDERHOLEN_MS = 5000;
const SPERRE_PRUEFEN_MS = 15000;
const STANDARD_POLL_S = 60;
const ENTPRELLEN_MS = 300;

function istSperre(art: ApiFehlerArt): art is SperrFehler {
  return art === "nicht_angemeldet" || art === "verboten" || art === "nicht_gefunden";
}

function versatzAus(serverZeit: string | null | undefined): number | null {
  if (!serverZeit) return null;
  const ms = Date.parse(serverZeit);
  return Number.isNaN(ms) ? null : ms - Date.now();
}

/**
 * Lädt den Feed einer Anzeige und hält ihn aktuell: mit ETag (`If-None-Match`, 304 = unverändert),
 * neu bei den Server-Ereignissen aus `reload_on` und spätestens nach `poll_seconds`. Ist der Server
 * weg, bleibt der letzte Stand stehen und `getrenntSeit` ist gesetzt; der Hook versucht es weiter.
 */
export function useFeed(quelle: FeedQuelle): FeedZustand {
  const pfad = feedPfad(quelle);
  const [feed, setFeed] = useState<Feed | null>(null);
  const [laedt, setLaedt] = useState(true);
  const [sperre, setSperre] = useState<SperrFehler | null>(null);
  const [getrenntSeit, setGetrenntSeit] = useState<Date | null>(null);
  const [versatzMs, setVersatzMs] = useState(0);

  const etag = useRef<string | null>(null);
  const pollSekunden = useRef(STANDARD_POLL_S);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const laufend = useRef<AbortController | null>(null);
  const ladenRef = useRef<() => void>(() => {});

  const planen = useCallback((ms: number) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => ladenRef.current(), ms);
  }, []);

  const laden = useCallback(async () => {
    laufend.current?.abort();
    const steuerung = new AbortController();
    laufend.current = steuerung;
    const kopf: Record<string, string> = { Accept: "application/json" };
    if (etag.current) kopf["If-None-Match"] = etag.current;
    try {
      const antwort = await fetch(`${API_BASIS}${pfad}`, {
        headers: kopf,
        cache: "no-store",
        signal: steuerung.signal,
      });
      if (antwort.status === 304) {
        const versatz = versatzAus(antwort.headers.get("Date"));
        if (versatz !== null) setVersatzMs(versatz);
        setGetrenntSeit(null);
        planen(pollSekunden.current * 1000);
        return;
      }
      if (!antwort.ok) {
        const art = artAusStatus(antwort.status);
        if (istSperre(art)) {
          etag.current = null;
          setFeed(null);
          setSperre(art);
          setGetrenntSeit(null);
          planen(SPERRE_PRUEFEN_MS);
        } else {
          setGetrenntSeit((alt) => alt ?? new Date());
          planen(WIEDERHOLEN_MS);
        }
        return;
      }
      const neu = (await antwort.json()) as Feed;
      etag.current = antwort.headers.get("ETag") ?? `"${neu.version}"`;
      pollSekunden.current = neu.poll_seconds > 0 ? neu.poll_seconds : STANDARD_POLL_S;
      const versatz = versatzAus(neu.server_time);
      if (versatz !== null) setVersatzMs(versatz);
      setFeed((alt) => (alt?.version === neu.version ? alt : neu));
      setSperre(null);
      setGetrenntSeit(null);
      planen(pollSekunden.current * 1000);
    } catch (fehler) {
      if (fehler instanceof DOMException && fehler.name === "AbortError") return;
      setGetrenntSeit((alt) => alt ?? new Date());
      planen(WIEDERHOLEN_MS);
    } finally {
      if (laufend.current === steuerung) laufend.current = null;
      setLaedt(false);
    }
  }, [pfad, planen]);

  ladenRef.current = () => void laden();

  // Neue Quelle: von vorn.
  useEffect(() => {
    etag.current = null;
    setFeed(null);
    setSperre(null);
    setLaedt(true);
    void laden();
    return () => {
      clearTimeout(timer.current);
      laufend.current?.abort();
    };
  }, [laden]);

  // Server-Ereignisse: eigene Verbindung, damit genau die Namen aus `reload_on` zählen.
  const namen = feed ? ereignisseZumNachladen(feed.reload_on).join(" ") : "display.changed";
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    let quelleSse: EventSource | null = null;
    let neuVerbinden: ReturnType<typeof setTimeout> | undefined;
    let entprellen: ReturnType<typeof setTimeout> | undefined;
    let beendet = false;
    const nachladen = () => {
      clearTimeout(entprellen);
      entprellen = setTimeout(() => ladenRef.current(), ENTPRELLEN_MS);
    };
    const verbinden = () => {
      if (beendet) return;
      quelleSse = new EventSource(`${API_BASIS}/events`);
      // Nach jedem (Wieder-)Aufbau einmal neu laden: Ereignisse dazwischen sind verloren.
      quelleSse.addEventListener(EREIGNIS_VERBUNDEN, nachladen);
      quelleSse.addEventListener("error", () => {
        // Verbindung weg: sofort prüfen, ob auch der Feed nicht erreichbar ist.
        nachladen();
        if (quelleSse?.readyState === EventSource.CLOSED) {
          clearTimeout(neuVerbinden);
          neuVerbinden = setTimeout(verbinden, WIEDERHOLEN_MS);
        }
      });
      for (const name of namen.split(" ")) {
        if (name) quelleSse.addEventListener(name, nachladen);
      }
    };
    verbinden();
    return () => {
      beendet = true;
      clearTimeout(neuVerbinden);
      clearTimeout(entprellen);
      quelleSse?.close();
    };
  }, [namen]);

  const neuLaden = useCallback(() => ladenRef.current(), []);
  return { feed, laedt, sperre, getrenntSeit, versatzMs, neuLaden };
}
