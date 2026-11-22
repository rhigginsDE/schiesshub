import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiFehler, apiSenden, beiApiFehler } from "./client";

function antwort(status: number, inhalt?: unknown): Response {
  return new Response(inhalt === undefined ? null : JSON.stringify(inhalt), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function fetchMit(...antworten: Response[]) {
  const mock = vi.fn<typeof fetch>();
  for (const a of antworten) mock.mockResolvedValueOnce(a);
  vi.stubGlobal("fetch", mock);
  return mock;
}

function kopfVon(mock: ReturnType<typeof fetchMit>, aufruf = 0): Record<string, string> {
  return (mock.mock.calls[aufruf]?.[1]?.headers ?? {}) as Record<string, string>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiSenden", () => {
  it("sendet eigene Kopfzeilen mit, z. B. Idempotency-Key", async () => {
    const mock = fetchMit(antwort(200, { ok: true }));
    await apiSenden("POST", "/x", { a: 1 }, { kopf: { "Idempotency-Key": "abc" } });
    expect(kopfVon(mock)).toMatchObject({
      "Idempotency-Key": "abc",
      "X-Schiesshub-Request": "1",
      "Content-Type": "application/json",
    });
  });

  it("lässt Schutz-Kopfzeile und Inhaltstyp nicht überschreiben", async () => {
    const mock = fetchMit(antwort(204));
    await apiSenden(
      "PUT",
      "/x",
      { a: 1 },
      { kopf: { "x-schiesshub-request": "0", "content-type": "text/plain" } },
    );
    const kopf = kopfVon(mock);
    expect(kopf["X-Schiesshub-Request"]).toBe("1");
    expect(kopf["Content-Type"]).toBe("application/json");
    expect(kopf["x-schiesshub-request"]).toBeUndefined();
    expect(kopf["content-type"]).toBeUndefined();
  });

  it("liefert bei 409 mit Feldbezug die Meldung am Feld und den Inhalt", async () => {
    const inhalt = {
      detail: "Bahn 2 ist schon belegt.",
      errors: [{ field: "lane", message: "Bahn 2 ist schon belegt." }],
    };
    fetchMit(antwort(409, inhalt));
    const fehler = await apiSenden("POST", "/x", {}).catch((f: unknown) => f);
    expect(fehler).toBeInstanceOf(ApiFehler);
    const api = fehler as ApiFehler;
    expect(api.art).toBe("konflikt");
    expect(api.detail).toBe("Bahn 2 ist schon belegt.");
    expect(api.felder).toEqual([{ feld: "lane", meldung: "Bahn 2 ist schon belegt." }]);
    expect(api.inhalt).toEqual(inhalt);
  });

  it("meldet 401 nicht an die App-Shell, wenn die Anfrage still ist", async () => {
    const gemeldet = vi.fn();
    const abmelden = beiApiFehler(gemeldet);
    fetchMit(antwort(401, { detail: "Bitte anmelden." }), antwort(401, {}));
    await apiSenden("POST", "/x", {}, { still: true }).catch(() => undefined);
    expect(gemeldet).not.toHaveBeenCalled();
    await apiSenden("POST", "/x", {}).catch(() => undefined);
    expect(gemeldet).toHaveBeenCalledTimes(1);
    abmelden();
  });
});
