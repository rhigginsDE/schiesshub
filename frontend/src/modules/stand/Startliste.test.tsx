import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAnsicht, serverAttrappe } from "../teilnehmer/testhilfe";
import type { TurnierUebersicht } from "../turnier/typen";
import { Startliste } from "./Startliste";
import { stationStart } from "./testdaten";

const T = "78a0a62a-fd80-4ef3-876a-3e7ad7a332b6";

const uebersicht = {
  id: T,
  name: "Herbstpokal",
  ranges: [],
  classes: [],
  competitions: [],
} as unknown as TurnierUebersicht;

describe("Startliste am Schießstand", () => {
  it("zeigt die Bemerkung zum Abbruch ruhig am abgebrochenen Start (names=full)", async () => {
    serverAttrappe({
      [`GET /tournaments/${T}/startlist?names=full`]: {
        inhalt: [
          stationStart({
            start_id: "s-1",
            start_number: 7,
            status: "aborted",
            abort_reason: "dnf",
            abort_note: "Waffe defekt",
          }),
          // Bemerkung nur bei abgebrochenen Starts, auch wenn sonst etwas mitkäme.
          stationStart({ start_id: "s-2", start_number: 8, abort_note: "nicht zeigen" }),
        ],
      },
    });
    renderAnsicht(() => <Startliste uebersicht={uebersicht} suche={{}} onSuche={() => {}} />);
    expect(await screen.findByText("Bemerkung: Waffe defekt")).toBeInTheDocument();
    expect(screen.getByText("Aufgegeben")).toBeInTheDocument();
    expect(screen.queryByText(/nicht zeigen/)).not.toBeInTheDocument();
  });
});
