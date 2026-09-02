import assert from "node:assert/strict";
import test from "node:test";
import { mergeCharactersBySlug } from "./character-roster.js";

test("roster refresh keeps characters added while the request was in flight", () => {
  const refreshed = mergeCharactersBySlug(
    [
      { slug: "mario", name: "Mario" },
      { slug: "newcomer", name: "Newcomer", generated: true },
    ],
    [{ slug: "mario", name: "Mario" }],
  );

  assert.deepEqual(refreshed, [
    { slug: "mario", name: "Mario" },
    { slug: "newcomer", name: "Newcomer", generated: true },
  ]);
});

test("roster refresh uses API data for matching slugs without duplicates", () => {
  const refreshed = mergeCharactersBySlug(
    [{ slug: "newcomer", name: "Old name", generated: true }],
    [{ slug: "newcomer", name: "New name", generated: true }],
  );

  assert.deepEqual(refreshed, [{ slug: "newcomer", name: "New name", generated: true }]);
});
