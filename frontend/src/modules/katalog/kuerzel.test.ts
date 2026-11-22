import { describe, expect, it } from "vitest";
import { verwendeteKuerzel } from "./kuerzel";

describe("verwendeteKuerzel", () => {
  it("findet nur Kürzel, die im Text vorkommen", () => {
    expect(verwendeteKuerzel("über .38; MI 150")).toEqual(["mi"]);
    expect(verwendeteKuerzel("Schrot bis 12/89 Z12")).toEqual(["z_scheibe"]);
    expect(verwendeteKuerzel("KW-Patronen (Anhang 1), MI 125")).toEqual(["mi", "kw_patronen"]);
  });

  it("erklärt keine Wortteile und keine Verweise ohne Quelle", () => {
    expect(verwendeteKuerzel("Mindestens MIT Zielfernrohr, K 4.06/4.07")).toEqual([]);
  });
});
