import { describe, expect, it } from "vitest";
import { brauchbareAdressen, istNurDiesesGeraet, kopplungsAdresse } from "./Geraete";

describe("Kopplungsadresse", () => {
  it("setzt die Adresse aus der Herkunft dieses Browsers zusammen", () => {
    expect(kopplungsAdresse("/pair?code=AB", "http://192.168.1.20:8080")).toBe(
      "http://192.168.1.20:8080/pair?code=AB",
    );
    expect(kopplungsAdresse("pair?code=AB", "https://schiesshub.local")).toBe(
      "https://schiesshub.local/pair?code=AB",
    );
  });

  it("erkennt Adressen, die nur auf diesem Gerät gelten", () => {
    for (const lokal of [
      "http://localhost:5180",
      "http://LOCALHOST",
      "http://127.0.0.1:8010",
      "http://127.1.2.3",
      "http://[::1]:5173",
      "http://0.0.0.0:5180",
    ]) {
      expect(istNurDiesesGeraet(lokal), lokal).toBe(true);
    }
    for (const netz of [
      "http://192.168.1.20",
      "https://schiesshub.local",
      "http://10.0.0.5:8080",
      "http://localhost.example.de",
    ]) {
      expect(istNurDiesesGeraet(netz), netz).toBe(false);
    }
  });

  it("nimmt aus den Adressen des Servers nur die, die andere Geräte erreichen", () => {
    expect(
      brauchbareAdressen([
        "http://localhost:8010",
        "http://192.168.1.20:8080",
        "http://127.0.0.1",
        "https://schiesshub.local",
      ]),
    ).toEqual(["http://192.168.1.20:8080", "https://schiesshub.local"]);
    expect(brauchbareAdressen(["http://localhost:5180"])).toEqual([]);
    expect(brauchbareAdressen(undefined)).toEqual([]);
    const [erste] = brauchbareAdressen(["http://127.0.0.1", "http://10.0.0.5"]);
    expect(kopplungsAdresse("/pair?code=AB", erste)).toBe("http://10.0.0.5/pair?code=AB");
  });
});
