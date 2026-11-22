import { Button, MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { theme } from "../theme";
import { Dialog } from "./Dialog";

/** Wie in den Modulen: Der Dialog wird nur gerendert, solange er offen ist. */
function Beispiel() {
  const [offen, setOffen] = useState(false);
  return (
    <>
      <Button onClick={() => setOffen(true)}>Turnier anlegen</Button>
      {offen && (
        <Dialog onClose={() => setOffen(false)} title="Neues Turnier">
          <Button onClick={() => setOffen(false)}>Abbrechen</Button>
        </Dialog>
      )}
    </>
  );
}

function oeffnen() {
  render(
    <MantineProvider theme={theme}>
      <Beispiel />
    </MantineProvider>,
  );
  return screen.getByRole("button", { name: "Turnier anlegen" });
}

describe("Dialog", () => {
  it("gibt dem Schließen-Knopf einen Namen", async () => {
    const user = userEvent.setup();
    await user.click(oeffnen());
    expect(
      await screen.findByRole("button", { name: "Dialog schließen, ohne etwas zu ändern" }),
    ).toBeInTheDocument();
  });

  it("gibt den Fokus nach Esc an den Auslöser zurück", async () => {
    const user = userEvent.setup();
    const ausloeser = oeffnen();
    ausloeser.focus();
    await user.keyboard("{Enter}");
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(ausloeser).toHaveFocus());
  });

  it("gibt den Fokus nach „Abbrechen“ an den Auslöser zurück", async () => {
    const user = userEvent.setup();
    const ausloeser = oeffnen();
    ausloeser.focus();
    await user.keyboard("{Enter}");
    await user.click(await screen.findByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(ausloeser).toHaveFocus());
  });
});
