import assert from "node:assert/strict";
import test from "node:test";
import { matchesCharacterSearch, normalizeSearchText } from "./character-search.js";

const fighter = { name: "Mário Prime", short: "MPRIME", slug: "marioprime" };

test("character search covers display name, short name, and slug", () => {
  assert.equal(matchesCharacterSearch(fighter, "mario"), true);
  assert.equal(matchesCharacterSearch(fighter, "mprime"), true);
  assert.equal(matchesCharacterSearch(fighter, "marioprime"), true);
  assert.equal(matchesCharacterSearch(fighter, "mario prime"), true);
  assert.equal(matchesCharacterSearch(fighter, "samus"), false);
});

test("character search normalization is accent and punctuation insensitive", () => {
  assert.equal(normalizeSearchText("  Mário—Prime! "), "mario prime");
});
