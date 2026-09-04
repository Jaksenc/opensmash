import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { parseOsb6Preview } from "./osb6-preview.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PLAY = path.resolve(HERE, "..", "..", "play");
const STARTER = JSON.parse(readFileSync(
  path.resolve(HERE, "..", "config", "backyard-starter.json"), "utf8"));

// Statue bundles (scripts/backyard_statues.py) must survive the repo's own
// OSB6 preview parser: finite positions, in-range indices, sane bbox.
// Missing bundles (fresh clone without `backyard:sprites` output) skip:
// play/ is gitignored, so CI-style checkouts have no .osb6 at all.
for (const entry of STARTER) {
  test(`statue bundle parses: ${entry.slug}`, () => {
    const file = path.join(PLAY, `${entry.slug}.osb6`);
    if (!existsSync(file)) {
      console.log(`  (skip: ${entry.slug}.osb6 not built)`);
      return;
    }
    const parsed = parseOsb6Preview(new Uint8Array(readFileSync(file)), 0);
    assert.ok(parsed.positions.length > 0);
    assert.ok(parsed.indices.length > 0);
    let minY = Infinity, maxY = -Infinity;
    for (let i = 0; i < parsed.positions.length; i += 3) {
      const [x, y, z] = [parsed.positions[i], parsed.positions[i + 1], parsed.positions[i + 2]];
      assert.ok(Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z));
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    }
    for (const index of parsed.indices) {
      assert.ok(index < parsed.positions.length / 3, "index out of range");
    }
    // chibi statue: ~2 units tall, feet at y=0
    assert.ok(Math.abs(minY) < 0.05, `feet off ground: ${minY}`);
    assert.ok(maxY > 1.5 && maxY < 2.5, `height off: ${maxY}`);
    assert.equal(parsed.textureWidth, 512);
  });
}

test("backyard starter slugs have matching sprite packs", () => {
  if (!existsSync(PLAY)) {
    console.log("  (skip: play/ absent)");
    return;
  }
  const files = new Set(readdirSync(PLAY));
  for (const entry of STARTER) {
    if (!files.has(`${entry.slug}.osb6`)) continue; // covered above
    const ui = path.join(PLAY, "ui", entry.slug);
    assert.ok(existsSync(path.join(ui, `${entry.slug}.osbui`)), `${entry.slug}.osbui`);
    assert.ok(existsSync(path.join(ui, "announcer.wav")), "announcer.wav");
  }
});
