import { formatGeld } from "../../../components/geld";
import i18n, { aktiveSprache } from "../../../i18n";
import { formatDatum } from "../../../lib/format";
import { abschnittKurz, startsKurz, zeitraum } from "../klartext";
import type { TurnierUebersicht } from "../typen";
import type {
  Ausschreibung,
  AusschreibungDokument,
  Baustein,
  DokumentBaustein,
  DokumentWettbewerb,
  Eckdaten,
} from "./typen";

/** Text in Absätze: Leerzeilen trennen, einfache Umbrüche bleiben im Absatz. */
export function absaetze(text: string): string[] {
  return text
    .replace(/\r\n/g, "\n")
    .split(/\n\s*\n/)
    .map((teil) => teil.trim())
    .filter(Boolean);
}

/** Ein sichtbarer Text-Baustein ohne Inhalt („noch leer“). */
export function istLeer(baustein: Pick<Baustein, "kind" | "body">): boolean {
  return baustein.kind === "text" && baustein.body.trim() === "";
}

/**
 * Dokument aus dem ungespeicherten Entwurf und den Turnierdaten, wie es der Server zusammensetzen
 * würde (`announcement.py`). Für die Live-Vorschau und als Ersatz, wenn `…/document` fehlt.
 * Abweichungen vom Katalog kennt nur der Server; sie kommen aus `server`, wenn vorhanden.
 */
export function dokumentAusEntwurf(
  entwurf: Ausschreibung,
  turnier: TurnierUebersicht,
  server?: AusschreibungDokument | null,
  sprache: string = aktiveSprache(),
): AusschreibungDokument {
  const waehrung = turnier.settings.currency;
  const standName = new Map(turnier.ranges.map((stand) => [stand.id, stand.name]));
  const serverWettbewerbe = new Map(
    (server?.blocks.find((b) => b.kind === "competitions")?.competitions ?? []).map((w) => [
      w.id,
      w,
    ]),
  );

  const wettbewerbe = (): DokumentWettbewerb[] =>
    turnier.competitions.map((w) => {
      const vomServer = serverWettbewerbe.get(w.id);
      return {
        id: w.id,
        name: w.name,
        catalog_federation: w.catalog_federation,
        catalog_code: w.catalog_code,
        group: w.definition.source?.group ?? null,
        range_name: w.range_id ? (standName.get(w.range_id) ?? null) : null,
        procedure: w.definition.ablauf_beschreibung ?? null,
        sections: w.definition.variant.abschnitte.map((a) => ({
          name: a.name,
          serien: a.serien,
          schuss_je_serie: a.schuss_je_serie ?? null,
          serien_gewertet: a.serien_gewertet ?? null,
          summary:
            w.definition.variant.abschnitte.length > 1
              ? `${a.name}: ${abschnittKurz(a, sprache)}`
              : abschnittKurz(a, sprache),
        })),
        multi_start: w.multi_start,
        max_starts: w.max_starts,
        multi_start_rule: w.multi_start_rule,
        multi_start_text: startsKurz(w, sprache),
        deviates_from_catalog: vomServer?.deviates_from_catalog ?? false,
        deviations: vomServer?.deviations ?? [],
      };
    });

  const bausteine: DokumentBaustein[] = entwurf.blocks
    .filter((b) => b.visible)
    .map((b) => {
      const eintrag: DokumentBaustein = {
        id: b.id,
        kind: b.kind,
        heading: b.heading,
        body: b.body,
      };
      if (b.kind === "competitions") eintrag.competitions = wettbewerbe();
      if (b.kind === "classes") {
        eintrag.classes = turnier.classes.map((k) => ({ name: k.name, short: k.short }));
      }
      if (b.kind === "fees") {
        eintrag.fees = {
          currency: waehrung,
          items: turnier.competitions.map((w) => ({
            competition_id: w.id,
            name: w.name,
            fee_first_cents: w.fee_first_cents,
            fee_repeat_cents: w.multi_start ? w.fee_repeat_cents : null,
          })),
        };
      }
      if (b.kind === "dates") {
        eintrag.dates = {
          date_from: turnier.date_from,
          date_to: turnier.date_to,
          registration_deadline: entwurf.facts.registration_deadline ?? null,
        };
      }
      if (b.kind === "ranges") {
        eintrag.ranges = turnier.ranges.map((r) => ({ name: r.name, lane_count: r.lane_count }));
      }
      return eintrag;
    });

  return {
    title:
      entwurf.title?.trim() || `${i18n.t("turnier:ausschreibung.titel_standard")} ${turnier.name}`,
    tournament: {
      id: turnier.id,
      name: turnier.name,
      organizer: turnier.organizer,
      date_from: turnier.date_from,
      date_to: turnier.date_to,
      status: turnier.status,
      currency: waehrung,
    },
    facts: entwurf.facts,
    blocks: bausteine,
  };
}

// --- Druckmodell -------------------------------------------------------------------------------

export interface Zeile {
  bezeichnung: string;
  text: string;
}

export interface DruckWettbewerb {
  kennziffer: string;
  name: string;
  ablauf: string;
  starts: string;
  stand: string;
  startgeld: string | null;
  abweichend: boolean;
  abweichungen: string[];
}

interface DruckBasis {
  id: string;
  ueberschrift: string;
  absaetze: string[];
}

export type DruckBaustein = DruckBasis &
  (
    | { art: "text" }
    | { art: "wettbewerbe"; wettbewerbe: DruckWettbewerb[]; mitGeld: boolean }
    | { art: "klassen"; klassen: string[] }
    | { art: "gebuehren"; zeilen: { name: string; startgeld: string; nachkauf: string | null }[] }
    | { art: "termine"; zeilen: Zeile[] }
    | { art: "staende"; zeilen: string[] }
  );

export interface DruckModell {
  titel: string;
  turnier: string;
  veranstalter: string | null;
  zeitraum: string;
  eckdaten: Zeile[];
  bausteine: DruckBaustein[];
}

function eckdatenZeilen(eckdaten: Eckdaten, sprache: string): Zeile[] {
  const t = i18n.getFixedT(sprache, "turnier", "ausschreibung.eckdaten");
  const zeilen: Zeile[] = [];
  const dazu = (feld: keyof Eckdaten, text: string | null | undefined) => {
    if (text?.trim()) zeilen.push({ bezeichnung: t(feld), text: text.trim() });
  };
  dazu("venue", eckdaten.venue);
  dazu("address", eckdaten.address);
  dazu(
    "registration_deadline",
    eckdaten.registration_deadline ? formatDatum(eckdaten.registration_deadline, sprache) : null,
  );
  dazu("registration_info", eckdaten.registration_info);
  const kontakt = [eckdaten.contact_name, eckdaten.contact_info]
    .map((teil) => teil?.trim())
    .filter(Boolean)
    .join(", ");
  dazu("contact_name", kontakt);
  return zeilen;
}

/**
 * Aus dem Dokument wird, was gedruckt wird: leere Text-Bausteine fallen weg, automatische Bausteine
 * ohne Daten und ohne Zusatztext ebenso; Geld und Datum stehen fertig formatiert da.
 */
export function druckModell(
  dokument: AusschreibungDokument,
  sprache: string = aktiveSprache(),
): DruckModell {
  const t = i18n.getFixedT(sprache, "turnier", "ausschreibung");
  const waehrung = dokument.tournament.currency;
  const geld = (cent: number) => formatGeld(cent, waehrung, sprache);
  const gebuehren = new Map(
    (dokument.blocks.find((b) => b.kind === "fees")?.fees?.items ?? []).map((g) => [
      g.competition_id,
      g,
    ]),
  );

  const bausteine: DruckBaustein[] = [];
  for (const b of dokument.blocks) {
    const basis = { id: b.id, ueberschrift: b.heading.trim(), absaetze: absaetze(b.body) };
    if (b.kind === "text") {
      if (basis.absaetze.length > 0) bausteine.push({ ...basis, art: "text" });
      continue;
    }
    if (b.kind === "competitions") {
      const liste = b.competitions ?? [];
      if (liste.length === 0 && basis.absaetze.length === 0) continue;
      bausteine.push({
        ...basis,
        art: "wettbewerbe",
        mitGeld: gebuehren.size > 0,
        wettbewerbe: liste.map((w) => {
          const g = gebuehren.get(w.id);
          return {
            kennziffer: w.catalog_code ?? "",
            name: w.name,
            ablauf: w.sections.map((a) => a.summary).join("; "),
            starts: w.multi_start_text,
            stand: w.range_name ?? "",
            startgeld: g
              ? g.fee_repeat_cents !== null
                ? `${geld(g.fee_first_cents)} / ${geld(g.fee_repeat_cents)}`
                : geld(g.fee_first_cents)
              : null,
            abweichend: w.deviates_from_catalog,
            abweichungen: w.deviations,
          };
        }),
      });
      continue;
    }
    if (b.kind === "classes") {
      const klassen = (b.classes ?? []).map((k) => `${k.name} (${k.short})`);
      if (klassen.length === 0 && basis.absaetze.length === 0) continue;
      bausteine.push({ ...basis, art: "klassen", klassen });
      continue;
    }
    if (b.kind === "fees") {
      const zeilen = (b.fees?.items ?? []).map((g) => ({
        name: g.name,
        startgeld: geld(g.fee_first_cents),
        nachkauf: g.fee_repeat_cents !== null ? geld(g.fee_repeat_cents) : null,
      }));
      if (zeilen.length === 0 && basis.absaetze.length === 0) continue;
      bausteine.push({ ...basis, art: "gebuehren", zeilen });
      continue;
    }
    if (b.kind === "dates") {
      const zeilen: Zeile[] = [];
      if (b.dates) {
        zeilen.push({
          bezeichnung: t("termine.turnier"),
          text: zeitraum({ date_from: b.dates.date_from, date_to: b.dates.date_to }, sprache),
        });
        if (b.dates.registration_deadline) {
          zeilen.push({
            bezeichnung: t("termine.meldeschluss"),
            text: formatDatum(b.dates.registration_deadline, sprache),
          });
        }
      }
      bausteine.push({ ...basis, art: "termine", zeilen });
      continue;
    }
    if (b.kind === "ranges") {
      const zeilen = (b.ranges ?? []).map((r) =>
        t("staende.zeile", { name: r.name, count: r.lane_count }),
      );
      if (zeilen.length === 0 && basis.absaetze.length === 0) continue;
      bausteine.push({ ...basis, art: "staende", zeilen });
    }
  }

  return {
    titel: dokument.title,
    turnier: dokument.tournament.name,
    veranstalter: dokument.tournament.organizer,
    zeitraum: zeitraum(dokument.tournament, sprache),
    eckdaten: eckdatenZeilen(dokument.facts, sprache),
    bausteine,
  };
}
