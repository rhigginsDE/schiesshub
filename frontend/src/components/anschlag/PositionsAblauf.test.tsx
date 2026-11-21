import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PositionsAblauf } from "./PositionsAblauf";
import type { Position } from "./typen";

const parcours: Position[] = [
  { nr: 5, distanz_m: 20, anschlaege: [{ haltung: "stehend", hand: "beidhaendig" }], scheibe: 1 },
  {
    nr: 6,
    distanz_m: 15,
    anschlaege: [
      { haltung: "kniend", hand: "beidhaendig" },
      { haltung: "stehend", hand: "schwache_hand" },
    ],
    scheibe: 2,
  },
  { nr: 7, distanz_m: 10, anschlaege: [{ haltung: "stehend", hand: "beidhaendig" }], scheibe: 3 },
  { nr: 8, distanz_m: 5, anschlaege: [{ haltung: "stehend", hand: "einhaendig" }], scheibe: 4 },
];

describe("PositionsAblauf", () => {
  it("zeigt je Position Distanz, Anschlag in Klartext und Scheibe", () => {
    render(<PositionsAblauf label="Parcours" positionen={parcours} schussJeSerie={5} />);

    const liste = screen.getByRole("list", { name: "Parcours" });
    const eintraege = within(liste).getAllByRole("listitem");
    expect(eintraege).toHaveLength(4);

    const pos6 = eintraege[1] as HTMLElement;
    expect(within(pos6).getByText("Pos. 6")).toBeInTheDocument();
    expect(within(pos6).getByText("15 m")).toBeInTheDocument();
    expect(
      within(pos6).getByText("kniend, beidhändig oder stehend, nur schwache Hand"),
    ).toBeInTheDocument();
    expect(within(pos6).getByText("Scheibe 2")).toBeInTheDocument();
    // beide erlaubten Anschläge als Bild mit zugänglichem Namen
    expect(within(pos6).getByRole("img", { name: "kniend, beidhändig" })).toBeInTheDocument();
    expect(
      within(pos6).getByRole("img", { name: "stehend, nur schwache Hand" }),
    ).toBeInTheDocument();

    const pos8 = eintraege[3] as HTMLElement;
    expect(within(pos8).getByText("stehend, einhändig (Hand frei wählbar)")).toBeInTheDocument();
  });

  it("zeigt die Zeit je Serie, wenn keine Scheibe genannt ist, und markiert Trefferaufnahmen", () => {
    const fertigkeit: Position[] = [
      { nr: 1, distanz_m: 5, anschlaege: [{ haltung: "stehend", hand: "schwache_hand" }] },
      { nr: 2, distanz_m: 10, anschlaege: [{ haltung: "stehend", hand: "starke_hand" }] },
    ];
    render(
      <PositionsAblauf
        label="Fertigkeit"
        positionen={fertigkeit}
        zeitJeSerieS={10}
        trefferaufnahmeNach={[2]}
      />,
    );

    expect(screen.getAllByText("10 s")).toHaveLength(2);
    const [pos1, pos2] = screen.getAllByRole("listitem") as [HTMLElement, HTMLElement];
    expect(within(pos1).queryByText("Trefferaufnahme")).not.toBeInTheDocument();
    expect(within(pos2).getAllByText("Trefferaufnahme").length).toBeGreaterThan(0);
  });

  it("streicht Serien über der gewerteten Zahl und hebt die aktive Position hervor", () => {
    render(
      <PositionsAblauf label="Parcours" positionen={parcours} serienGewertet={2} aktivIndex={1} />,
    );

    const eintraege = screen.getAllByRole("listitem");
    expect(eintraege[1]).toHaveAttribute("aria-current", "step");
    expect(eintraege[2]).toHaveAttribute("data-gestrichen");
    expect(eintraege[3]).toHaveAttribute("data-gestrichen");
    expect(eintraege[1]).not.toHaveAttribute("data-gestrichen");
    expect(
      within(eintraege[3] as HTMLElement).getByText("gestrichen – zählt nicht"),
    ).toBeInTheDocument();
  });

  it("zeigt einen Hinweis, z. B. bei Abweichung vom Sporthandbuch", () => {
    render(
      <PositionsAblauf
        label="Parcours"
        positionen={parcours}
        hinweis="Abweichend vom Sporthandbuch"
      />,
    );
    expect(screen.getByText("Abweichend vom Sporthandbuch")).toBeInTheDocument();
  });
});
