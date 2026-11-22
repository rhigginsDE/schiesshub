import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiFehler, beiApiFehler } from "../../api/client";
import { SeqKonflikt, sendeVorgang } from "./api";

function antwort(status: number, inhalt?: unknown): Response {
  return new Response(inhalt === undefined ? null : JSON.stringify(inhalt), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function fetchMit(a: Response) {
  const mock = vi.fn<typeof fetch>().mockResolvedValueOnce(a);
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("sendeVorgang", () => {
  it("sendet den Idempotency-Key und liefert den neuen Stand", async () => {
    const mock = fetchMit(antwort(200, { seq: 2, status: "open" }));
    const stand = await sendeVorgang("PUT", "/raw", { raw: {} }, "schluessel-1");
    expect(stand).toEqual({ seq: 2, status: "open" });
    const kopf = mock.mock.calls[0]?.[1]?.headers as Record<string, string>;
    expect(kopf["Idempotency-Key"]).toBe("schluessel-1");
    expect(kopf["X-Schiesshub-Request"]).toBe("1");
  });

  it("macht aus 409 mit aktuellem Stand einen SeqKonflikt", async () => {
    fetchMit(antwort(409, { detail: "veraltet", current: { seq: 5 } }));
    const fehler = await sendeVorgang("PUT", "/raw", {}, "k").catch((f: unknown) => f);
    expect(fehler).toBeInstanceOf(SeqKonflikt);
    expect((fehler as SeqKonflikt).detail).toBe("veraltet");
    expect((fehler as SeqKonflikt).aktuell).toEqual({ seq: 5 });
  });

  it("lässt 409 ohne Stand ein ApiFehler bleiben", async () => {
    fetchMit(antwort(409, { detail: "Schon abgeschlossen." }));
    const fehler = await sendeVorgang("POST", "/finalize", {}, "k").catch((f: unknown) => f);
    expect(fehler).toBeInstanceOf(ApiFehler);
    expect((fehler as ApiFehler).art).toBe("konflikt");
  });

  it("liefert bei 422 die Feldfehler und meldet 401 nicht an die App-Shell", async () => {
    fetchMit(
      antwort(422, {
        detail: "Eingabe prüfen",
        errors: [{ field: "raw.abschnitte[0].serien", message: "zu groß" }],
      }),
    );
    const fehler = (await sendeVorgang("PUT", "/raw", {}, "k").catch(
      (f: unknown) => f,
    )) as ApiFehler;
    expect(fehler.status).toBe(422);
    expect(fehler.felder).toEqual([{ feld: "raw.abschnitte.0.serien", meldung: "zu groß" }]);

    const gemeldet = vi.fn();
    const abmelden = beiApiFehler(gemeldet);
    fetchMit(antwort(401, {}));
    await sendeVorgang("PUT", "/raw", {}, "k").catch(() => undefined);
    expect(gemeldet).not.toHaveBeenCalled();
    abmelden();
  });

  it("meldet einen Verbindungsabbruch als Netzwerkfehler", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValueOnce(new TypeError("weg")));
    const fehler = (await sendeVorgang("PUT", "/raw", {}, "k").catch(
      (f: unknown) => f,
    )) as ApiFehler;
    expect(fehler.art).toBe("netzwerk");
  });
});
