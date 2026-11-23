import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BEGRIFFE_RUECKFALL, type Begriffe, type Begriffssaetze } from "../../../lib/begriffe";
import { beispielTurnier, TURNIER_ID } from "../testdaten";
import { Blatt } from "./Blatt";
import { dokumentAusEntwurf, druckModell } from "./dokument";
import type { AusschreibungDokument, DokumentWettbewerb } from "./typen";

/** Wörter wie in `backend/app/core/begriffe/*.yaml` (nur die hier gebrauchten unterscheiden sich). */
const BDS: Begriffe = { ...BEGRIFFE_RUECKFALL, gebuehr_einspruch: "Protestgebühr" };
const DSB: Begriffe = {
  ...BEGRIFFE_RUECKFALL,
  gebuehr_einspruch: "Einspruchsgebühr",
  kennziffer: "Kennzahl",
  klasse: "Wettkampfklasse",
};

function wettbewerb(id: string, verband: string, terms?: Begriffe): DokumentWettbewerb {
  return {
    id,
    name: `Wettbewerb ${id}`,
    catalog_federation: verband,
    catalog_code: id === "d1" ? "1.10" : "4403",
    group: null,
    range_name: "Schießstand 25 m",
    procedure: null,
    sections: [],
    multi_start: false,
    max_starts: 1,
    multi_start_rule: "best",
    multi_start_text: "Ein Start je Teilnehmer",
    terms,
  };
}

function dokument(
  wettbewerbe: DokumentWettbewerb[],
  terms: Begriffe | undefined,
  ranges: NonNullable<AusschreibungDokument["blocks"][number]["ranges"]>,
): AusschreibungDokument {
  return {
    title: "Ausschreibung Herbstpokal",
    tournament: {
      id: TURNIER_ID,
      name: "Herbstpokal",
      organizer: null,
      date_from: "2026-12-05",
      date_to: "2026-12-05",
      status: "draft",
      currency: "EUR",
    },
    facts: {},
    blocks: [
      {
        id: "w",
        kind: "competitions",
        heading: "Wettbewerbe",
        body: "",
        competitions: wettbewerbe,
      },
      {
        id: "f",
        kind: "fees",
        heading: "Startgeld",
        body: "",
        fees: {
          currency: "EUR",
          items: wettbewerbe.map((w) => ({
            competition_id: w.id,
            name: w.name,
            fee_first_cents: 800,
            fee_repeat_cents: null,
          })),
        },
      },
      { id: "s", kind: "ranges", heading: "Schießstände", body: "", ranges },
      // Freitext des Veranstalters bleibt, wie er ist – auch mit anderem Wort.
      { id: "e", kind: "text", heading: "Einsprüche", body: "Einspruchsgebühr 25 Euro." },
    ],
    terms,
  };
}

function spaltenkoepfe() {
  const tabelle = screen.getAllByRole("table")[0] as HTMLElement;
  return within(tabelle)
    .getAllByRole("columnheader")
    .map((kopf) => kopf.textContent);
}

describe("Ausschreibung: formelle Wörter aus den Begriffen", () => {
  it("DSB: Kennzahl in der Wettbewerbstabelle, lanes_text des Servers am Schießstand", () => {
    const modell = druckModell(
      dokument([wettbewerb("d1", "dsb", DSB)], DSB, [
        { name: "Schießstand 10 m", lane_count: 1, lanes_text: "1 Schützenstand" },
      ]),
      "de",
    );
    render(<Blatt modell={modell} erstellt={new Date("2026-11-23T10:00:00")} />);
    expect(spaltenkoepfe()).toEqual([
      "Kennzahl",
      "Wettbewerb",
      "Ablauf",
      "Schießstand",
      "Startgeld / Nachkauf",
    ]);
    expect(screen.getByText("Schießstand 10 m (1 Schützenstand)")).toBeInTheDocument();
    expect(modell.begriffe.gebuehr_einspruch).toBe("Einspruchsgebühr");
    // Freitext unverändert
    expect(screen.getByText("Einspruchsgebühr 25 Euro.")).toBeInTheDocument();
  });

  it("BDS: Kennziffer, Protestgebühr; Freitext mit anderem Wort bleibt", () => {
    const modell = druckModell(
      dokument([wettbewerb("b1", "bds", BDS)], BDS, [
        { name: "Schießstand 25 m", lane_count: 6, lanes_text: "6 Schützenstände" },
      ]),
      "de",
    );
    render(<Blatt modell={modell} erstellt={new Date("2026-11-23T10:00:00")} />);
    expect(spaltenkoepfe()[0]).toBe("Kennziffer");
    expect(screen.getByText("Schießstand 25 m (6 Schützenstände)")).toBeInTheDocument();
    expect(modell.begriffe.gebuehr_einspruch).toBe("Protestgebühr");
    expect(screen.getByText("Einspruchsgebühr 25 Euro.")).toBeInTheDocument();
  });

  it("gemischt: Spaltenkopf aus dem Dokument-Satz, wenn die Wettbewerbe verschiedene Wörter nennen", () => {
    const modell = druckModell(
      dokument(
        [wettbewerb("b1", "bds", BDS), wettbewerb("d1", "dsb", DSB)],
        BEGRIFFE_RUECKFALL,
        [],
      ),
      "de",
    );
    const tabelle = modell.bausteine.find((b) => b.art === "wettbewerbe");
    expect(tabelle?.art === "wettbewerbe" && tabelle.spalten.kennziffer).toBe("Kennziffer");
  });

  it("Rückfall: ohne terms und lanes_text die bisherigen festen Wörter", () => {
    const modell = druckModell(
      dokument([wettbewerb("b1", "bds")], undefined, [
        { name: "Schießstand 25 m", lane_count: 2 },
        { name: "Schießstand 50 m", lane_count: 1, lanes_text: "" },
      ]),
      "de",
    );
    render(<Blatt modell={modell} erstellt={new Date("2026-11-23T10:00:00")} />);
    expect(spaltenkoepfe()).toEqual([
      "Kennziffer",
      "Wettbewerb",
      "Ablauf",
      "Schießstand",
      "Startgeld / Nachkauf",
    ]);
    expect(screen.getByText("Schießstand 25 m (2 Schützenstände)")).toBeInTheDocument();
    expect(screen.getByText("Schießstand 50 m (1 Schützenstand)")).toBeInTheDocument();
    expect(modell.begriffe.gebuehr_einspruch).toBe("Protestgebühr");
  });

  it("Rückfall je Schlüssel: ein fehlendes oder leeres Wort ersetzt der feste Text", () => {
    const { kennziffer: _weg, ...ohneKennziffer } = DSB;
    const modell = druckModell(
      dokument(
        [wettbewerb("d1", "dsb", { ...DSB, schiessstand: " " })],
        ohneKennziffer as Begriffe,
        [],
      ),
      "de",
    );
    const tabelle = modell.bausteine.find((b) => b.art === "wettbewerbe");
    if (tabelle?.art !== "wettbewerbe") throw new Error("Wettbewerbe fehlen");
    // Der Wettbewerb nennt „Kennzahl“, das Dokument nicht: das Wort des Wettbewerbs gilt.
    expect(tabelle.spalten.kennziffer).toBe("Kennzahl");
    expect(tabelle.spalten.schiessstand).toBe("Schießstand");
    expect(modell.begriffe.kennziffer).toBe("Kennziffer");
  });

  it("Vorschau ohne Server-Dokument: Begriffe aus GET /terms nach Verband", () => {
    const saetze: Begriffssaetze = {
      default: BEGRIFFE_RUECKFALL,
      federations: { bds: BDS, dsb: DSB },
    };
    const turnier = beispielTurnier();
    const dsbTurnier = {
      ...turnier,
      competitions: turnier.competitions.map((w) => ({ ...w, catalog_federation: "dsb" })),
    };
    const entwurf = {
      title: null,
      facts: {},
      blocks: [
        { id: "w", kind: "competitions" as const, heading: "", body: "", visible: true },
        { id: "s", kind: "ranges" as const, heading: "", body: "", visible: true },
      ],
    };
    const doc = dokumentAusEntwurf(entwurf, dsbTurnier, null, "de", saetze);
    expect(doc.terms?.gebuehr_einspruch).toBe("Einspruchsgebühr");
    expect(doc.blocks[0]?.competitions?.[0]?.terms?.kennziffer).toBe("Kennzahl");
    expect(doc.blocks[1]?.ranges?.[0]?.lanes_text).toBe("2 Schützenstände");

    // Mit Server-Dokument gelten dessen Wörter.
    const server = { ...doc, terms: BDS };
    expect(dokumentAusEntwurf(entwurf, dsbTurnier, server, "de", saetze).terms).toBe(BDS);
  });
});
