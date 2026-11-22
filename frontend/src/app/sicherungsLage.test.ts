import { describe, expect, it } from "vitest";
import { bannerAktion } from "./sicherungsLage";

describe("bannerAktion", () => {
  it("bietet „Erneut prüfen“ nur bei Stick-Problemen", () => {
    for (const code of [
      "usb_missing",
      "usb_not_writable",
      "usb_full",
      "usb_copy_failed",
      "journal_sync_failed",
    ]) {
      expect(bannerAktion(code)).toBe("pruefen");
    }
  });

  it("fehlendes Passwort führt zum Passwort, Einstellungen zur Sicherung", () => {
    expect(bannerAktion("passphrase_missing")).toBe("passwort");
    expect(bannerAktion("backup_disabled")).toBe("sicherung");
    expect(bannerAktion("snapshot_failed")).toBe("sicherung");
  });

  it("unbekannte Warnungen führen zur Sicherung statt ins Leere", () => {
    expect(bannerAktion("etwas_neues")).toBe("sicherung");
  });
});
