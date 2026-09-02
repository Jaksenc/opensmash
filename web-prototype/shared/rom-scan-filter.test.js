import assert from "node:assert/strict";
import test from "node:test";
import { isRomScanCandidate, rankRomCandidates, shouldDescend } from "./rom-scan-filter.js";

const MIB = 1024 * 1024;

test("exact-size files are candidates regardless of extension", () => {
  assert.equal(isRomScanCandidate({ name: "game", size: 16 * MIB }), true);
  assert.equal(isRomScanCandidate({ name: "game.dat", size: 16 * MIB + 512 }), true);
  assert.equal(isRomScanCandidate({ name: "movie.mp4", size: 900 * MIB }), false);
  assert.equal(isRomScanCandidate({ name: "photo.jpg", size: 3 * MIB }), false);
});

test("known ROM extensions tolerate over-dumps but not tiny files", () => {
  assert.equal(isRomScanCandidate({ name: "Super Smash Bros. (USA).z64", size: 16 * MIB }), true);
  assert.equal(isRomScanCandidate({ name: "smash.v64", size: 32 * MIB }), true);
  assert.equal(isRomScanCandidate({ name: "smash.n64", size: 65 * MIB }), false);
  assert.equal(isRomScanCandidate({ name: "mario.z64", size: 8 * MIB }), false);
  assert.equal(isRomScanCandidate({ name: "SMASH.Z64", size: 16 * MIB }), true);
});

test("zips are candidates only in a plausible compressed range", () => {
  assert.equal(isRomScanCandidate({ name: "smash.zip", size: 9 * MIB }), true);
  assert.equal(isRomScanCandidate({ name: "smash.zip", size: 200 * 1024 }), false);
  assert.equal(isRomScanCandidate({ name: "everything.zip", size: 3 * 1024 * MIB }), false);
});

test("bad input is never a candidate", () => {
  assert.equal(isRomScanCandidate({ name: "", size: 16 * MIB }), false);
  assert.equal(isRomScanCandidate({ name: "x.z64", size: 0 }), false);
  assert.equal(isRomScanCandidate({ name: "x.z64", size: Number.NaN }), false);
});

test("shouldDescend skips hidden, system, and deep directories", () => {
  assert.equal(shouldDescend("roms", 0), true);
  assert.equal(shouldDescend(".hidden", 0), false);
  assert.equal(shouldDescend("node_modules", 0), false);
  assert.equal(shouldDescend("Library", 1), false);
  assert.equal(shouldDescend("roms", 8), false);
  assert.equal(shouldDescend("roms", 7), true);
});

test("rankRomCandidates hashes the likeliest file first", () => {
  const ranked = rankRomCandidates([
    { name: "zelda.z64", size: 32 * MIB },
    { name: "unknown.bin", size: 16 * MIB },
    { name: "Super Smash Bros. (USA).zip", size: 9 * MIB },
    { name: "ssb.z64", size: 16 * MIB },
  ]);
  assert.deepEqual(ranked.map((candidate) => candidate.name), [
    "ssb.z64",
    "Super Smash Bros. (USA).zip",
    "unknown.bin",
    "zelda.z64",
  ]);
});
