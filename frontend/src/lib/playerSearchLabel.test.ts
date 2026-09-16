import { describe, expect, test } from "vite-plus/test";
import { playerSearchHaystack, resolvePlayerSearchEntry } from "./playerSearchLabel";

describe("player search identity", () => {
  const hartfeil = {
    id: "7830",
    name: "Hartfeil, Volkmar",
    aliases: ["Hartfeil-Ave, Volkmar", "Hartfeil , Volkmar"],
  };

  test("matches alias spellings in the haystack", () => {
    const haystack = playerSearchHaystack(hartfeil).toLowerCase();
    expect(haystack).toContain("hartfeil-ave");
    expect(haystack).toContain("7830");
  });

  test("resolves a catalog row by alias", () => {
    expect(resolvePlayerSearchEntry([hartfeil], { name: "Hartfeil-Ave, Volkmar" })).toEqual(
      hartfeil,
    );
  });
});
