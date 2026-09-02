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

test("character search tolerates conservative misspellings in full names", () => {
  const person = { name: "Abraham Lincoln", short: "LINCOLN", slug: "abraham-lincoln" };

  assert.equal(matchesCharacterSearch(person, "Abrahm Lincon"), true);
  assert.equal(matchesCharacterSearch(person, "Abrhaam Lincoln"), true);
  assert.equal(matchesCharacterSearch(person, "Aberham Linkon"), false);
});

test("character search tolerates misspellings in compact names and slugs", () => {
  assert.equal(matchesCharacterSearch(fighter, "marioprme"), true);
  assert.equal(matchesCharacterSearch(fighter, "maroi"), true);
});

test("character search keeps very short terms exact to avoid noisy matches", () => {
  assert.equal(matchesCharacterSearch({ name: "Mao Zedong" }, "mae"), false);
  assert.equal(matchesCharacterSearch({ name: "Tom Hanks" }, "tim"), false);
});
