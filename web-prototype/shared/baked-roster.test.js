import assert from "node:assert/strict";
import test from "node:test";
import { bakedRosterEntries, bakedRosterSlugs } from "./baked-roster.js";

test("baked roster manifest preserves its explicit order", () => {
  assert.deepEqual(
    bakedRosterSlugs([{ slug: "queen" }, "joeyflynn"]),
    ["queen", "joeyflynn"],
  );
});

test("baked roster manifest rejects invalid and duplicate slugs", () => {
  assert.throws(() => bakedRosterEntries([{ slug: "not-valid" }]), /Invalid baked character/);
  assert.throws(
    () => bakedRosterEntries([{ slug: "queen" }, { slug: "queen" }]),
    /Duplicate baked character 'queen'/,
  );
});
