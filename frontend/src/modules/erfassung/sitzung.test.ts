import { describe, expect, it, vi } from "vitest";
import { ApiFehler } from "../../api/client";
import { type ErgebnisStand, type Rohwerte, SeqKonflikt } from "./api";
import { type Entwurf, entwurfAus, rohwerteAus, setzeWert } from "./rohwerte";
import { Sitzung, type Uhr } from "./sitzung";
import { FALLSCHEIBE, stand } from "./testdaten";

/** Uhr, die nur auf Zuruf weiterläuft. */
function testUhr() {
  let jetzt = 0;
  let id = 0;
  const timer = new Map<number, { zeit: number; rueckruf: () => void }>();
  const uhr: Uhr = {
    setTimeout: (rueckruf, ms) => {
      id += 1;
      timer.set(id, { zeit: jetzt + ms, rueckruf });
      return id;
    },
    clearTimeout: (t) => {
      timer.delete(t as number);
    },
  };
  const vorspulen = async (ms: number) => {
    jetzt += ms;
    for (const [schluessel, t] of [...timer.entries()].sort((a, b) => a[1].zeit - b[1].zeit)) {
      if (t.zeit <= jetzt) {
        timer.delete(schluessel);
        t.rueckruf();
      }
    }
    // Versprechen abarbeiten lassen
    for (let i = 0; i < 5; i++) await Promise.resolve();
  };
  return { uhr, vorspulen };
}

const zeit = (e: Entwurf, wert: number) =>
  setzeWert(e, { abschnitt: "fallscheibe", serie: 0, key: "time_cs" }, wert);

function antwort(raw: Rohwerte, seq: number, teil: Partial<ErgebnisStand> = {}): ErgebnisStand {
  return stand({ raw, seq, status: "captured", ...teil });
}

function neueSitzung(
  senden: (raw: Rohwerte, seq: number, schluessel: string) => Promise<ErgebnisStand>,
) {
  const { uhr, vorspulen } = testUhr();
  const sitzung = new Sitzung({
    basis: stand(),
    rohwerte: (e) => rohwerteAus(FALLSCHEIBE, e),
    senden,
    uhr,
    verzoegerungMs: 400,
    wiederholungMs: [1000, 2000],
  });
  return { sitzung, vorspulen };
}

describe("Sende-Sitzung", () => {
  it("zeigt Eingaben sofort und sendet entprellt einmal", async () => {
    const senden = vi.fn(async (raw: Rohwerte, seq: number) => antwort(raw, seq + 1));
    const { sitzung, vorspulen } = neueSitzung(senden);
    sitzung.aendern(zeit(sitzung.lesen().entwurf, 1200));
    sitzung.aendern(zeit(sitzung.lesen().entwurf, 1284));
    expect(sitzung.lesen()).toMatchObject({ phase: "wartet", ungespeichert: true });
    await vorspulen(400);
    expect(senden).toHaveBeenCalledTimes(1);
    expect(senden.mock.calls[0]?.[0]).toEqual({
      sections: { fallscheibe: { series: [{ time_cs: 1284 }] } },
    });
    expect(senden.mock.calls[0]?.[1]).toBe(0);
    expect(sitzung.lesen()).toMatchObject({ phase: "gespeichert", ungespeichert: false });
    expect(sitzung.lesen().basis.seq).toBe(1);
  });

  it("wiederholt nach einem Netzfehler mit demselben Schlüssel", async () => {
    const senden = vi
      .fn<(raw: Rohwerte, seq: number, schluessel: string) => Promise<ErgebnisStand>>()
      .mockRejectedValueOnce(new ApiFehler("netzwerk", "/raw"))
      .mockImplementation(async (raw, seq) => antwort(raw, seq + 1));
    const { sitzung, vorspulen } = neueSitzung(senden);
    sitzung.aendern(zeit(sitzung.lesen().entwurf, 1284));
    await vorspulen(400);
    expect(sitzung.lesen()).toMatchObject({
      phase: "netzfehler",
      ungespeichert: true,
      versuche: 1,
    });
    await vorspulen(1000);
    expect(senden).toHaveBeenCalledTimes(2);
    expect(senden.mock.calls[1]?.[2]).toBe(senden.mock.calls[0]?.[2]);
    expect(sitzung.lesen().phase).toBe("gespeichert");
  });

  it("neue Eingabe nach Netzfehler bekommt einen neuen Schlüssel", async () => {
    const senden = vi
      .fn<(raw: Rohwerte, seq: number, schluessel: string) => Promise<ErgebnisStand>>()
      .mockRejectedValueOnce(new ApiFehler("netzwerk", "/raw"))
      .mockImplementation(async (raw, seq) => antwort(raw, seq + 1));
    const { sitzung, vorspulen } = neueSitzung(senden);
    sitzung.aendern(zeit(sitzung.lesen().entwurf, 1284));
    await vorspulen(400);
    sitzung.aendern(zeit(sitzung.lesen().entwurf, 1300));
    await vorspulen(400);
    expect(senden.mock.calls[1]?.[2]).not.toBe(senden.mock.calls[0]?.[2]);
  });

  it("409 mit Stand: nichts überschreiben, Entscheidung abwarten", async () => {
    const fremd = antwort({ sections: { fallscheibe: { series: [{ time_cs: 999 }] } } }, 4);
    const senden = vi
      .fn<(raw: Rohwerte, seq: number, schluessel: string) => Promise<ErgebnisStand>>()
      .mockRejectedValueOnce(new SeqKonflikt("veraltet", fremd))
      .mockImplementation(async (raw, seq) => antwort(raw, seq + 1));
    const { sitzung, vorspulen } = neueSitzung(senden);
    sitzung.aendern(zeit(sitzung.lesen().entwurf, 1284));
    await vorspulen(400);
    expect(sitzung.lesen()).toMatchObject({ phase: "konflikt", konflikt: fremd });
    // Weitere Eingaben senden nichts, solange der Konflikt offen ist.
    sitzung.aendern(zeit(sitzung.lesen().entwurf, 1290));
    await vorspulen(400);
    expect(senden).toHaveBeenCalledTimes(1);
    // „Meine Eingabe speichern“: auf dem Stand des Servers (seq 4) senden.
    sitzung.konfliktMeins();
    await vorspulen(0);
    expect(senden.mock.calls[1]?.[1]).toBe(4);
    expect(sitzung.lesen().basis.seq).toBe(5);
  });

  it("409: Stand des Servers laden verwirft die eigene Eingabe", async () => {
    const fremd = antwort({ sections: { fallscheibe: { series: [{ time_cs: 999 }] } } }, 4);
    const { sitzung, vorspulen } = neueSitzung(async () => {
      throw new SeqKonflikt("veraltet", fremd);
    });
    sitzung.aendern(zeit(sitzung.lesen().entwurf, 1284));
    await vorspulen(400);
    sitzung.konfliktServer();
    expect(sitzung.lesen()).toMatchObject({ phase: "gespeichert", ungespeichert: false });
    expect(sitzung.lesen().entwurf).toEqual(entwurfAus(fremd.raw));
  });

  it("422: Feldfehler mit Pfad, Eingabe bleibt", async () => {
    const { sitzung, vorspulen } = neueSitzung(async () => {
      throw new ApiFehler("anfrage", "/raw", 422, "Fehler", undefined, [
        { feld: "raw.sections.fallscheibe.series.0.time_cs", meldung: "größer 0" },
      ]);
    });
    sitzung.aendern(zeit(sitzung.lesen().entwurf, 1));
    await vorspulen(400);
    expect(sitzung.lesen()).toMatchObject({
      phase: "abgelehnt",
      ungespeichert: true,
      feldFehler: [{ pfad: "sections.fallscheibe.series.0.time_cs", meldung: "größer 0" }],
    });
  });

  it("fremde Änderung: übernehmen ohne eigene Eingabe, sonst Konflikt", async () => {
    const senden = vi.fn(async (raw: Rohwerte, seq: number) => antwort(raw, seq + 1));
    const { sitzung, vorspulen } = neueSitzung(senden);
    const fremd = antwort({ sections: { fallscheibe: { series: [{ time_cs: 777 }] } } }, 2);
    sitzung.serverStand(fremd);
    expect(sitzung.lesen()).toMatchObject({ fremdUebernommen: 1, ungespeichert: false });
    expect(sitzung.lesen().basis.seq).toBe(2);

    sitzung.aendern(zeit(sitzung.lesen().entwurf, 1284));
    sitzung.serverStand(antwort({}, 3));
    expect(sitzung.lesen().phase).toBe("konflikt");
    await vorspulen(400);
    expect(senden).not.toHaveBeenCalled();
  });

  it("ohne Automatik (Korrektur) wird nichts gesendet", async () => {
    const senden = vi.fn(async (raw: Rohwerte, seq: number) => antwort(raw, seq + 1));
    const { sitzung, vorspulen } = neueSitzung(senden);
    sitzung.setzeAutomatisch(false);
    sitzung.aendern(zeit(sitzung.lesen().entwurf, 1284));
    await vorspulen(2000);
    expect(senden).not.toHaveBeenCalled();
    expect(sitzung.lesen().ungespeichert).toBe(true);
  });
});
