import type { FeldFehler } from "../../../api/client";
import type { Anzeige, AnzeigeKonfig, Szene, SzenenArt } from "../typen";

/** Was die Verwaltung bearbeitet und mit einem Knopf speichert. */
export interface Entwurf {
  tournament_id: string | null;
  device_id: string | null;
  konfig: AnzeigeKonfig;
}

export const SZENEN_ARTEN: readonly SzenenArt[] = [
  "live_ranking",
  "startlist",
  "winners",
  "range",
  "notice",
];

const ID_STAMM: Record<SzenenArt, string> = {
  live_ranking: "live-wertung",
  startlist: "startliste",
  winners: "siegerliste",
  range: "stand",
  notice: "hinweis",
};

/** Szene mit allen Feldern, auch denen, die der Server mit Standardwerten auffüllen würde. */
export function vollstaendigeSzene(szene: Szene): Szene {
  const titel = szene.title ?? null;
  switch (szene.kind) {
    case "live_ranking":
      return {
        ...szene,
        title: titel,
        competition_ids: szene.competition_ids ?? [],
        class_ids: szene.class_ids ?? [],
      };
    case "startlist":
      return {
        ...szene,
        title: titel,
        competition_ids: szene.competition_ids ?? [],
        range_ids: szene.range_ids ?? [],
      };
    case "winners":
      return {
        ...szene,
        title: titel,
        competition_ids: szene.competition_ids ?? [],
        class_ids: szene.class_ids ?? [],
      };
    case "notice":
      return { ...szene, title: titel, text: szene.text ?? "" };
    case "range":
      return { ...szene, title: titel };
  }
}

export function konfigNormal(konfig: AnzeigeKonfig): AnzeigeKonfig {
  return {
    scenes: (konfig.scenes ?? []).map(vollstaendigeSzene),
    name_mode: konfig.name_mode,
    show_club: konfig.show_club === true ? "as_person" : konfig.show_club,
    ticker: konfig.ticker?.trim() ? konfig.ticker : null,
    show_backup_warning: konfig.show_backup_warning ?? null,
    show_provisional_note: konfig.show_provisional_note,
    theme: konfig.theme,
  };
}

export function entwurfAus(anzeige: Anzeige): Entwurf {
  return {
    tournament_id: anzeige.tournament_id,
    device_id: anzeige.device_id,
    konfig: konfigNormal(anzeige.config),
  };
}

/** Gleich im Sinne des Servers (normalisiert, z. B. leere Laufzeile = keine). */
export function gleicherEntwurf(a: Entwurf, b: Entwurf): boolean {
  return (
    a.tournament_id === b.tournament_id &&
    a.device_id === b.device_id &&
    JSON.stringify(konfigNormal(a.konfig)) === JSON.stringify(konfigNormal(b.konfig))
  );
}

/** Freie ID für eine neue Szene: `startliste`, sonst `startliste-2`, `startliste-3` … */
export function neueSzenenId(art: SzenenArt, vorhandene: readonly string[]): string {
  const stamm = ID_STAMM[art];
  if (!vorhandene.includes(stamm)) return stamm;
  let nr = 2;
  while (vorhandene.includes(`${stamm}-${nr}`)) nr += 1;
  return `${stamm}-${nr}`;
}

/** Neue Szene mit den Standardwerten des Servers. Die Standanzeige braucht einen Stand. */
export function neueSzene(
  art: SzenenArt,
  vorhandene: readonly string[],
  standId: string | null,
  ueberschrift: string,
): Szene {
  const id = neueSzenenId(art, vorhandene);
  const basis = { id, seconds: 20, title: null };
  switch (art) {
    case "live_ranking":
      return {
        ...basis,
        kind: art,
        competition_ids: [],
        class_ids: [],
        rows: 10,
        show_running: true,
        show_aborted: false,
      };
    case "startlist":
      return {
        ...basis,
        seconds: 15,
        kind: art,
        competition_ids: [],
        range_ids: [],
        rows: 12,
        include_finished: false,
      };
    case "winners":
      return {
        ...basis,
        kind: art,
        competition_ids: [],
        class_ids: [],
        top: 3,
        include_provisional: true,
        show_aborted: false,
      };
    case "range":
      return { ...basis, kind: art, range_id: standId ?? "", next_count: 4, show_procedure: true };
    case "notice":
      return { ...basis, kind: art, heading: ueberschrift, text: "" };
  }
}

/** Turnier und Inhalt in einem `PATCH /displays/{id}`. */
export interface AnzeigeAenderung {
  tournament_id?: string | null;
  config?: AnzeigeKonfig;
}

/** Ein Schritt beim Speichern: Turnier und Inhalt zusammen, das Gerät für sich. */
export type SpeicherSchritt =
  | { art: "anzeige"; aenderung: AnzeigeAenderung }
  | { art: "geraet"; wert: string | null };

/**
 * Was beim Speichern an den Server geht. Turnier und Szenen gehen in einer Anfrage
 * (`PATCH` mit `config`); der Server prüft die Szenen gegen das neue Turnier. Das Gerät hat einen
 * eigenen Endpunkt und kommt danach.
 */
export function speicherSchritte(server: Entwurf, entwurf: Entwurf): SpeicherSchritt[] {
  const schritte: SpeicherSchritt[] = [];
  const aenderung: AnzeigeAenderung = {};
  if (server.tournament_id !== entwurf.tournament_id) {
    aenderung.tournament_id = entwurf.tournament_id;
  }
  const konfig = konfigNormal(entwurf.konfig);
  if (JSON.stringify(konfigNormal(server.konfig)) !== JSON.stringify(konfig)) {
    aenderung.config = konfig;
  }
  if (Object.keys(aenderung).length > 0) schritte.push({ art: "anzeige", aenderung });
  if (server.device_id !== entwurf.device_id) {
    schritte.push({ art: "geraet", wert: entwurf.device_id });
  }
  return schritte;
}

/** Was die Vorschau an den Server schickt: der Entwurf, ohne ihn zu speichern. */
export function vorschauAnfrage(entwurf: Entwurf): {
  config: AnzeigeKonfig;
  tournament_id: string | null;
} {
  return { config: konfigNormal(entwurf.konfig), tournament_id: entwurf.tournament_id };
}

/** Feldpfad des Servers ohne `config.`-Vorsilbe: `config.scenes.0.rows` → `scenes.0.rows`. */
export function feldOhneKonfig(feld: string): string {
  return feld.startsWith("config.") ? feld.slice("config.".length) : feld;
}

/** Meldungen zu einem Feld und allem darunter (`scenes.2` trifft `scenes.2.competition_ids.0`). */
export function fehlerZu(felder: readonly FeldFehler[], pfad: string): string | undefined {
  const treffer = felder
    .filter((fehler) => {
      const feld = feldOhneKonfig(fehler.feld);
      return feld === pfad || feld.startsWith(`${pfad}.`);
    })
    .map((fehler) => fehler.meldung);
  return treffer.length > 0 ? [...new Set(treffer)].join(" · ") : undefined;
}

/** Meldungen, die keinem bekannten Feld zuzuordnen sind (oben über dem Formular zeigen). */
export function uebrigeFehler(
  felder: readonly FeldFehler[],
  bekannt: (feld: string) => boolean,
): string[] {
  return felder.filter((fehler) => !bekannt(feldOhneKonfig(fehler.feld))).map((f) => f.meldung);
}
