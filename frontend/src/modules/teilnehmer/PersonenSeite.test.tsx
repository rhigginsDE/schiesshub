import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { teilnehmerSchluessel } from "./api";
import { PersonenSeite } from "./PersonenSeite";
import type { PersonenAdresse } from "./pfade";
import {
  BRANDT,
  KOEHLER,
  MAIER,
  person,
  renderAnsicht,
  serverAttrappe,
  VEREIN_HUBERTUS,
  VEREIN_TELL,
} from "./testhilfe";

// Mantine scrollt vorgewählte Optionen ins Bild; jsdom kennt scrollIntoView nicht.
beforeAll(() => {
  Element.prototype.scrollIntoView ??= () => {};
});

const LISTE = "GET /persons?limit=50";
const VEREINE = { inhalt: [VEREIN_TELL, VEREIN_HUBERTUS] };

function Seite({ start = {} }: { start?: PersonenAdresse }) {
  const [adresse, setAdresse] = useState<PersonenAdresse>(start);
  return <PersonenSeite adresse={adresse} onAdresse={setAdresse} />;
}

describe("Personen", () => {
  it("zeigt die Gesamtzahl aus X-Total-Count und öffnet mit / und Enter den ersten Treffer", async () => {
    serverAttrappe({
      [LISTE]: { inhalt: [BRANDT, MAIER, KOEHLER], kopf: { "X-Total-Count": "214" } },
      "GET /persons?q=koehler&limit=50": { inhalt: [KOEHLER], kopf: { "X-Total-Count": "1" } },
      [`GET /persons/${KOEHLER.id}`]: { inhalt: KOEHLER },
      "GET /clubs": VEREINE,
    });
    renderAnsicht(() => <Seite />);

    expect(await screen.findByText("214 Personen gespeichert")).toBeInTheDocument();
    expect(
      screen.getByText("3 von 214 angezeigt. Suche eingrenzen, um weitere zu finden."),
    ).toBeInTheDocument();
    // Abgekürzte Anzeige ist in der Trefferliste sichtbar
    expect(screen.getByText("abgekürzt")).toBeInTheDocument();

    await userEvent.keyboard("/");
    const suche = screen.getByRole("searchbox", { name: "Person suchen" });
    expect(suche).toHaveFocus();
    await userEvent.keyboard("koehler{Enter}");

    expect(await screen.findByRole("heading", { name: "Sabine Köhler" })).toBeInTheDocument();
    // Vorschau zeigt, was der Server liefert
    const vorschau = screen.getByText("So erscheint die Person").closest("figure");
    expect(within(vorschau as HTMLElement).getByText("S. Köhler")).toBeInTheDocument();
  });

  it("Esc im leeren Suchfeld schließt die geöffnete Person", async () => {
    serverAttrappe({
      [LISTE]: { inhalt: [BRANDT] },
      [`GET /persons/${BRANDT.id}`]: { inhalt: BRANDT },
      "GET /clubs": VEREINE,
    });
    renderAnsicht(() => <Seite start={{ person: BRANDT.id }} />);
    expect(await screen.findByRole("heading", { name: "Markus Brandt" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("searchbox", { name: "Person suchen" }));
    await userEvent.keyboard("{Escape}");
    expect(await screen.findByText("Keine Person geöffnet")).toBeInTheDocument();
  });

  it("zeigt beim Anlegen einer Dublette die Kandidaten und legt auf Wunsch trotzdem an", async () => {
    const neu = person("dddddddd-dddd-4ddd-8ddd-dddddddddddd", "Markus Brandt", {
      display_mode: "short",
      display_name: "M. Brandt",
    });
    const aufrufe = serverAttrappe({
      [LISTE]: { inhalt: [BRANDT] },
      "GET /persons?q=Markus+Brandt&limit=50": { inhalt: [BRANDT] },
      "GET /clubs": VEREINE,
      "POST /persons": {
        status: 409,
        inhalt: { detail: "Ähnliche Person vorhanden.", candidates: [BRANDT] },
      },
      "POST /persons?force=true": { status: 201, inhalt: neu },
      [`GET /persons/${neu.id}`]: { inhalt: neu },
    });
    renderAnsicht(() => <Seite />);

    await userEvent.type(await screen.findByRole("searchbox"), "Markus Brandt");
    await userEvent.click(
      await screen.findByRole("button", { name: "„Markus Brandt“ neu anlegen" }),
    );

    const name = await screen.findByRole("textbox", { name: /^Name/ });
    expect(name).toHaveValue("Markus Brandt");

    // Verein im Feld suchen und wählen
    await userEvent.click(screen.getByPlaceholderText("Verein suchen oder neu anlegen"));
    await userEvent.keyboard("tell");
    expect(await screen.findByText("„tell“ als neuen Verein anlegen")).toBeInTheDocument();
    await userEvent.keyboard("{Enter}");
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Verein suchen oder neu anlegen")).toHaveValue(
        "SV Tell Musterstadt",
      ),
    );

    // Live-Vorschau mit gleicher Regel wie der Server
    await userEvent.click(screen.getByText("Abgekürzt"));
    const vorschau = screen.getByText("So erscheint die Person").closest("figure") as HTMLElement;
    expect(within(vorschau).getByText("M. Brandt")).toBeInTheDocument();
    expect(within(vorschau).getByText("SV Tell Musterstadt")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Person anlegen" }));
    const hinweis = await screen.findByText("Gibt es diese Person schon?");
    const bereich = hinweis.closest("section") as HTMLElement;
    expect(within(bereich).getByText("Markus Brandt")).toBeInTheDocument();
    expect(
      within(bereich).getByRole("button", { name: "Diese Person öffnen" }),
    ).toBeInTheDocument();

    await userEvent.click(within(bereich).getByRole("button", { name: "Trotzdem anlegen" }));
    expect(await screen.findByText("Person angelegt.")).toBeInTheDocument();

    const anlegen = aufrufe.filter((a) => a.methode === "POST");
    expect(anlegen.map((a) => a.pfad)).toEqual(["/persons", "/persons?force=true"]);
    expect(anlegen[1]?.inhalt).toEqual({
      name: "Markus Brandt",
      club_id: VEREIN_TELL.id,
      member_no: null,
      display_mode: "short",
      show_club: true,
    });
  });

  it("speichert mit dem neu angelegten Verein, auch wenn sofort nach der Vereinswahl abgeschickt wird", async () => {
    const neuerVerein = {
      ...VEREIN_HUBERTUS,
      id: "33333333-3333-4333-8333-333333333333",
      name: "SG Probe 1920",
      person_count: 0,
    };
    const neu = person("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", "Aylin Demir", {
      club_id: neuerVerein.id,
      club_name: neuerVerein.name,
      display_club: neuerVerein.name,
    });
    const aufrufe = serverAttrappe({
      [LISTE]: { inhalt: [] },
      "GET /clubs": VEREINE,
      "POST /clubs": { status: 201, inhalt: neuerVerein },
      "POST /persons": { status: 201, inhalt: neu },
      [`GET /persons/${neu.id}`]: { inhalt: neu },
    });
    // Das Anlegen des Vereins dauert, bis `freigeben` aufgerufen wird.
    let freigeben: () => void = () => {};
    const tor = new Promise<void>((weiter) => {
      freigeben = weiter;
    });
    const attrappe = globalThis.fetch;
    vi.stubGlobal("fetch", async (eingabe: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST" && String(eingabe).endsWith("/clubs")) await tor;
      return attrappe(eingabe, init);
    });
    renderAnsicht(() => <Seite start={{ neu: true }} />);

    await userEvent.type(await screen.findByRole("textbox", { name: /^Name/ }), "Aylin Demir");
    await userEvent.click(screen.getByPlaceholderText("Verein suchen oder neu anlegen"));
    await userEvent.keyboard("SG Probe 1920");
    await userEvent.click(await screen.findByText("„SG Probe 1920“ als neuen Verein anlegen"));
    // Noch bevor der Server den Verein bestätigt hat
    await userEvent.click(screen.getByRole("button", { name: "Person anlegen" }));
    expect(aufrufe.some((a) => a.methode === "POST" && a.pfad === "/persons")).toBe(false);

    await act(async () => freigeben());
    expect(await screen.findByText("Person angelegt.")).toBeInTheDocument();
    const anlegen = aufrufe.filter((a) => a.methode === "POST" && a.pfad === "/persons");
    expect(anlegen).toHaveLength(1);
    expect(anlegen[0]?.inhalt).toMatchObject({ name: "Aylin Demir", club_id: neuerVerein.id });
  });

  it("fragt nicht nach ungespeicherten Änderungen, während die neue Person gespeichert wird", async () => {
    const neu = person("ffffffff-ffff-4fff-8fff-ffffffffffff", "Bernd Krause");
    serverAttrappe({
      [LISTE]: { inhalt: [] },
      "GET /clubs": VEREINE,
      "POST /persons": { status: 201, inhalt: neu },
      [`GET /persons/${neu.id}`]: { inhalt: neu },
    });
    let freigeben: () => void = () => {};
    const tor = new Promise<void>((weiter) => {
      freigeben = weiter;
    });
    const attrappe = globalThis.fetch;
    vi.stubGlobal("fetch", async (eingabe: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST" && String(eingabe).endsWith("/persons")) await tor;
      return attrappe(eingabe, init);
    });
    renderAnsicht(() => <Seite start={{ neu: true }} />);

    await userEvent.type(await screen.findByRole("textbox", { name: /^Name/ }), "Bernd Krause");
    await userEvent.click(screen.getByRole("button", { name: "Person anlegen" }));
    // Speichern läuft noch; gleich die nächste Person beginnen
    await userEvent.click(screen.getByRole("button", { name: "Neue Person anlegen" }));
    expect(screen.queryByText("Änderungen verwerfen?")).not.toBeInTheDocument();

    await act(async () => freigeben());
    // Nach dem Speichern öffnet sich das leere Formular für die nächste Person
    await waitFor(() => expect(screen.getByRole("textbox", { name: /^Name/ })).toHaveValue(""));
    expect(screen.queryByText("Änderungen verwerfen?")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Neue Person" })).toBeInTheDocument();
  });

  it("ändert nur die geänderten Felder und zeigt einen Widerspruch beim Löschen verständlich", async () => {
    const aufrufe = serverAttrappe({
      [LISTE]: { inhalt: [BRANDT] },
      [`GET /persons/${BRANDT.id}`]: { inhalt: BRANDT },
      "GET /clubs": VEREINE,
      [`PATCH /persons/${BRANDT.id}`]: {
        inhalt: {
          ...BRANDT,
          show_club: false,
          display_club: null,
          updated_at: "2026-11-21T11:00:00Z",
        },
      },
      [`DELETE /persons/${BRANDT.id}`]: {
        status: 409,
        inhalt: { detail: "Die Person ist in einem laufenden Turnier angemeldet." },
      },
    });
    renderAnsicht(() => <Seite start={{ person: BRANDT.id }} />);

    await userEvent.click(await screen.findByRole("switch", { name: "Verein anzeigen" }));
    expect(screen.getByText("Ungespeicherte Änderungen")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
    expect(aufrufe.find((a) => a.methode === "PATCH")?.inhalt).toEqual({ show_club: false });

    await userEvent.click(screen.getByRole("button", { name: "Löschen" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/lässt sich nicht rückgängig machen/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Endgültig löschen" }));
    expect(
      await within(dialog).findByText(/Die Person ist in einem laufenden Turnier angemeldet/),
    ).toBeInTheDocument();
  });

  it("behält eine laufende Eingabe, wenn der Server einen neuen Stand meldet", async () => {
    let stand = BRANDT;
    serverAttrappe({
      [LISTE]: () => ({ inhalt: [stand] }),
      [`GET /persons/${BRANDT.id}`]: () => ({ inhalt: stand }),
      "GET /clubs": VEREINE,
    });
    const { queryClient } = renderAnsicht(() => <Seite start={{ person: BRANDT.id }} />);

    const nr = await screen.findByRole("textbox", { name: /Mitgliedsnummer/ });
    await userEvent.clear(nr);
    await userEvent.type(nr, "99 0001");

    // Anderes Gerät ändert den Namen; Ereignis person.updated lädt neu
    stand = { ...BRANDT, name: "Markus Brand", updated_at: "2026-11-21T12:00:00Z" };
    await act(() => queryClient.invalidateQueries({ queryKey: teilnehmerSchluessel.alle }));

    expect(
      await screen.findByText(/inzwischen an einem anderen Gerät geändert/),
    ).toBeInTheDocument();
    expect(nr).toHaveValue("99 0001");
    expect(screen.getByRole("textbox", { name: /^Name/ })).toHaveValue("Markus Brandt");

    await userEvent.click(screen.getByRole("button", { name: "Neuen Stand laden" }));
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: /^Name/ })).toHaveValue("Markus Brand"),
    );
    expect(nr).toHaveValue("10 2231");
  });

  it("übernimmt einen neuen Stand ohne Rückfrage, solange nichts eingegeben ist", async () => {
    let stand = BRANDT;
    serverAttrappe({
      [LISTE]: () => ({ inhalt: [stand] }),
      [`GET /persons/${BRANDT.id}`]: () => ({ inhalt: stand }),
      "GET /clubs": VEREINE,
    });
    const { queryClient } = renderAnsicht(() => <Seite start={{ person: BRANDT.id }} />);
    const name = await screen.findByRole("textbox", { name: /^Name/ });
    stand = { ...BRANDT, name: "Markus Brand", updated_at: "2026-11-21T12:00:00Z" };
    await act(() => queryClient.invalidateQueries({ queryKey: teilnehmerSchluessel.alle }));
    await waitFor(() => expect(name).toHaveValue("Markus Brand"));
  });
});
