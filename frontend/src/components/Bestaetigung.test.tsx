import { MantineProvider, TextInput } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { theme } from "../theme";
import { Bestaetigung } from "./Bestaetigung";

describe("Bestaetigung", () => {
  it("setzt den Fokus beim Öffnen auf den sicheren Knopf, nicht auf das Eingabefeld", async () => {
    render(
      <MantineProvider theme={theme}>
        <Bestaetigung
          offen
          titel="Turnier löschen?"
          text="Das lässt sich nicht rückgängig machen."
          bestaetigen="Löschen"
          abbrechen="Behalten"
          ton="gefahr"
          onSchliessen={vi.fn()}
          onBestaetigen={vi.fn()}
        >
          <TextInput label="Grund" />
        </Bestaetigung>
      </MantineProvider>,
    );
    const behalten = await screen.findByRole("button", { name: "Behalten" });
    await waitFor(() => expect(behalten).toHaveFocus());
  });
});
