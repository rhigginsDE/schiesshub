import { screen } from "@testing-library/react";
import { UserPlus } from "lucide-react";
import { describe, expect, it } from "vitest";
import { renderAnsicht } from "../teilnehmer/testhilfe";
import { AnmeldungSeite } from "./AnmeldungSeite";

describe("Station Anmeldung", () => {
  it("zeigt den Bereich Teilnehmer und sagt ehrlich, dass Starts buchen noch folgt", async () => {
    renderAnsicht(() => <AnmeldungSeite station="anmeldung" icon={UserPlus} />);
    expect(await screen.findByRole("heading", { name: "Anmeldung" })).toBeInTheDocument();
    expect(screen.getByText(/Starts buchen und kassieren folgt noch/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Teilnehmer/ })).toHaveAttribute(
      "href",
      "/anmeldung/teilnehmer",
    );
  });
});
