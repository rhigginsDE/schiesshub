import { describe, expect, it } from "vitest";
import { istNurDiesesGeraet, kopplungsAdresse } from "./Geraete";

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
});
