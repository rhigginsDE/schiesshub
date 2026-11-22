import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  BRANDT,
  KOEHLER,
  MAIER,
  renderAnsicht,
  serverAttrappe,
} from "../modules/teilnehmer/testhilfe";
import { PersonenSuche } from "./PersonenSuche";

describe("PersonenSuche", () => {
  it("meldet die Auswahl, wandert mit Pfeiltasten und schlägt den Suchtext als Namen vor", async () => {
    const aufrufe = serverAttrappe({
      "GET /persons?limit=50": { inhalt: [BRANDT, MAIER, KOEHLER] },
      "GET /persons?q=Erika+Neu&limit=50": { inhalt: [], kopf: { "X-Total-Count": "0" } },
    });
    const onAuswahl = vi.fn();
    const onNeu = vi.fn();
    renderAnsicht(() => <PersonenSuche onAuswahl={onAuswahl} onNeu={onNeu} />);

    const feld = await screen.findByRole("searchbox", { name: "Person suchen" });
    await screen.findByText("Markus Brandt");
    // Enter im leeren Feld öffnet niemanden, sondern springt nur in die Liste.
    await userEvent.click(feld);
    await userEvent.keyboard("{Enter}");
    expect(onAuswahl).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Markus Brandt/ })).toHaveFocus();

    await userEvent.click(feld);
    await userEvent.keyboard("{ArrowDown}{ArrowDown}{Enter}");
    expect(onAuswahl).toHaveBeenCalledWith(MAIER);

    await userEvent.click(feld);
    await userEvent.type(feld, "  Erika Neu ");
    expect(await screen.findByText("Keine Person gefunden")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "„Erika Neu“ neu anlegen" }));
    expect(onNeu).toHaveBeenCalledWith("Erika Neu");

    // Esc leert die Suche; der Suchtext landet nur in der Anfrage, nie in der Adresse.
    await userEvent.click(feld);
    await userEvent.keyboard("{Escape}");
    expect(feld).toHaveValue("");
    expect(window.location.search).toBe("");
    expect(aufrufe.some((a) => a.pfad.includes("q=Erika"))).toBe(true);
  });
});
