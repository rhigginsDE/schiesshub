import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import type { ImportBericht } from "./api";
import { ImportSeite } from "./ImportSeite";
import { renderAnsicht, serverAttrappe, VEREIN_HUBERTUS, VEREIN_TELL } from "./testhilfe";
import { VereineSeite } from "./VereineSeite";

beforeAll(() => {
  Element.prototype.scrollIntoView ??= () => {};
});

describe("Vereine", () => {
  it("führt zwei Vereine nach klarer Bestätigung zusammen", async () => {
    const doppelt = {
      ...VEREIN_TELL,
      id: "33333333-3333-4333-8333-333333333333",
      name: "Schützenverein Tell",
      short: null,
      person_count: 3,
    };
    const aufrufe = serverAttrappe({
      "GET /clubs": { inhalt: [VEREIN_TELL, doppelt, VEREIN_HUBERTUS] },
      [`POST /clubs/${doppelt.id}/merge`]: { inhalt: { ...VEREIN_TELL, person_count: 5 } },
    });
    renderAnsicht(() => <VereineSeite />);

    expect(await screen.findByText("3 Vereine")).toBeInTheDocument();
    const zeile = screen.getByText("Schützenverein Tell").closest("li") as HTMLElement;
    expect(within(zeile).getByText("3 Personen")).toBeInTheDocument();
    await userEvent.click(within(zeile).getByRole("button", { name: /Zusammenführen/ }));

    const dialog = await screen.findByRole("dialog");
    const ziel = within(dialog).getByPlaceholderText("Zielverein wählen");
    await userEvent.click(ziel);
    await userEvent.keyboard("Muster{ArrowDown}{Enter}");
    expect(
      await within(dialog).findByText(
        "Alle 3 Personen aus „Schützenverein Tell“ gehören danach zu „SV Tell Musterstadt“. „Schützenverein Tell“ wird gelöscht. Das lässt sich nicht rückgängig machen.",
      ),
    ).toBeInTheDocument();
    await userEvent.click(
      within(dialog).getByRole("button", {
        name: "„Schützenverein Tell“ in „SV Tell Musterstadt“ zusammenführen",
      }),
    );
    expect(
      await screen.findByText("„Schützenverein Tell“ ist jetzt Teil von „SV Tell Musterstadt“."),
    ).toBeInTheDocument();
    expect(aufrufe.find((a) => a.methode === "POST")?.inhalt).toEqual({ into_id: VEREIN_TELL.id });
  });

  it("bietet bei einem Verein mit Personen statt Löschen das Zusammenführen an", async () => {
    serverAttrappe({ "GET /clubs": { inhalt: [VEREIN_TELL, VEREIN_HUBERTUS] } });
    renderAnsicht(() => <VereineSeite />);
    const zeile = (await screen.findByText("SSV Hubertus Altdorf")).closest("li") as HTMLElement;
    await userEvent.click(within(zeile).getByRole("button", { name: /Löschen/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/hat noch eine Person/)).toBeInTheDocument();
    expect(
      within(dialog).queryByRole("button", { name: "Verein löschen" }),
    ).not.toBeInTheDocument();
  });

  it("benennt um und meldet einen vergebenen Namen", async () => {
    serverAttrappe({
      "GET /clubs": { inhalt: [VEREIN_TELL, VEREIN_HUBERTUS] },
      [`PATCH /clubs/${VEREIN_HUBERTUS.id}`]: {
        status: 409,
        inhalt: { detail: "Einen Verein mit dem Namen „SV Tell Musterstadt“ gibt es schon." },
      },
    });
    renderAnsicht(() => <VereineSeite />);
    const zeile = (await screen.findByText("SSV Hubertus Altdorf")).closest("li") as HTMLElement;
    await userEvent.click(within(zeile).getByRole("button", { name: /Bearbeiten/ }));
    const feld = screen.getByDisplayValue("SSV Hubertus Altdorf");
    await userEvent.clear(feld);
    await userEvent.type(feld, "SV Tell Musterstadt{Enter}");
    expect(await screen.findByText(/gibt es schon/)).toBeInTheDocument();
  });
});

describe("Import", () => {
  const vorschau: ImportBericht = {
    dry_run: true,
    new: 2,
    duplicate: 1,
    error: 1,
    new_clubs: ["SGi Neustadt 1862"],
    rows: [
      { line: 2, status: "new", message: null, person_id: null },
      {
        line: 3,
        status: "duplicate",
        message: null,
        person_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      },
      { line: 4, status: "error", message: "Der Name fehlt.", person_id: null },
      { line: 5, status: "new", message: null, person_id: null },
    ],
  };
  const csv =
    "Name;Verein\nPetra Lang;SGi Neustadt 1862\nMarkus Brandt;SV Tell Musterstadt\n;SV Tell Musterstadt\nAndreas Wolf;SV Tell Musterstadt\n";

  it("prüft zuerst (dry_run) und importiert erst nach Bestätigung", async () => {
    const aufrufe = serverAttrappe({
      "POST /persons/import?dry_run=true": { inhalt: vorschau },
      "POST /persons/import?dry_run=false": { inhalt: { ...vorschau, dry_run: false } },
    });
    renderAnsicht(() => <ImportSeite />);

    const datei = new File([csv], "personen.csv", { type: "text/csv" });
    await screen.findByRole("region", { name: "Datei wählen" });
    const eingabe = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(eingabe, datei);

    expect(await screen.findByText("Petra Lang")).toBeInTheDocument();
    expect(aufrufe.map((a) => `${a.methode} ${a.pfad}`)).toEqual([
      "POST /persons/import?dry_run=true",
    ]);
    expect(screen.getByText("2 neu")).toBeInTheDocument();
    expect(screen.getByText("1 Dublette")).toBeInTheDocument();
    expect(screen.getByText("Neuer Verein: SGi Neustadt 1862")).toBeInTheDocument();
    expect(screen.getByText("Der Name fehlt.")).toBeInTheDocument();
    expect(screen.getByText("Gibt es schon im selben Verein.")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("checkbox", { name: "Nur Dubletten und Fehler zeigen" }),
    );
    expect(screen.queryByText("Petra Lang")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "2 Personen importieren" }));
    expect(await screen.findByText("2 Personen importiert.")).toBeInTheDocument();
    expect(aufrufe.at(-1)?.pfad).toBe("/persons/import?dry_run=false");
  });

  it("zeigt die Erklärung des Servers, wenn die Datei unbrauchbar ist", async () => {
    serverAttrappe({
      "POST /persons/import?dry_run=true": {
        status: 400,
        inhalt: { detail: "Die Kopfzeile braucht eine Spalte „name“ oder „Name“." },
      },
    });
    renderAnsicht(() => <ImportSeite />);
    const ablage = await screen.findByRole("region", { name: "Datei wählen" });
    fireEvent.drop(ablage, {
      dataTransfer: {
        files: [new File(["Vorname;Verein\nA;B\n"], "liste.csv", { type: "text/csv" })],
      },
    });
    expect(await screen.findByText("Die Datei lässt sich nicht importieren")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByText(/braucht eine Spalte „name“/).length).toBeGreaterThan(0),
    );
  });

  it("lehnt Dateien ohne CSV-Endung ab, ohne den Server zu fragen", async () => {
    const aufrufe = serverAttrappe({});
    renderAnsicht(() => <ImportSeite />);
    await screen.findByRole("region", { name: "Datei wählen" });
    const eingabe = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(eingabe, new File(["x"], "bild.png", { type: "image/png" }), {
      applyAccept: false,
    });
    expect(
      await screen.findByText("Bitte eine CSV-Datei wählen (Endung .csv)."),
    ).toBeInTheDocument();
    expect(aufrufe).toHaveLength(0);
  });
});
