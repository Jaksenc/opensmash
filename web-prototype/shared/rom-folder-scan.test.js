import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";
import { collectRomCandidates, scanFolderForRom } from "../src/rom-folder-scan.js";

const MIB = 1024 * 1024;
if (!globalThis.crypto?.subtle) globalThis.crypto = webcrypto;

// Minimal stand-ins for FileSystemDirectoryHandle / FileSystemFileHandle.
function fakeFile(name, size, { header = true } = {}) {
  const bytes = new Uint8Array(Math.min(size, 8192));
  if (header) bytes.set([0x80, 0x37, 0x12, 0x40], 0);
  return {
    name,
    size,
    slice(start, end) {
      return { arrayBuffer: async () => bytes.slice(start, end).buffer };
    },
    async arrayBuffer() { return bytes.buffer; },
  };
}
function fileHandle(file) {
  return { kind: "file", name: file.name, getFile: async () => file };
}
function dir(name, entries) {
  return {
    kind: "directory",
    name,
    async *values() { for (const entry of entries) yield entry; },
  };
}

test("collectRomCandidates walks nested folders, skips junk, and ranks the likely file first", async () => {
  const root = dir("Games", [
    fileHandle(fakeFile("readme.txt", 1200)),
    dir("node_modules", [fileHandle(fakeFile("trap.z64", 16 * MIB))]),
    dir(".hidden", [fileHandle(fakeFile("trap2.z64", 16 * MIB))]),
    dir("N64", [
      fileHandle(fakeFile("Mario Kart 64.z64", 12 * MIB)),
      fileHandle(fakeFile("Super Smash Bros. (USA).z64", 16 * MIB)),
      dir("more", [fileHandle(fakeFile("mystery", 16 * MIB))]),
    ]),
  ]);
  const progress = [];
  const result = await collectRomCandidates(root, { onProgress: (event) => progress.push(event) });
  assert.deepEqual(result.candidates.map((candidate) => candidate.name), ["Super Smash Bros. (USA).z64", "mystery"]);
  assert.equal(result.candidates[0].path, "Games/N64/Super Smash Bros. (USA).z64");
  assert.equal(result.truncated, false);
  assert.ok(progress.length >= 1);
});

test("collectRomCandidates stops at the entry budget", async () => {
  const many = Array.from({ length: 50 }, (_, index) => fileHandle(fakeFile(`file${index}.bin`, 10)));
  const result = await collectRomCandidates(dir("big", many), { limits: { maxDepth: 2, maxEntries: 10, maxCandidates: 5, timeBudgetMs: 60_000 } });
  assert.equal(result.truncated, true);
  assert.ok(result.entries <= 11);
});

test("scanFolderForRom returns the first file the identifier accepts and skips header-less files", async () => {
  const wrongHeader = fakeFile("garbage.z64", 16 * MIB, { header: false });
  const smash = fakeFile("smash.z64", 16 * MIB);
  const identified = [];
  const file = await scanFolderForRom({
    pickDirectory: async () => dir("roms", [fileHandle(wrongHeader), fileHandle(smash)]),
    identify: async (candidate) => { identified.push(candidate.name); return candidate === smash ? { sha1: "x" } : null; },
  });
  assert.equal(file, smash);
  // garbage.z64 fails the cheap header probe and never reaches the identifier.
  assert.deepEqual(identified, ["smash.z64"]);
});

test("scanFolderForRom explains an empty or unsupported folder and honours picker cancel", async () => {
  assert.equal(await scanFolderForRom({ pickDirectory: async () => { throw Object.assign(new Error("cancel"), { name: "AbortError" }); } }), null);

  await assert.rejects(
    scanFolderForRom({ pickDirectory: async () => dir("Photos", [fileHandle(fakeFile("a.jpg", 3 * MIB))]) }),
    /No ROM-sized files found in “Photos”/,
  );

  const japan = new Error("That is the Japan release, which this port cannot run yet.");
  await assert.rejects(
    scanFolderForRom({
      pickDirectory: async () => dir("roms", [fileHandle(fakeFile("jp.z64", 16 * MIB)), fileHandle(fakeFile("other.z64", 16 * MIB))]),
      identify: async (candidate) => { if (candidate.name === "jp.z64") throw japan; return null; },
    }),
    /Japan release/,
  );

  await assert.rejects(
    scanFolderForRom({
      pickDirectory: async () => dir("roms", [fileHandle(fakeFile("other.z64", 16 * MIB))]),
      identify: async () => null,
    }),
    /Checked 1 likely file in “roms”/,
  );
});
